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
from app.schemas.question import CODING_TYPES, CodeTestCase, Question, QuestionProvenance, QuestionType, SourceChunk
from app.services.code_sandbox import (
    ALLOWED_IMPORTS,
    CodeTimeoutError,
    UnsafeCodeError,
    normalize_output,
    outputs_match,
    run_code,
)
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

FORMAT RULES for {question_type}: {type_instruction}
{style_instruction}{feedback}
- Ground every question in the syllabus context provided.
- Tag each question with the topic names it covers (topic_names): include "{topic}" and any related \
topics from the list above that the question actually draws on.
- If Course Outcomes were given, tag applicable co_codes; otherwise leave co_codes empty.
"""

# The auto-grader's sandbox (app/services/code_sandbox.py) rejects code that
# breaks these rules, so every reference solution and starter program must
# follow them or the draft fails its own check and is dropped.
SANDBOX_RULES = (
    " SANDBOX RULES for every program you write (starter_code and correct_answer): read input ONLY with "
    "`input()` - never `sys.stdin`; you may import ONLY these modules: "
    + ", ".join(sorted(ALLOWED_IMPORTS))
    + "; do NOT use the words os, sys, subprocess, open, eval, exec, compile, globals, locals or vars anywhere "
    "in the code, not even inside strings or comments; do NOT wrap the code in `if __name__ == \"__main__\":` "
    "(it would never run) - write a plain top-level script."
)

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
    ) + SANDBOX_RULES,
    QuestionType.CODE_WRITE: (
        "Set `code_language` to \"python\" (the only language the auto-grader currently runs). The student "
        "writes the WHOLE program themselves. Put a complete problem statement in `text`: what the program "
        "must do, an **Input format** section, an **Output format** section, any constraints, and one worked "
        "example (sample input and sample output). The program MUST read its input via `input()` (one value "
        "or line per `input()` call, exactly as the input format says) and MUST print its result via "
        "`print()` - no bare functions with a `return` value only. Put a correct, complete reference program "
        "in `correct_answer`; it must produce exactly the expected outputs of `test_cases`. Leave "
        "`starter_code` empty (or at most a 1-2 line input-reading skeleton). Populate `test_cases` with 3-5 "
        "hidden input/expected_output pairs (input is the exact text fed to input(), one value per line; "
        "expected_output is exactly what the reference program prints) covering normal cases and at least "
        "one edge case. Leave `options` empty."
    ) + SANDBOX_RULES,
}

# Extra instruction appended for code_write questions asked to be scenario-based.
SCENARIO_INSTRUCTION = (
    "STYLE: interview / industry scenario. Frame the problem the way a technical interview at a "
    "software company would: a short, realistic business scenario (e.g. an e-commerce order queue, a "
    "ride-sharing dispatcher, a bank transaction log, a library system, a delivery route planner) that the "
    "student must translate into the algorithm or data structure for this topic. Keep the scenario "
    "concrete, state exactly what the program reads and prints, and keep it solvable in an exam. Even in "
    "this style the reference program reads every line with input() (first line = count, then a loop) - "
    "never sys.stdin."
)


def _context_hits(topic: str, subject_id: str, n_chunks: int = 5) -> list[dict]:
    return query_similar_chunks(topic, subject_id, n_results=n_chunks)


def _context_text(hits: list[dict]) -> str:
    if not hits:
        return "(no indexed syllabus content found for this topic)"
    return "\n\n".join(f"[{h['metadata'].get('source_document')}] {h['text']}" for h in hits)


def graph_relation_lines(topic: str, graph_store: KnowledgeGraphStore) -> list[str]:
    """Prerequisite / course-outcome relations touching a topic, as readable lines."""
    graph = graph_store.graph
    node_id = normalize_topic_name(topic)
    if node_id not in graph:
        return []
    lines: list[str] = []
    for pred in graph.predecessors(node_id):
        rel = graph.edges[pred, node_id].get("relation_type")
        lines.append(f"- {graph.nodes[pred].get('name', pred)} --[{rel}]--> {topic}")
    for succ in graph.successors(node_id):
        rel = graph.edges[node_id, succ].get("relation_type")
        lines.append(f"- {topic} --[{rel}]--> {graph.nodes[succ].get('name', succ)}")
    return lines


def _related_topics_text(topic: str, graph_store: KnowledgeGraphStore) -> str:
    if normalize_topic_name(topic) not in graph_store.graph:
        return "(topic not found in knowledge graph)"
    lines = graph_relation_lines(topic, graph_store)
    return "\n".join(lines) if lines else "(no direct relations found)"


def chunks_from_hits(hits: list[dict], excerpt_chars: int = 600) -> list[SourceChunk]:
    return [
        SourceChunk(
            source_document=h["metadata"].get("source_document"),
            chunk_index=h["metadata"].get("chunk_index"),
            excerpt=h["text"][:excerpt_chars],
            relevance=round(1 - h["distance"], 3) if h.get("distance") is not None else None,
        )
        for h in hits
    ]


def _co_section(course_outcomes: list[CourseOutcome] | None) -> str:
    if not course_outcomes:
        return ""
    listed = "\n".join(f"- {co.code}: {co.description}" for co in course_outcomes)
    return f"COURSE OUTCOMES (tag co_codes from this list only):\n{listed}\n"


def _reference_solution_problem(question: Question) -> str | None:
    """Sanity-checks a coding draft (code_fix / code_write) before it ever
    reaches a student, and settles its test cases.

    The reference solution is run on every test input. The model works out
    expected outputs in its head and often slips on some, so the outputs the
    graded tests use are the ones the solution actually prints. As an anchor
    that the solution really implements the task the model described, at
    least one of the model's own expected outputs must agree with the run.
    A draft whose solution errors, prints nothing, or never agrees with the
    model is dropped rather than surfaced.

    Returns None when the draft is usable (test cases settled in place), else
    a short reason - fed back into the next attempt's prompt."""
    if not question.correct_answer or not question.test_cases:
        return "the reference solution (correct_answer) or the test_cases were missing"
    settled: list[CodeTestCase] = []
    agreed = 0
    for case in question.test_cases:
        try:
            actual = normalize_output(run_code(question.correct_answer, case.input))
        except (UnsafeCodeError, CodeTimeoutError) as exc:
            return f"the auto-grader could not run the reference solution: {exc}"
        if not actual:
            return f"the reference solution printed nothing for input {case.input!r}"
        agreed += outputs_match(actual, case.expected_output)
        settled.append(CodeTestCase(input=case.input, expected_output=actual))
    if not agreed:
        return "the reference solution's output matched none of the expected outputs in test_cases"
    question.test_cases = settled
    return None


def generate_questions(
    topic: str,
    graph_store: KnowledgeGraphStore,
    subject_id: str,
    num_questions: int = 3,
    bloom_level: BloomLevel = BloomLevel.UNDERSTAND,
    marks: int = 5,
    question_type: QuestionType = QuestionType.SHORT_ANSWER,
    course_outcomes: list[CourseOutcome] | None = None,
    scenario_based: bool = False,
) -> list[Question]:
    """Generate exam questions for a topic, grounded in retrieved syllabus context
    and augmented with the topic's prerequisite/CO relationships from the knowledge graph.
    `scenario_based` (code_write only) frames the problem as an interview-style scenario.

    Coding drafts (code_fix / code_write) that fail their own reference-solution check (see
    _reference_solution_problem) are dropped by _generate_questions_once. For a
    single-question request that means one bad LLM draft returns nothing at
    all, so retry the whole generation call a couple of times in that specific
    case rather than surfacing "no question returned" to the teacher - telling
    the model each time why its previous draft was rejected.
    """
    attempts = 3 if question_type in CODING_TYPES else 1
    questions: list[Question] = []
    rejections: list[str] = []
    for _ in range(attempts):
        questions = _generate_questions_once(
            topic=topic,
            graph_store=graph_store,
            subject_id=subject_id,
            num_questions=num_questions,
            bloom_level=bloom_level,
            marks=marks,
            question_type=question_type,
            course_outcomes=course_outcomes,
            scenario_based=scenario_based and question_type == QuestionType.CODE_WRITE,
            rejections=rejections,
        )
        if questions:
            break
    return questions


@retry(
    retry=retry_if_exception_type((errors.ServerError, errors.APIError, httpx.TransportError)),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    reraise=True,
)
def _generate_questions_once(
    topic: str,
    graph_store: KnowledgeGraphStore,
    subject_id: str,
    num_questions: int,
    bloom_level: BloomLevel,
    marks: int,
    question_type: QuestionType,
    course_outcomes: list[CourseOutcome] | None,
    scenario_based: bool = False,
    rejections: list[str] | None = None,
) -> list[Question]:
    """One generation call. `rejections` collects why coding drafts were
    rejected (and earlier reasons are shown to the model in the prompt)."""
    settings = get_settings()
    client = get_genai_client()

    hits = _context_hits(topic, subject_id)
    relations = graph_relation_lines(topic, graph_store)
    prompt = GENERATION_PROMPT.format(
        topic=topic,
        context=_context_text(hits),
        related_topics=_related_topics_text(topic, graph_store),
        co_section=_co_section(course_outcomes),
        num_questions=num_questions,
        question_type=question_type.value,
        bloom_level=bloom_level.name,
        marks=marks,
        type_instruction=QUESTION_TYPE_INSTRUCTIONS[question_type],
        style_instruction=f"{SCENARIO_INSTRUCTION}\n" if scenario_based else "",
        feedback=(
            "PREVIOUS ATTEMPT REJECTED - fix this: " + "; ".join(dict.fromkeys(rejections)) + "\n"
            if rejections else ""
        ),
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
    provenance = QuestionProvenance(
        requested_topic=topic,
        retrieved_chunks=chunks_from_hits(hits),
        graph_relations=[line.removeprefix("- ") for line in relations],
        model=settings.generation_model,
    )
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
            co_ids=list(dict.fromkeys(draft.co_codes)),  # the model sometimes repeats a CO
            options=draft.options,
            correct_answer=draft.correct_answer,
            code_language=draft.code_language,
            starter_code=draft.starter_code,
            test_cases=draft.test_cases,
            scenario_based=scenario_based and draft.question_type == QuestionType.CODE_WRITE,
            origin="generated",
            provenance=provenance,
            source_document=provenance.retrieved_chunks[0].source_document if provenance.retrieved_chunks else None,
        )
        if question.question_type in CODING_TYPES:
            problem = _reference_solution_problem(question)
            if problem:
                if rejections is not None:
                    rejections.append(problem)
                continue
        questions.append(question)

    return questions
