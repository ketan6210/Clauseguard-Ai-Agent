from pathlib import Path

from app.schemas.review import Evidence, Finding
from app.services.evaluation import EvaluationCase, score_case, score_retrieval


def _finding(title: str) -> Finding:
    return Finding(
        id=title,
        title=title,
        risk_level="High",
        confidence=1,
        explanation="test",
        recommended_action="test",
        contract_excerpt="test",
    )


def test_evaluation_reports_precision_recall_and_forbidden_findings():
    case = EvaluationCase(
        name="example",
        document=Path("unused"),
        expected_contract_type="Master Services Agreement",
        expected_findings=frozenset({"Expected A", "Expected B"}),
        forbidden_findings=frozenset({"Bad finding"}),
    )
    result = {
        "contract_type": "Master Services Agreement",
        "findings": [_finding("Expected A"), _finding("Bad finding")],
    }

    score = score_case(case, result)

    assert score["classification_correct"] is True
    assert score["precision"] == 0.5
    assert score["recall"] == 0.5
    assert score["forbidden_findings"] == 1
    assert score["brier_score"] == 0.6667


def test_retrieval_metrics_report_recall_at_k_and_mrr():
    results = [
        Evidence(source_id="wrong", title="x", section="x", text="x", score=0.8),
        Evidence(source_id="expected", title="x", section="x", text="x", score=0.7),
    ]

    score = score_retrieval({"expected"}, results, k=2)

    assert score == {"recall_at_2": 1.0, "mrr": 0.5}
