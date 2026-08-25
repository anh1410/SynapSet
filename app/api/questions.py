from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_current_teacher
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

router = APIRouter(prefix="/api/v1/questions", tags=["questions"], dependencies=[Depends(get_current_teacher)])

DifficultyBucket = Literal["Easy", "Medium", "Hard"]


class GenerateQuestionsRequest(BaseModel):
    topic: str
    num_questions: int = 3
    bloom_level: BloomLevel = BloomLevel.UNDERSTAND
    marks: int = 5
    question_type: QuestionType = QuestionType.SHORT_ANSWER
    target_difficulty: DifficultyBucket | None = None
    course_outcomes: list[CourseOutcome] | None = None
    check_duplicates: bool = True
    save_to_bank: bool = False


class GeneratedQuestionResult(BaseModel):
    question: Question
    difficulty: DifficultyScore
    duplicate_matches: list[DuplicateMatch] = []


class GenerateQuestionsResponse(BaseModel):
    results: list[GeneratedQuestionResult]


@router.post("/generate", response_model=GenerateQuestionsResponse)
def generate(request: GenerateQuestionsRequest) -> GenerateQuestionsResponse:
    """RAG-generate questions for a topic, score their difficulty, and flag duplicates
    against the existing question bank. Defaults to a preview (not saved) — pass
    save_to_bank=true, or POST the chosen question(s) to /questions afterward."""
    graph_store = get_graph_store()
    bank = get_question_bank()

    questions = generate_questions(
        topic=request.topic,
        graph_store=graph_store,
        num_questions=request.num_questions,
        bloom_level=request.bloom_level,
        marks=request.marks,
        question_type=request.question_type,
        target_difficulty=request.target_difficulty,
        course_outcomes=request.course_outcomes,
    )

    results = []
    for q in questions:
        difficulty = score_difficulty(q, graph_store)
        q.difficulty_score = difficulty.score
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


@router.post("", response_model=Question)
def save_question(question: Question) -> Question:
    """Persist a question the user has reviewed (e.g. a generation preview they approved)."""
    get_question_bank().add(question)
    return question


@router.delete("/{question_id}")
def delete_question(question_id: str) -> dict:
    if not get_question_bank().remove(question_id):
        raise HTTPException(status_code=404, detail="Question not found")
    return {"deleted": question_id}
