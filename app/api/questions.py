from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_current_teacher, require_subject
from app.core.graph_store import get_graph_store
from app.core.question_bank import get_question_bank
from app.schemas.bloom import BloomLevel
from app.schemas.course_outcome import CourseOutcome
from app.schemas.difficulty import DifficultyScore
from app.schemas.duplicate import DuplicateMatch
from app.schemas.grading import GradeResult
from app.schemas.question import Question, QuestionType
from app.schemas.teacher import Teacher
from app.services.difficulty_scoring import score_difficulty
from app.services.duplicate_detection import find_duplicates
from app.services.grading import AUTO_GRADABLE_TYPES, grade_answer
from app.services.question_generation import generate_questions

router = APIRouter(prefix="/api/v1/questions", tags=["questions"], dependencies=[Depends(get_current_teacher)])


class GenerateQuestionsRequest(BaseModel):
    subject_id: str
    topic: str
    num_questions: int = 3
    bloom_level: BloomLevel = BloomLevel.UNDERSTAND
    marks: int = 5
    question_type: QuestionType = QuestionType.SHORT_ANSWER
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
def generate(request: GenerateQuestionsRequest, teacher: Teacher = Depends(get_current_teacher)) -> GenerateQuestionsResponse:
    """RAG-generate questions for a topic, score their difficulty, and flag duplicates
    against the existing question bank. Defaults to a preview (not saved) — pass
    save_to_bank=true, or POST the chosen question(s) to /questions afterward."""
    require_subject(request.subject_id, teacher)
    graph_store = get_graph_store(request.subject_id)
    bank = get_question_bank(request.subject_id)

    questions = generate_questions(
        topic=request.topic,
        graph_store=graph_store,
        subject_id=request.subject_id,
        num_questions=request.num_questions,
        bloom_level=request.bloom_level,
        marks=request.marks,
        question_type=request.question_type,
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
    subject_id: str
    question: Question
    threshold: float = 0.75


class CheckDuplicatesResponse(BaseModel):
    matches: list[DuplicateMatch]


@router.post("/check-duplicates", response_model=CheckDuplicatesResponse)
def check_duplicates(request: CheckDuplicatesRequest, teacher: Teacher = Depends(get_current_teacher)) -> CheckDuplicatesResponse:
    require_subject(request.subject_id, teacher)
    bank = get_question_bank(request.subject_id)
    matches = find_duplicates(request.question, bank.list(), threshold=request.threshold)
    return CheckDuplicatesResponse(matches=matches)


@router.get("", response_model=list[Question])
def list_questions(subject_id: str, teacher: Teacher = Depends(get_current_teacher)) -> list[Question]:
    require_subject(subject_id, teacher)
    return get_question_bank(subject_id).list()


@router.post("", response_model=Question)
def save_question(subject_id: str, question: Question, teacher: Teacher = Depends(get_current_teacher)) -> Question:
    """Persist a question the user has reviewed (e.g. a generation preview they approved)."""
    require_subject(subject_id, teacher)
    get_question_bank(subject_id).add(question)
    return question


@router.delete("/{question_id}")
def delete_question(question_id: str, subject_id: str, teacher: Teacher = Depends(get_current_teacher)) -> dict:
    require_subject(subject_id, teacher)
    if not get_question_bank(subject_id).remove(question_id):
        raise HTTPException(status_code=404, detail="Question not found")
    return {"deleted": question_id}


class GradeAnswerRequest(BaseModel):
    subject_id: str
    answer: str


@router.post("/{question_id}/grade", response_model=GradeResult)
def grade_question_answer(
    question_id: str, request: GradeAnswerRequest, teacher: Teacher = Depends(get_current_teacher)
) -> GradeResult:
    """Auto-grades a submitted answer against this question. For code_fix,
    runs the submission in a sandbox against the question's hidden test
    cases; for mcq/fill_in_blank/numerical, does an exact-match check.
    short_answer/long_answer aren't auto-gradable and return 400."""
    require_subject(request.subject_id, teacher)
    question = get_question_bank(request.subject_id).get(question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found")
    if question.question_type not in AUTO_GRADABLE_TYPES:
        raise HTTPException(status_code=400, detail=f"{question.question_type.value} questions require manual grading")
    return grade_answer(question, request.answer)
