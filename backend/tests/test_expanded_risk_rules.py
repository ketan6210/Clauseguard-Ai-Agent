import pytest

from app.schemas.review import Clause
from app.services.clause_classifier import classify_clause
from app.services.risk_engine import analyze_clause_risk


@pytest.mark.parametrize(
    ("text", "expected_title", "expected_level"),
    [
        (
            "7.3 AI Training Provider may use Customer Data and prompts to train and fine-tune machine-learning models.",
            "Customer data may be used for AI training",
            "High",
        ),
        (
            "7.2 License to Provider Customer grants a perpetual, irrevocable, sublicensable license to Customer Data.",
            "Overly broad customer-data license",
            "High",
        ),
        (
            "7.4 Data Sharing Provider may share Customer Data with data brokers and marketing partners.",
            "Customer data may be commercialized or broadly shared",
            "High",
        ),
        (
            "3.4 Price Changes Provider may increase fees by twenty-five percent (25%) during the current term.",
            "Unilateral price increase",
            "High",
        ),
        (
            "5.1 Provider may terminate for convenience on ten days notice, but Customer may not terminate for convenience.",
            "One-sided termination right",
            "High",
        ),
        (
            "5.3 Early Termination Charge Customer must pay all remaining fees plus a transition fee.",
            "Excessive early-termination charges",
            "High",
        ),
        (
            "8.1 Security Program Provider will maintain safeguards it considers commercially reasonable and does not warrant compliance with any standard.",
            "Weak security-control commitment",
            "High",
        ),
        (
            "11.2 Disclaimer THE SERVICES ARE PROVIDED AS IS AND PROVIDER DISCLAIMS ALL WARRANTIES.",
            "Broad warranty disclaimer",
            "Medium",
        ),
    ],
)
def test_expanded_high_risk_rules(text, expected_title, expected_level):
    clause = Clause(
        id="test-clause",
        clause_type=classify_clause(text),
        text=text,
        page=1,
        confidence=0.88,
    )

    findings = analyze_clause_risk(clause, [])

    assert any(
        finding.title == expected_title and finding.risk_level == expected_level
        for finding in findings
    )


def test_long_parenthetical_deletion_period_is_high_risk():
    text = (
        "7.6 Retention and Deletion Provider may retain Customer Data for one "
        "hundred eighty (180) days after termination."
    )
    clause = Clause(
        id="deletion",
        clause_type="data_deletion",
        text=text,
        page=5,
        confidence=0.88,
    )

    findings = analyze_clause_risk(clause, [])

    assert findings[0].title == "Excessive post-termination data retention"
    assert "180 days" in findings[0].explanation


def test_related_sla_problems_are_merged_into_one_finding():
    text = (
        "10.3 Service Level Availability is 99.0%. Service credits capped at five "
        "percent are Customer's sole remedy."
    )
    clause = Clause(
        id="sla",
        clause_type="service_levels",
        text=text,
        page=7,
        confidence=0.88,
    )

    findings = analyze_clause_risk(clause, [])

    assert [finding.title for finding in findings] == [
        "Weak SLA with exclusive service-credit remedy"
    ]
