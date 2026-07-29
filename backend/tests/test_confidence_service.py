from app.schemas.review import Clause, Evidence, Finding
from app.services import confidence_service


CLAUSE = Clause(
    id="clause-1",
    clause_type="indemnification",
    text="Customer will defend and indemnify Provider against all claims and losses.",
    page=1,
    confidence=0.9,
)
FINDING = Finding(
    id="finding-1",
    clause_id="clause-1",
    title="Broad customer indemnification",
    risk_level="High",
    confidence=0.5,
    explanation="The clause creates broad customer exposure.",
    recommended_action="Narrow the indemnity.",
    contract_excerpt=CLAUSE.text,
    evidence=[
        Evidence(
            source_id="POL-INDEM-001",
            title="Indemnity policy",
            section="Risk",
            text="Indemnity should be mutual and narrow.",
            score=0.8,
        )
    ],
)


def test_match_strength_combines_explainable_factors(monkeypatch):
    monkeypatch.setattr(
        confidence_service,
        "verify_findings_with_qwen",
        lambda findings, clauses: {
            "finding-1": {
                "supported": True,
                "ambiguity": "low",
                "evidence_ids": ["clause-1"],
            }
        },
    )

    result = confidence_service.score_findings([CLAUSE], [FINDING])[0]

    assert result.verification == "rule_and_qwen"
    assert result.confidence != 0.92
    assert result.combined_score == result.confidence
    assert result.priority_score > 0
    assert result.priority_band in {"Low", "Moderate", "High", "Urgent"}
    assert set(result.confidence_factors) == set(confidence_service.WEIGHTS)
    assert set(result.score_contributions) == set(confidence_service.WEIGHTS)
    assert round(sum(result.score_contributions.values()), 3) == round(result.combined_score, 3)
    assert result.confidence_factors["qwen_verification"] == 0.95


def test_qwen_disagreement_caps_match_strength(monkeypatch):
    monkeypatch.setattr(
        confidence_service,
        "verify_findings_with_qwen",
        lambda findings, clauses: {
            "finding-1": {
                "supported": False,
                "ambiguity": "high",
                "evidence_ids": [],
            }
        },
    )

    result = confidence_service.score_findings([CLAUSE], [FINDING])[0]

    assert result.verification == "needs_review"
    assert result.confidence <= 0.59
    assert result.priority_score <= 47.2


def test_uncertain_critical_finding_is_urgent(monkeypatch):
    critical = FINDING.model_copy(update={"risk_level": "Critical"})
    monkeypatch.setattr(
        confidence_service,
        "verify_findings_with_qwen",
        lambda findings, clauses: {
            "finding-1": {
                "supported": False,
                "ambiguity": "high",
                "policy_stance": "insufficient",
                "evidence_ids": [],
            }
        },
    )

    result = confidence_service.score_findings([CLAUSE], [critical])[0]

    assert result.priority_score >= 75
    assert result.priority_band == "Urgent"
