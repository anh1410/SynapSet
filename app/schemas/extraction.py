from typing import Literal

from pydantic import BaseModel, Field


class ExtractedTopic(BaseModel):
    name: str
    description: str = Field(default="", description="One-sentence summary of the topic")


class ExtractedRelation(BaseModel):
    source: str = Field(description="Name of the source topic")
    target: str = Field(description="Name of the target topic, concept, or CO code")
    relation_type: Literal["PREREQUISITE_OF", "MAPS_TO"]


class ExtractionResult(BaseModel):
    topics: list[ExtractedTopic] = Field(default_factory=list)
    relations: list[ExtractedRelation] = Field(default_factory=list)
