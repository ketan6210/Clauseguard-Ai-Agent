import pytest

from app.services.clause_classifier import classify_contract_type, classify_document


MSA_WITH_SCHEDULES = """
MASTER SERVICES AGREEMENT

This Master Services Agreement is entered into between Provider and Customer.
The parties agree to the services and commercial terms described below.

Schedule A - Order Form
The subscription fee is payable annually.

Schedule B - Data Processing Addendum
This Data Processing Addendum applies when Provider processes personal data.
Provider acts as processor and Customer acts as controller.
"""


def test_msa_remains_primary_when_document_contains_dpa():
    result = classify_document(MSA_WITH_SCHEDULES)

    assert result.primary_type == "Master Services Agreement"
    assert "Order Form" in result.attachments
    assert "Data Processing Addendum" in result.attachments
    assert result.confidence >= 0.7


def test_standalone_dpa_is_classified_as_dpa():
    text = """
    DATA PROCESSING AGREEMENT
    This Data Processing Agreement is entered into by the controller and processor.
    It governs processing of personal data.
    """

    assert classify_contract_type(text) == "Data Processing Agreement"


@pytest.mark.parametrize(
    ("heading", "expected"),
    [
        ("MUTUAL NON-DISCLOSURE AGREEMENT", "NDA"),
        ("EMPLOYMENT AGREEMENT", "Employment Agreement"),
        ("VENDOR AGREEMENT", "Vendor Agreement"),
        ("PROFESSIONAL SERVICES AGREEMENT", "Service Agreement"),
        ("INTERNAL POLICY", "Internal Policy"),
    ],
)
def test_primary_document_headings(heading, expected):
    assert classify_contract_type(f"{heading}\nThe parties agree to the following terms.") == expected


def test_incidental_legal_words_do_not_force_a_contract_type():
    text = "A cover letter discussing an employee, services, vendors, and company privacy."

    assert classify_contract_type(text) == "Unknown"
