from app.schemas.review import Clause
from app.services.conflict_detector import detect_clause_conflicts


def _clause(identifier: str, text: str) -> Clause:
    return Clause(
        id=identifier,
        clause_type="other",
        text=text,
        page=1,
        confidence=0.88,
    )


def test_detects_cross_clause_numeric_conflicts():
    clauses = [
        _clause("payment-msa", "3.2 Payment Terms. Invoices are due within thirty (30) days."),
        _clause("payment-order", "Schedule A. Payment Terms are Net 10 from the invoice date."),
        _clause("delete-msa", "Provider may delete Customer Data after thirty (30) days."),
        _clause("delete-dpa", "Provider may retain Customer Data for one hundred eighty (180) days."),
        _clause("breach-msa", "Provider will notify Customer within seventy-two (72) hours after a Security Incident."),
        _clause("breach-dpa", "Provider will notify Customer within five (5) days after a data breach."),
        _clause("sla-msa", "Provider targets 99.5% uptime."),
        _clause("sla-order", "The availability commitment is 99.0%."),
    ]

    titles = {finding.title for finding in detect_clause_conflicts(clauses)}

    assert titles == {
        "Conflicting payment terms",
        "Conflicting data deletion periods",
        "Conflicting breach notification periods",
        "Conflicting service-level commitments",
    }


def test_detects_conflicting_document_precedence():
    clauses = [
        _clause(
            "precedence-1",
            "The Data Processing Addendum will control for matters concerning personal data.",
        ),
        _clause(
            "precedence-2",
            "This Master Agreement controls over all schedules and addenda.",
        ),
    ]

    findings = detect_clause_conflicts(clauses)

    assert len(findings) == 1
    assert findings[0].title == "Conflicting document precedence"
    assert findings[0].risk_level == "High"


def test_equal_values_are_not_reported_as_conflicts():
    clauses = [
        _clause("payment-1", "Invoices are due within thirty (30) days."),
        _clause("payment-2", "Payment terms are Net 30."),
    ]

    assert detect_clause_conflicts(clauses) == []
