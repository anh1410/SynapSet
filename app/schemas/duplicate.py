from pydantic import BaseModel


class DuplicateMatch(BaseModel):
    existing_question_id: str
    semantic_score: float
    graph_score: float
    structural_score: float
    final_score: float
    is_duplicate: bool
