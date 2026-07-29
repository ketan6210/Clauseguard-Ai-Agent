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
    analysis_source: Literal["rules", "local_llm"] = "rules"
    verification: Literal[
        "rules_only", "rule_and_qwen", "qwen_only", "needs_review"
    ] = "rules_only"
    combined_score: float = Field(default=0.5, ge=0, le=1)
    priority_score: float = Field(default=0, ge=0, le=100)
    priority_band: Literal["Low", "Moderate", "High", "Urgent"] = "Low"
    confidence_factors: dict[str, float] = Field(default_factory=dict)
    score_contributions: dict[str, float] = Field(default_factory=dict)
    signal_status: dict[str, str] = Field(default_factory=dict)
    pipeline_version: str = "legacy"
    model_name: str = ""
    prompt_version: str = ""
    policy_version: str = ""
    retrieval_mode: str = ""


class ReviewMetrics(BaseModel):
    overall_risk_score: float = Field(ge=0, le=100)
    overall_risk_band: Literal["Low", "Moderate", "High", "Critical"]
    pipeline_quality_score: float = Field(ge=0, le=100)
    evidence_health_score: float = Field(ge=0, le=100)
    severity_counts: dict[str, int]
    verification_counts: dict[str, int]
    evidence_bands: dict[str, int]
    policy_coverage: float = Field(ge=0, le=1)
    qwen_verification_coverage: float = Field(ge=0, le=1)
    qwen_assessment_coverage: float = Field(ge=0, le=1)
    pending_human_review: int
    risk_score_factors: dict[str, float]


class ReviewResponse(BaseModel):
    review_id: str
    filename: str
    contract_type: str
    summary: str
    clauses: list[Clause]
    findings: list[Finding]
    metrics: ReviewMetrics


class QuestionRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000)


class QuestionResponse(BaseModel):
    answer: str
    citations: list[Evidence]
    contract_citations: list[Evidence] = []
    policy_citations: list[Evidence] = []
    generation_mode: Literal["local_llm", "extractive_fallback"] = "extractive_fallback"


class DecisionRequest(BaseModel):
    finding_id: str
    decision: Literal["approved", "rejected"]
    comment: str = Field(default="", max_length=2000)


class DecisionResponse(BaseModel):
    finding_id: str
    status: str


class ValidationRequest(BaseModel):
    finding_id: str
    label: Literal["valid", "invalid", "uncertain"]


class ValidationResponse(BaseModel):
    finding_id: str
    label: str
    pipeline_version: str
