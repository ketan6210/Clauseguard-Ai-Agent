import pytest

from app.schemas.review import Clause
from app.services.number_parser import (
    extract_duration,
    extract_measurements,
    extract_number_of_days,
    extract_number_of_hours,
    extract_payment_days,
    extract_percentages,
    parse_number_words,
)
from app.services.risk_engine import analyze_clause_risk


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("seventy-two", 72),
        ("one hundred twenty", 120),
        ("one hundred and eighty", 180),
        ("forty-five", 45),
        ("three thousand two hundred ten", 3210),
    ],
)
def test_parse_written_numbers(source, expected):
    assert parse_number_words(source) == expected


@pytest.mark.parametrize(
    ("source", "expected_days"),
    [
        ("within 10 business days after discovery", 10),
        ("at least one hundred twenty (120) days before renewal", 120),
        ("retained for one hundred eighty (180) days", 180),
        ("provide thirty calendar days notice", 30),
        ("within seventy-two (72) hours", 3),
        ("within seventy-two hours", 3),
    ],
)
def test_extract_days_from_legal_formats(source, expected_days):
    assert extract_number_of_days(source) == expected_days


def test_extract_structured_measurements():
    measurements = extract_measurements(
        "The initial term is three (3) years and notice is due 120 calendar days before renewal."
    )

    assert [(item.value, item.unit, item.qualifier) for item in measurements] == [
        (3.0, "years", None),
        (120.0, "days", "calendar"),
    ]
    assert extract_duration("limited to one (1) month of fees", "months") == 1
    assert extract_number_of_hours("within seventy-two (72) hours") == 72


def test_extract_payment_and_percentage_values():
    assert extract_payment_days("Invoices are payable Net 60 from receipt.") == 60
    assert extract_payment_days("Undisputed amounts are due within thirty (30) days.") == 30
    assert extract_percentages("Interest is two percent (2.0%) per month.") == [2.0]


def test_parenthetical_renewal_period_triggers_risk():
    clause = Clause(
        id="clause-renewal",
        clause_type="renewal",
        text=(
            "This Agreement automatically renews unless Customer gives written "
            "notice at least one hundred twenty (120) days before renewal."
        ),
        page=4,
        confidence=0.88,
    )

    findings = analyze_clause_risk(clause, [])

    assert len(findings) == 1
    assert findings[0].risk_level == "High"
    assert "120 days" in findings[0].explanation


def test_compliant_parenthetical_breach_period_does_not_trigger_risk():
    clause = Clause(
        id="clause-breach",
        clause_type="data_breach_notification",
        text="Provider will notify Customer within seventy-two (72) hours after confirming an incident.",
        page=6,
        confidence=0.88,
    )

    assert analyze_clause_risk(clause, []) == []
