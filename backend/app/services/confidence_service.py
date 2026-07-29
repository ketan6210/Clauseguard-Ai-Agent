"""Build explainable evidence and review-priority scores for findings.

The combined score is an engineering index, not a calibrated probability. Each
factor is retained in the API so reviewers can inspect the calculation.
"""

import re

from app.schemas.review import Clause, Finding
from app.core.config import settings
from app.services.llm_service import verify_findings_with_qwen
from app.services.policy_store import policy_version


# These weights are versioned through settings.pipeline_version. Missing optional
# signals are removed and the remaining weights are renormalized below.
WEIGHTS = {
    "rule_strength": 0.18,
    "clause_classification": 0.10,
    "document_relevance": 0.09,
    "policy_rag_alignment": 0.07,
    "retrieval_quality": 0.07,
    "policy_deviation_support": 0.13,
    "qwen_verification": 0.12,
    "evidence_consistency": 0.08,
    "clause_specificity": 0.07,
    "extraction_quality": 0.09,
}
SEVERITY_WEIGHTS = {"Low": 0.30, "Medium": 0.55, "High": 0.80, "Critical": 1.0}


def _rule_strength(finding: Finding) -> float:
    if finding.analysis_source == "local_llm":
        return 0.55
    if finding.clause_id is None:
        return 0.9
    if finding.title.startswith("Conflicting "):
        return 0.9
    if re.search(r"\b\d+(?:\.\d+)?\b", finding.explanation):
        return 0.95
    return 0.82


def _extraction_quality(finding: Finding) -> float:
    text = finding.contract_excerpt.strip()
    if text == "No matching clause found.":
        return 0.9
    if not text:
        return 0.2
    printable_ratio = sum(character.isprintable() for character in text) / len(text)
    length_score = 0.95 if len(text) >= 80 else 0.75 if len(text) >= 35 else 0.5
    return round(min(length_score, printable_ratio), 4)


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _document_relevance(finding: Finding) -> float:
    if finding.clause_id is None:
        return 0.9
    query_tokens = _tokens(f"{finding.title} {finding.explanation}")
    clause_tokens = _tokens(finding.contract_excerpt)
    if not query_tokens or not clause_tokens:
        return 0.2
    overlap = len(query_tokens & clause_tokens) / max(1, min(len(query_tokens), 12))
    return round(min(1.0, 0.35 + overlap), 4)


def _policy_alignment(finding: Finding) -> float | None:
    """Return absolute retrieval similarity, not reciprocal-rank-fusion rank."""
    if not finding.evidence:
        return None
    return round(max(item.score for item in finding.evidence), 4)


def _retrieval_quality(finding: Finding) -> float | None:
    scores = sorted((item.score for item in finding.evidence), reverse=True)
    if not scores:
        return None
    margin = scores[0] - scores[1] if len(scores) > 1 else scores[0]
    return round(min(1.0, scores[0] * 0.75 + max(0, margin) * 0.25), 4)


def _policy_deviation_support(finding: Finding) -> float | None:
    """Estimate whether a rule establishes deviation, separately from similarity."""
    if not finding.evidence:
        return None
    if finding.clause_id is None:
        return 0.9
    explanation = finding.explanation.lower()
    if re.search(r"\b\d+(?:\.\d+)?\b", explanation) and any(
        marker in explanation
        for marker in ("exceed", "below", "outside", "more than", "less than")
    ):
        return 0.95
    return 0.78


def _clause_specificity(finding: Finding) -> float:
    text = finding.contract_excerpt
    if text == "No matching clause found.":
        return 0.9
    legal_markers = (
        "shall", "will", "must", "may", "within", "days", "hours", "liable",
        "indemn", "terminate", "warrant", "confidential", "audit",
    )
    marker_count = sum(marker in text.lower() for marker in legal_markers)
    number_bonus = 0.15 if re.search(r"\b\d+(?:\.\d+)?%?\b", text) else 0
    return round(min(1.0, 0.45 + marker_count * 0.08 + number_bonus), 4)


def _qwen_score(assessment: dict | None, finding: Finding) -> float | None:
    """Translate validated support/ambiguity into one bounded model signal."""
    if assessment:
        if (
            not assessment["supported"]
            or assessment.get("policy_stance") == "compliant"
        ):
            return 0.1
        return {"low": 0.95, "medium": 0.75, "high": 0.5}[assessment["ambiguity"]]
    if finding.analysis_source == "local_llm":
        return 0.6
    return None


def _evidence_consistency(
    finding: Finding,
    document_relevance: float,
    policy_alignment: float | None,
) -> float:
    rule_support = _rule_strength(finding)
    available = [rule_support, document_relevance]
    if policy_alignment is not None:
        available.append(policy_alignment)
    spread = max(available) - min(available)
    agreement = sum(available) / len(available) - spread * 0.25
    return round(min(1.0, max(0.0, agreement)), 4)


def score_findings(clauses: list[Clause], findings: list[Finding]) -> list[Finding]:
    """Score findings and attach transparent factors, provenance, and priority."""
    clause_map = {clause.id: clause for clause in clauses}
    assessments = verify_findings_with_qwen(findings, clauses)
    scored = []
    for finding in findings:
        clause = clause_map.get(finding.clause_id or "")
        assessment = assessments.get(finding.id)
        document_relevance = _document_relevance(finding)
        policy_alignment = _policy_alignment(finding)
        retrieval_quality = _retrieval_quality(finding)
        deviation_support = _policy_deviation_support(finding)
        qwen_score = _qwen_score(assessment, finding)
        factors: dict[str, float] = {
            "rule_strength": _rule_strength(finding),
            "clause_classification": clause.confidence if clause else 0.9,
            "document_relevance": document_relevance,
            "evidence_consistency": _evidence_consistency(
                finding, document_relevance, policy_alignment
            ),
            "clause_specificity": _clause_specificity(finding),
            "extraction_quality": _extraction_quality(finding),
        }
        optional_signals = {
            "policy_rag_alignment": policy_alignment,
            "retrieval_quality": retrieval_quality,
            "policy_deviation_support": deviation_support,
        }
        for name, value in optional_signals.items():
            if value is not None:
                factors[name] = value
        signal_status = {
            name: "available" for name in factors
        }
        for name, value in optional_signals.items():
            if value is None:
                signal_status[name] = "not_available"
        if qwen_score is not None:
            factors["qwen_verification"] = qwen_score
            signal_status["qwen_verification"] = (
                "verified" if assessment else "self_generated"
            )
        else:
            signal_status["qwen_verification"] = "not_available"
        # Do not invent neutral values for unavailable policy/model signals.
        # Renormalization ensures the visible contributions still sum to the score.
        active_weight_total = sum(WEIGHTS[name] for name in factors)
        contributions = {
            name: factors[name] * (WEIGHTS[name] / active_weight_total)
            for name in factors
        }
        score = sum(contributions.values())
        model_disagrees = bool(
            assessment
            and (
                not assessment["supported"]
                or assessment.get("policy_stance") == "compliant"
            )
        )
        if model_disagrees:
            # A model contradiction never deletes a deterministic finding. It caps
            # evidence support and explicitly routes the item to human review.
            capped_score = min(score, 0.59)
            if score > 0:
                scale = capped_score / score
                contributions = {
                    name: value * scale for name, value in contributions.items()
                }
            score = capped_score
            verification = "needs_review"
        elif finding.analysis_source == "local_llm":
            verification = "qwen_only"
        elif assessment:
            verification = "rule_and_qwen"
        else:
            verification = "rules_only"
        bounded_score = round(min(0.99, max(0.01, score)), 4)
        priority_score = round(SEVERITY_WEIGHTS[finding.risk_level] * bounded_score * 100, 1)
        if finding.risk_level == "Critical" and bounded_score < 0.70:
            # Uncertain Critical risks must not disappear below lower-impact items.
            priority_score = max(75.0, priority_score)
        priority_band = (
            "Urgent" if priority_score >= 75
            else "High" if priority_score >= 50
            else "Moderate" if priority_score >= 30
            else "Low"
        )
        scored.append(
            finding.model_copy(
                update={
                    "confidence": bounded_score,
                    "combined_score": bounded_score,
                    "priority_score": priority_score,
                    "priority_band": priority_band,
                    "confidence_factors": {
                        name: round(value, 4) for name, value in factors.items()
                    },
                    "score_contributions": {
                        name: round(value, 4) for name, value in contributions.items()
                    },
                    "signal_status": signal_status,
                    "pipeline_version": settings.pipeline_version,
                    "model_name": settings.ollama_model if settings.ollama_enabled else "",
                    "prompt_version": "finding-verification-v2",
                    "policy_version": policy_version(),
                    "retrieval_mode": (
                        "qdrant_vector_plus_lexical"
                        if settings.qdrant_enabled
                        else "lexical_fallback"
                    ),
                    "verification": verification,
                }
            )
        )
    return scored
