from typing import Literal

from pydantic import BaseModel, Field


class DocumentPage(BaseModel):
    page_number: int
    text: str


class Clause(BaseModel):
    id: str
    clause_type: str
    text: str
    page: int = 1
    confidence: float = Field(ge=0, le=1)


class Evidence(BaseModel):
    source_id: str
    title: str
    section: str
    text: str
    score: float


class Finding(BaseModel):
    id: str
    clause_id: str | None = None
    title: str
    risk_level: Literal["Low", "Medium", "High", "Critical"]
    confidence: float = Field(ge=0, le=1)
    explanation: str
    recommended_action: str
    contract_excerpt: str
    evidence: list[Evidence] = []
    status: Literal["pending", "approved", "rejected"] = "pending"


class ReviewResponse(BaseModel):
    review_id: str
    filename: str
    contract_type: str
    summary: str
    clauses: list[Clause]
    findings: list[Finding]


class QuestionRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000)


class QuestionResponse(BaseModel):
    answer: str
    citations: list[Evidence]


class DecisionRequest(BaseModel):
    finding_id: str
    decision: Literal["approved", "rejected"]
    comment: str = Field(default="", max_length=2000)


class DecisionResponse(BaseModel):
    finding_id: str
    status: str
