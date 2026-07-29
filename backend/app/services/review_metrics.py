"""Aggregate finding-level signals into review dashboard metrics."""

from collections import Counter

from app.schemas.review import Finding, ReviewMetrics


def _risk_band(score: float) -> str:
    if score >= 75:
        return "Critical"
    if score >= 55:
        return "High"
    if score >= 30:
        return "Moderate"
    return "Low"


def calculate_review_metrics(findings: list[Finding]) -> ReviewMetrics:
    """Summarize evidence health and contract risk without conflating the two."""
    severity_counts = Counter(item.risk_level for item in findings)
    verification_counts = Counter(item.verification for item in findings)
    evidence_bands = Counter(
        "strong" if item.combined_score >= 0.85
        else "moderate" if item.combined_score >= 0.70
        else "weak"
        for item in findings
    )
    count = len(findings)
    policy_coverage = (
        sum(bool(item.evidence) for item in findings) / count if count else 0
    )
    qwen_verified_coverage = (
        sum(item.verification in {"rule_and_qwen", "qwen_only"} for item in findings)
        / count
        if count else 0
    )
    qwen_assessment_coverage = (
        sum(item.verification in {"rule_and_qwen", "qwen_only", "needs_review"} for item in findings)
        / count
        if count else 0
    )
    strengths = [item.combined_score for item in findings]
    # Evidence health describes runtime coverage, not measured legal accuracy.
    pipeline_quality = (
        (sum(strengths) / count) * 70
        + policy_coverage * 15
        + qwen_assessment_coverage * 15
        if count else 0
    )

    top = sorted((item.priority_score for item in findings), reverse=True)[:5]
    maximum_priority = top[0] if top else 0
    top_five_mean = sum(top) / len(top) if top else 0
    prevalence = min(
        100,
        severity_counts["Critical"] * 25
        + severity_counts["High"] * 12
        + severity_counts["Medium"] * 5
        + severity_counts["Low"] * 2,
    )
    factors = {
        "maximum_finding_priority": round(maximum_priority, 1),
        "top_five_priority_mean": round(top_five_mean, 1),
        "risk_prevalence": round(prevalence, 1),
    }
    # Overall risk emphasizes the strongest item, while still accounting for
    # repeated exposure across the five highest-priority findings.
    overall = round(
        maximum_priority * 0.55 + top_five_mean * 0.30 + prevalence * 0.15,
        1,
    )
    return ReviewMetrics(
        overall_risk_score=overall,
        overall_risk_band=_risk_band(overall),
        pipeline_quality_score=round(min(100, pipeline_quality), 1),
        evidence_health_score=round(min(100, pipeline_quality), 1),
        severity_counts={
            name: severity_counts[name] for name in ("Critical", "High", "Medium", "Low")
        },
        verification_counts={
            name: verification_counts[name]
            for name in ("rule_and_qwen", "rules_only", "qwen_only", "needs_review")
        },
        evidence_bands={
            name: evidence_bands[name] for name in ("strong", "moderate", "weak")
        },
        policy_coverage=round(policy_coverage, 4),
        qwen_verification_coverage=round(qwen_verified_coverage, 4),
        qwen_assessment_coverage=round(qwen_assessment_coverage, 4),
        pending_human_review=sum(item.status == "pending" for item in findings),
        risk_score_factors=factors,
    )
