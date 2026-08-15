from fastapi import APIRouter
from pydantic import BaseModel

from app.core.graph_store import get_graph_store
from app.core.question_bank import get_question_bank
from app.schemas.bloom import BloomLevel
from app.schemas.course_outcome import CourseOutcome
from app.schemas.difficulty import DifficultyScore
from app.schemas.duplicate import DuplicateMatch
from app.schemas.question import Question, QuestionType
from app.services.difficulty_scoring import score_difficulty
from app.services.duplicate_detection import find_duplicates
from app.services.question_generation import generate_questions

router = APIRouter(prefix="/api/v1/questions", tags=["questions"])


class GenerateQuestionsRequest(BaseModel):
    topic: str
    num_questions: int = 3
    bloom_level: BloomLevel = BloomLevel.UNDERSTAND
    marks: int = 5
    question_type: QuestionType = QuestionType.SHORT_ANSWER
    course_outcomes: list[CourseOutcome] | None = None
    check_duplicates: bool = True
    save_to_bank: bool = True


class GeneratedQuestionResult(BaseModel):
    question: Question
    difficulty: DifficultyScore
    duplicate_matches: list[DuplicateMatch] = []


class GenerateQuestionsResponse(BaseModel):
    results: list[GeneratedQuestionResult]


@router.post("/generate", response_model=GenerateQuestionsResponse)
def generate(request: GenerateQuestionsRequest) -> GenerateQuestionsResponse:
    """RAG-generate questions for a topic, score their difficulty, and flag duplicates
    against the existing question bank."""
    graph_store = get_graph_store()
    bank = get_question_bank()

    questions = generate_questions(
        topic=request.topic,
        graph_store=graph_store,
        num_questions=request.num_questions,
        bloom_level=request.bloom_level,
        marks=request.marks,
        question_type=request.question_type,
        course_outcomes=request.course_outcomes,
    )

    results = []
    for q in questions:
        difficulty = score_difficulty(q, graph_store)
        matches = find_duplicates(q, bank.list()) if request.check_duplicates else []
        results.append(GeneratedQuestionResult(question=q, difficulty=difficulty, duplicate_matches=matches))
        if request.save_to_bank:
            bank.add(q)

    return GenerateQuestionsResponse(results=results)


class CheckDuplicatesRequest(BaseModel):
    question: Question
    threshold: float = 0.75


class CheckDuplicatesResponse(BaseModel):
    matches: list[DuplicateMatch]


@router.post("/check-duplicates", response_model=CheckDuplicatesResponse)
def check_duplicates(request: CheckDuplicatesRequest) -> CheckDuplicatesResponse:
    bank = get_question_bank()
    matches = find_duplicates(request.question, bank.list(), threshold=request.threshold)
    return CheckDuplicatesResponse(matches=matches)


@router.get("", response_model=list[Question])
def list_questions() -> list[Question]:
    return get_question_bank().list()
