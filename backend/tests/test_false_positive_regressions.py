from app.schemas.review import Clause, Finding
from app.services.clause_classifier import classify_clause
from app.services.report_service import deduplicate_findings
from app.services.risk_engine import analyze_clause_risk


def _analyze(text: str):
    clause = Clause(
        id="regression",
        clause_type=classify_clause(text),
        text=text,
        page=1,
        confidence=0.88,
    )
    return clause, analyze_clause_risk(clause, [])


def test_authorized_user_definition_is_not_a_warranty():
    text = (
        '1.1 Authorized User means a person whom Customer permits to access the '
        'Services, whether or not Provider has issued that person a credential.'
    )

    clause, findings = _analyze(text)

    assert clause.clause_type != "warranty"
    assert findings == []


def test_feedback_license_is_not_a_customer_data_license():
    text = (
        "9.2 Feedback Customer grants Provider a perpetual, irrevocable right to "
        "commercialize suggestions, ideas, requests, or feedback."
    )

    clause, findings = _analyze(text)

    assert clause.clause_type == "feedback_rights"
    assert [finding.title for finding in findings] == ["Broad feedback-use rights"]
    assert findings[0].risk_level == "Medium"


def test_negated_termination_charge_is_not_a_fee_risk():
    text = (
        "Special Terms. Customer may terminate for convenience after six months "
        "by giving thirty days notice and paying no additional termination charge."
    )

    _, findings = _analyze(text)

    assert "Excessive early-termination charges" not in {
        finding.title for finding in findings
    }


def test_new_asymmetric_and_publicity_risks():
    examples = {
        "13.3 Customer Liability Customer's obligations are uncapped and not subject to any exclusion of damages.": "Unequal uncapped customer liability",
        "12.2 Provider Indemnity Provider will defend only United States patent claims; Provider has no obligation for data or outputs.": "Narrow provider indemnification",
        "17.3 Publicity Provider may use Customer's name and logo in customer lists and press releases without approval.": "Publicity rights without customer approval",
        "16.3 Fees Customer will advance all arbitration fees and Provider's reasonable legal fees.": "One-sided arbitration cost shifting",
        "14.1 Non-Competition Customer will not use any product that competes with Provider for twenty-four months.": "Restrictive customer covenant",
    }

    for text, expected_title in examples.items():
        _, findings = _analyze(text)
        assert expected_title in {finding.title for finding in findings}


def test_exact_duplicate_findings_are_removed():
    finding = Finding(
        id="one",
        clause_id="clause-1",
        title="Example risk",
        risk_level="Medium",
        confidence=0.8,
        explanation="Example",
        recommended_action="Review",
        contract_excerpt="Text",
        evidence=[],
    )

    assert deduplicate_findings([finding, finding.model_copy(update={"id": "two"})]) == [
        finding
    ]
