import uuid

import httpx
from google.genai import errors, types
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.core.graph_store import KnowledgeGraphStore, normalize_topic_name
from app.core.llm import get_genai_client
from app.schemas.bloom import BloomLevel
from app.schemas.course_outcome import CourseOutcome
from app.schemas.generation import QuestionDraftBatch
from app.schemas.question import Question, QuestionType
from app.services.vector_indexing import query_similar_chunks

GENERATION_PROMPT = """You are an exam question writer for a university course. Write exam questions \
strictly grounded in the SYLLABUS CONTEXT below — do not introduce facts that aren't supported by it.

TOPIC: {topic}

SYLLABUS CONTEXT (retrieved passages):
{context}

RELATED TOPICS (from the course knowledge graph):
{related_topics}

{co_section}
Write {num_questions} {question_type} question(s) at Bloom's level "{bloom_level}" worth {marks} marks \
each, about "{topic}".
- Ground every question in the syllabus context provided.
- Tag each question with the topic names it covers (topic_names): include "{topic}" and any related \
topics from the list above that the question actually draws on.
- If Course Outcomes were given, tag applicable co_codes; otherwise leave co_codes empty.
- For MCQ questions, include exactly 4 options and correct_answer must exactly match one option.
- For non-MCQ questions, leave options empty and correct_answer as a model answer or None.
"""


def _context_text(topic: str, n_chunks: int = 5) -> str:
    hits = query_similar_chunks(topic, n_results=n_chunks)
    if not hits:
        return "(no indexed syllabus content found for this topic)"
    return "\n\n".join(f"[{h['metadata'].get('source_document')}] {h['text']}" for h in hits)


def _related_topics_text(topic: str, graph_store: KnowledgeGraphStore) -> str:
    graph = graph_store.graph
    node_id = normalize_topic_name(topic)
    if node_id not in graph:
        return "(topic not found in knowledge graph)"

    lines: list[str] = []
    for pred in graph.predecessors(node_id):
        rel = graph.edges[pred, node_id].get("relation_type")
        lines.append(f"- {graph.nodes[pred].get('name', pred)} --[{rel}]--> {topic}")
    for succ in graph.successors(node_id):
        rel = graph.edges[node_id, succ].get("relation_type")
        lines.append(f"- {topic} --[{rel}]--> {graph.nodes[succ].get('name', succ)}")

    return "\n".join(lines) if lines else "(no direct relations found)"


def _co_section(course_outcomes: list[CourseOutcome] | None) -> str:
    if not course_outcomes:
        return ""
    listed = "\n".join(f"- {co.code}: {co.description}" for co in course_outcomes)
    return f"COURSE OUTCOMES (tag co_codes from this list only):\n{listed}\n"


@retry(
    retry=retry_if_exception_type((errors.ServerError, errors.APIError, httpx.TransportError)),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    reraise=True,
)
def generate_questions(
    topic: str,
    graph_store: KnowledgeGraphStore,
    num_questions: int = 3,
    bloom_level: BloomLevel = BloomLevel.UNDERSTAND,
    marks: int = 5,
    question_type: QuestionType = QuestionType.SHORT_ANSWER,
    course_outcomes: list[CourseOutcome] | None = None,
) -> list[Question]:
    """Generate exam questions for a topic, grounded in retrieved syllabus context
    and augmented with the topic's prerequisite/CO relationships from the knowledge graph.
    """
    settings = get_settings()
    client = get_genai_client()

    prompt = GENERATION_PROMPT.format(
        topic=topic,
        context=_context_text(topic),
        related_topics=_related_topics_text(topic, graph_store),
        co_section=_co_section(course_outcomes),
        num_questions=num_questions,
        question_type=question_type.value,
        bloom_level=bloom_level.name,
        marks=marks,
    )

    response = client.models.generate_content(
        model=settings.generation_model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=QuestionDraftBatch,
        ),
    )

    if response.parsed is None:
        return []

    graph = graph_store.graph
    questions: list[Question] = []
    for draft in response.parsed.questions:
        topic_ids = [
            normalize_topic_name(name)
            for name in draft.topic_names
            if normalize_topic_name(name) in graph
        ]
        questions.append(
            Question(
                id=str(uuid.uuid4()),
                text=draft.text,
                question_type=draft.question_type,
                marks=draft.marks,
                bloom_level=BloomLevel[draft.bloom_level],
                topic_ids=topic_ids,
                co_ids=draft.co_codes,
                options=draft.options,
                correct_answer=draft.correct_answer,
            )
        )

    return questions
