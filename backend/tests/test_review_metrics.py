from app.schemas.review import Finding
from app.services.review_metrics import calculate_review_metrics


def _finding(level: str, combined: float, priority: float, verification="rule_and_qwen"):
    return Finding(
        id=f"{level}-{priority}",
        title="Test finding",
        risk_level=level,
        confidence=combined,
        combined_score=combined,
        priority_score=priority,
        priority_band="High" if priority >= 50 else "Moderate",
        explanation="test",
        recommended_action="test",
        contract_excerpt="A sufficiently clear contract clause will apply.",
        evidence=[],
        verification=verification,
    )


def test_review_metrics_separate_risk_from_pipeline_quality():
    metrics = calculate_review_metrics(
        [
            _finding("High", 0.9, 72),
            _finding("Medium", 0.8, 44, "rules_only"),
        ]
    )

    assert metrics.overall_risk_score > 0
    assert metrics.overall_risk_band in {"Moderate", "High", "Critical"}
    assert metrics.pipeline_quality_score > 0
    assert metrics.severity_counts["High"] == 1
    assert metrics.qwen_verification_coverage == 0.5
    assert metrics.qwen_assessment_coverage == 0.5
