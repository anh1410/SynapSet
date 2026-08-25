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
from app.services.code_sandbox import CodeTimeoutError, UnsafeCodeError, run_code
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
{difficulty_section}

FORMAT RULES for {question_type}: {type_instruction}

- Ground every question in the syllabus context provided.
- Tag each question with the topic names it covers (topic_names): include "{topic}" and any related \
topics from the list above that the question actually draws on.
- If Course Outcomes were given, tag applicable co_codes; otherwise leave co_codes empty.
"""

QUESTION_TYPE_INSTRUCTIONS: dict[QuestionType, str] = {
    QuestionType.MCQ: "Include exactly 4 options in `options` and `correct_answer` must exactly match one option.",
    QuestionType.SHORT_ANSWER: "Leave `options` empty. Put a model answer (or key points) in `correct_answer`.",
    QuestionType.LONG_ANSWER: "Leave `options` empty. Put a model answer (or key points) in `correct_answer`.",
    QuestionType.NUMERICAL: "Leave `options` empty. Put the numeric answer in `correct_answer`.",
    QuestionType.FILL_IN_BLANK: (
        'Write the sentence in `text` with a literal "_____" placeholder marking the blank, include '
        "exactly 4 plausible options in `options`, and `correct_answer` must exactly match one option "
        "(the one that correctly fills the blank)."
    ),
    QuestionType.CODE_FIX: (
        "Set `code_language` to \"python\" (the only language the auto-grader currently runs). Write a "
        'short instruction in `text` — e.g. "Find and fix the bug in this program" or "Fill in the missing '
        'line" — describing what the student must do. '
        "IMPORTANT — the auto-grader runs both `starter_code`'s corrected form and `correct_answer` as a "
        "plain script and compares printed output, so the program MUST read its input (if any) via "
        "`input()` and MUST print its final result via `print()` — do NOT write a bare function with a "
        "`return` value and no I/O, since nothing would ever call it or show its result. "
        "Put the buggy/incomplete script the student sees in `starter_code` (a real, runnable, "
        "input()/print()-driven snippet with one clear, specific bug or one missing line — not a vague "
        "description). Put the corrected, fully working version of the SAME script in `correct_answer` "
        "— it must produce exactly the outputs listed in `test_cases` when run. Populate `test_cases` with "
        "2-4 hidden input/expected_output pairs (input is the exact text fed to the program's input() "
        "calls, one value per line if there are several; use an empty string if the program takes no "
        "input) that exercise the fixed behavior — these are used to auto-grade the student's submitted "
        "fix by running it and comparing stdout. Leave `options` empty."
    ),
}

DIFFICULTY_GUIDANCE = {
    "Easy": "Keep the question straightforward: test direct recall or a single-step "
    "application of the syllabus context, with simple wording and no multi-part reasoning.",
    "Medium": "Give the question moderate difficulty: require connecting two or more "
    "concepts from the syllabus context, not just recall.",
    "Hard": "Make the question challenging: require multi-step reasoning, synthesis "
    "across several related concepts, or applying the material to an unfamiliar scenario.",
}


def _difficulty_section(target_difficulty: str | None) -> str:
    if target_difficulty is None or target_difficulty not in DIFFICULTY_GUIDANCE:
        return ""
    return f"Target difficulty: {target_difficulty}. {DIFFICULTY_GUIDANCE[target_difficulty]}"


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


def _reference_solution_passes(question: Question) -> bool:
    """Sanity-checks a code_fix draft by running its own reference solution
    against its own test cases before it ever reaches a student — catches
    the LLM writing an inconsistent solution/test-case pair. A draft that
    fails this is dropped rather than surfaced, mirroring how a bad diagram
    or empty worksheet grid gets dropped elsewhere in this pipeline."""
    if not question.correct_answer or not question.test_cases:
        return False
    for case in question.test_cases:
        try:
            actual = run_code(question.correct_answer, case.input).strip()
        except (UnsafeCodeError, CodeTimeoutError):
            return False
        if actual != case.expected_output.strip():
            return False
    return True


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
    target_difficulty: str | None = None,
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
        difficulty_section=_difficulty_section(target_difficulty),
        type_instruction=QUESTION_TYPE_INSTRUCTIONS[question_type],
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
        question = Question(
            id=str(uuid.uuid4()),
            text=draft.text,
            question_type=draft.question_type,
            marks=draft.marks,
            bloom_level=BloomLevel[draft.bloom_level],
            topic_ids=topic_ids,
            co_ids=draft.co_codes,
            options=draft.options,
            correct_answer=draft.correct_answer,
            code_language=draft.code_language,
            starter_code=draft.starter_code,
            test_cases=draft.test_cases,
        )
        if question.question_type == QuestionType.CODE_FIX and not _reference_solution_passes(question):
            continue
        questions.append(question)

    return questions
