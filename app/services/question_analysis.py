"""Classify a question the teacher wrote themselves.

The teacher supplies the question (and, depending on its type, options /
answer / starter code / reference solution / test cases); this works out the
rest so it can join the bank like a generated question:

- Bloom's level with a one-line rationale, the knowledge-graph topics and
  course outcomes it assesses, a suggested question type and marks - from
  Gemini, constrained to the subject's own topic and CO lists;
- difficulty from the local XGBoost model, skill category, and near-duplicates
  already in the bank (both local);
- for coding questions: the reference solution is run against the teacher's
  test cases, and suggested test cases are produced by running the reference
  solution on AI-proposed inputs (expected outputs are never taken from the
  model).

If Gemini can't be reached, a keyword heuristic classifies the question
instead (`method="heuristic"`), so the feature still works offline.
"""

import logging
import re
from typing import Literal

from google.genai import types
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.graph_store import KnowledgeGraphStore, course_outcome_node_ids, normalize_topic_name
from app.core.llm import get_genai_client
from app.schemas.bloom import BloomLevel
from app.schemas.difficulty import DifficultyScore
from app.schemas.duplicate import DuplicateMatch
from app.schemas.generation import BloomLevelName
from app.schemas.grading import TestCaseResult
from app.schemas.question import CODING_TYPES, CodeTestCase, Question, QuestionType
from app.schemas.skill import SkillCategory
from app.services.code_sandbox import CodeTimeoutError, UnsafeCodeError, normalize_output, outputs_match, run_code
from app.services.difficulty_scoring import score_difficulty
from app.services.duplicate_detection import find_duplicates

logger = logging.getLogger(__name__)

MAX_SUGGESTED_TESTS = 5
MAX_TOPICS = 3  # the prompt asks for 1-3; the model sometimes returns more


class QuestionAnalysisDraft(BaseModel):
    """Structured output requested from Gemini."""

    question_type: QuestionType
    bloom_level: BloomLevelName
    bloom_rationale: str
    topic_names: list[str] = Field(default_factory=list)
    co_codes: list[str] = Field(default_factory=list)
    suggested_marks: int
    test_inputs: list[str] = Field(default_factory=list)


class CodeCheck(BaseModel):
    """The reference solution run against the teacher's own test cases."""

    passed: int
    total: int
    results: list[TestCaseResult]


class QuestionAnalysis(BaseModel):
    method: Literal["ai", "heuristic"]
    note: str | None = None  # why the heuristic was used, or other caveats
    question_type: QuestionType
    bloom_level: BloomLevel
    bloom_rationale: str
    topic_ids: list[str]
    co_ids: list[str]
    suggested_marks: int
    skill_category: SkillCategory
    difficulty: DifficultyScore
    duplicate_matches: list[DuplicateMatch] = Field(default_factory=list)
    suggested_test_cases: list[CodeTestCase] = Field(default_factory=list)
    code_check: CodeCheck | None = None


class QuestionInput(BaseModel):
    """What the teacher wrote. Only `text` is required."""

    text: str
    question_type: QuestionType | None = None  # None = let the AI choose
    options: list[str] | None = None
    correct_answer: str | None = None
    code_language: str | None = None
    starter_code: str | None = None
    test_cases: list[CodeTestCase] | None = None
    marks: int | None = None
    scenario_based: bool = False


ANALYSIS_PROMPT = """You are an expert in Bloom's Revised Taxonomy and university assessment design. \
A teacher wrote the exam question below. Classify it.

QUESTION TYPE: {qtype}
QUESTION:
{text}
{extra}
COURSE TOPICS (choose topic_names ONLY from this list - the 1 to 3 topics the question actually assesses):
{topics}

COURSE OUTCOMES (choose co_codes ONLY from this list; leave empty if none clearly applies):
{cos}

Rules:
- bloom_level is the cognitive process a student must use to answer, judged by the verb AND by what the task \
really requires: REMEMBER (recall facts/definitions), UNDERSTAND (explain, describe, classify, summarise), \
APPLY (use a known procedure on a new case, compute, trace, implement a standard algorithm), ANALYZE (compare, \
debug, find the cause, break down, distinguish), EVALUATE (judge, justify, critique, choose with criteria), \
CREATE (design or compose a new solution, system or plan). Examples: "find and fix the bug" = ANALYZE; \
"write a program that implements binary search" = APPLY; "design a system for this scenario" = CREATE.
- bloom_rationale: one short sentence explaining the level, quoting the key verb or task.
- question_type: {type_rule}
- suggested_marks: typical marks in a university exam (1-2 objective, 2-5 short or numerical, 5-10 coding, \
8-15 long answer).
- test_inputs: ONLY for code_fix / code_write questions: 3-5 inputs exactly as fed to the program's input() \
calls (one value per line), covering normal and edge cases. Otherwise leave empty.
"""

TYPE_CHOICES = ", ".join(t.value for t in QuestionType)

# Heuristic fallback: strongest verbs first.
_BLOOM_VERBS: list[tuple[BloomLevel, tuple[str, ...]]] = [
    (BloomLevel.CREATE, ("design", "create", "compose", "construct", "devise", "formulate", "propose", "invent", "plan")),
    (BloomLevel.EVALUATE, ("evaluate", "justify", "critique", "assess", "judge", "argue", "defend", "recommend", "which is better")),
    (BloomLevel.ANALYZE, ("analyse", "analyze", "compare", "contrast", "differentiate", "distinguish", "debug", "fix", "examine", "why does")),
    (BloomLevel.APPLY, ("apply", "calculate", "compute", "solve", "implement", "write a program", "write code", "trace", "use", "determine", "evaluate the")),
    (BloomLevel.UNDERSTAND, ("explain", "describe", "summarise", "summarize", "classify", "discuss", "illustrate", "interpret", "what happens")),
    (BloomLevel.REMEMBER, ("define", "list", "name", "state", "identify", "recall", "what is", "which", "who")),
]
_DEFAULT_MARKS = {
    QuestionType.MCQ: 1, QuestionType.FILL_IN_BLANK: 1, QuestionType.NUMERICAL: 2, QuestionType.SHORT_ANSWER: 4,
    QuestionType.LONG_ANSWER: 10, QuestionType.CODE_FIX: 5, QuestionType.CODE_WRITE: 8,
}


def _topic_names(graph_store: KnowledgeGraphStore) -> tuple[dict[str, str], dict[str, str]]:
    """({topic_id: name}, {co_code: description}) for this subject's graph."""
    graph = graph_store.graph
    cos = course_outcome_node_ids(graph)
    topics = {n: d.get("name", n) for n, d in graph.nodes(data=True) if n not in cos}
    outcomes = {graph.nodes[c].get("name", c): graph.nodes[c].get("description", "") for c in cos}
    return topics, outcomes


def _extra_section(q: QuestionInput) -> str:
    parts = []
    if q.options:
        parts.append("OPTIONS:\n" + "\n".join(f"- {o}" for o in q.options))
    if q.correct_answer and (q.question_type not in CODING_TYPES):
        parts.append(f"ANSWER / KEY POINTS:\n{q.correct_answer}")
    if q.starter_code:
        parts.append(f"CODE GIVEN TO THE STUDENT:\n{q.starter_code}")
    if q.correct_answer and q.question_type in CODING_TYPES:
        parts.append(f"REFERENCE SOLUTION:\n{q.correct_answer}")
    if q.scenario_based:
        parts.append("(The teacher framed this as an interview / real-world scenario problem.)")
    return ("\n" + "\n\n".join(parts) + "\n") if parts else ""


def _ask_gemini(q: QuestionInput, topics: dict[str, str], outcomes: dict[str, str]) -> QuestionAnalysisDraft | None:
    settings = get_settings()
    prompt = ANALYSIS_PROMPT.format(
        qtype=q.question_type.value if q.question_type else "auto (not given)",
        text=q.text.strip(),
        extra=_extra_section(q),
        topics="\n".join(f"- {name}" for name in topics.values()) or "(no topics in this subject's knowledge graph yet)",
        cos="\n".join(f"- {code}: {desc}" for code, desc in outcomes.items()) or "(none)",
        type_rule=(f'the teacher chose "{q.question_type.value}" - return exactly that.' if q.question_type
                   else f"choose the best fit from: {TYPE_CHOICES}."),
    )
    response = get_genai_client().models.generate_content(
        model=settings.generation_model,
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=QuestionAnalysisDraft),
    )
    return response.parsed


def _heuristic(q: QuestionInput, topics: dict[str, str]) -> QuestionAnalysisDraft:
    text = q.text.lower()
    qtype = q.question_type or _guess_type(q)
    bloom, verb = BloomLevel.UNDERSTAND, None
    for level, verbs in _BLOOM_VERBS:
        hit = next((v for v in verbs if re.search(rf"\b{re.escape(v)}\b", text)), None)
        if hit:
            bloom, verb = level, hit
            break
    if qtype == QuestionType.CODE_FIX and bloom < BloomLevel.ANALYZE:
        bloom, verb = BloomLevel.ANALYZE, verb or "fix the code"
    if qtype == QuestionType.CODE_WRITE and bloom < BloomLevel.APPLY:
        bloom, verb = BloomLevel.APPLY, verb or "write the program"
    words = re.findall(r"[a-z0-9]+", text)
    matched = [name for name in topics.values() if _mentions(name, words)]
    rationale = f'Keyword match on "{verb}".' if verb else "No clear task verb; defaulted to Understand."
    return QuestionAnalysisDraft(
        question_type=qtype, bloom_level=bloom.name, bloom_rationale=rationale, topic_names=matched[:3],
        co_codes=[], suggested_marks=_DEFAULT_MARKS[qtype],
    )


def _stem(word: str) -> str:
    return re.sub(r"(ing|es|s)$", "", word) if len(word) > 4 else word


def _mentions(topic_name: str, words: list[str]) -> bool:
    """Every significant word of the topic appears in the text, allowing simple
    inflections ("Sorting" ~ "sort", "Linked Lists" ~ "linked list")."""
    stems = {_stem(w) for w in words}
    parts = [_stem(p) for p in re.findall(r"[a-z0-9]+", topic_name.lower()) if len(p) > 2]
    return bool(parts) and all(any(s.startswith(p) or (p.startswith(s) and len(s) > 3) for s in stems) for p in parts)


def _guess_type(q: QuestionInput) -> QuestionType:
    if q.starter_code:
        return QuestionType.CODE_FIX
    if q.test_cases or re.search(r"\bwrite (a|the) (program|function|code)\b", q.text.lower()):
        return QuestionType.CODE_WRITE
    if q.options:
        return QuestionType.FILL_IN_BLANK if "___" in q.text else QuestionType.MCQ
    if q.correct_answer and re.fullmatch(r"-?\d+(\.\d+)?", q.correct_answer.strip()):
        return QuestionType.NUMERICAL
    return QuestionType.LONG_ANSWER if len(q.text) > 250 else QuestionType.SHORT_ANSWER


def _run_reference(solution: str, stdin: str) -> tuple[str | None, str | None]:
    try:
        return normalize_output(run_code(solution, stdin)), None
    except (UnsafeCodeError, CodeTimeoutError) as exc:
        return None, str(exc)


def check_reference_solution(solution: str, cases: list[CodeTestCase]) -> CodeCheck:
    results = []
    for case in cases:
        actual, error = _run_reference(solution, case.input)
        results.append(TestCaseResult(
            input=case.input, expected_output=case.expected_output, actual_output=actual or "",
            passed=error is None and outputs_match(actual or "", case.expected_output), error=error,
        ))
    return CodeCheck(passed=sum(r.passed for r in results), total=len(results), results=results)


def suggest_test_cases(solution: str, inputs: list[str]) -> list[CodeTestCase]:
    """Expected outputs come from actually running the reference solution."""
    suggested: list[CodeTestCase] = []
    for stdin in inputs[:MAX_SUGGESTED_TESTS]:
        stdin = stdin if stdin.endswith("\n") or not stdin else stdin + "\n"
        actual, error = _run_reference(solution, stdin)
        if error is None and actual is not None:
            suggested.append(CodeTestCase(input=stdin, expected_output=actual))
    return suggested


def analyze_question(q: QuestionInput, graph_store: KnowledgeGraphStore, bank: list[Question]) -> QuestionAnalysis:
    topics, outcomes = _topic_names(graph_store)
    method: Literal["ai", "heuristic"] = "ai"
    note = None
    draft = None
    try:
        draft = _ask_gemini(q, topics, outcomes)
    except Exception as exc:  # no key, quota, network, bad response: degrade, don't fail the form
        logger.warning("Question analysis fell back to heuristics: %s", exc)
        note = "The AI service couldn't be reached, so the classification uses keyword rules - please double-check it."
    if draft is None:
        method = "heuristic"
        note = note or "The AI returned no classification, so keyword rules were used - please double-check it."
        draft = _heuristic(q, topics)

    qtype = q.question_type or draft.question_type
    name_to_id = {normalize_topic_name(name): tid for tid, name in topics.items()}
    topic_ids = list(dict.fromkeys(tid for n in draft.topic_names if (tid := name_to_id.get(normalize_topic_name(n)))))[:MAX_TOPICS]
    co_ids = list(dict.fromkeys(c for c in draft.co_codes if c in outcomes))
    marks = q.marks or max(1, draft.suggested_marks)
    bloom = BloomLevel[draft.bloom_level]

    candidate = Question(
        id="__analysis__", text=q.text, question_type=qtype, marks=marks, bloom_level=bloom,
        topic_ids=topic_ids, co_ids=co_ids, options=q.options, correct_answer=q.correct_answer,
        code_language=q.code_language, starter_code=q.starter_code, test_cases=q.test_cases,
        scenario_based=q.scenario_based,
    )
    analysis = QuestionAnalysis(
        method=method, note=note, question_type=qtype, bloom_level=bloom, bloom_rationale=draft.bloom_rationale,
        topic_ids=topic_ids, co_ids=co_ids, suggested_marks=marks,
        skill_category=candidate.effective_skill_category,
        difficulty=score_difficulty(candidate, graph_store),
        duplicate_matches=find_duplicates(candidate, bank),
    )
    if qtype in CODING_TYPES and q.correct_answer:
        if q.test_cases:
            analysis.code_check = check_reference_solution(q.correct_answer, q.test_cases)
        if draft.test_inputs:
            analysis.suggested_test_cases = suggest_test_cases(q.correct_answer, draft.test_inputs)
    return analysis
