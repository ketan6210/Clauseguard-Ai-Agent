from app.schemas.review import Clause
from app.services.contract_checklists import get_contract_checklist
from app.services.risk_engine import detect_missing_clauses


def _clause(identifier: str, category: str) -> Clause:
    return Clause(
        id=identifier,
        clause_type=category,
        text=f"Example {category} language for testing.",
        page=1,
        confidence=0.88,
    )


def test_msa_checklist_contains_core_legal_and_security_categories():
    categories = {
        requirement.category
        for requirement in get_contract_checklist("Master Services Agreement")
    }

    assert {
        "payment_terms",
        "termination",
        "confidentiality",
        "data_breach_notification",
        "data_deletion",
        "security_controls",
        "indemnification",
        "liability",
        "audit_rights",
    } <= categories


def test_missing_msa_clauses_generate_findings():
    clauses = [
        _clause("payment", "payment_terms"),
        _clause("termination", "termination_for_convenience"),
        _clause("confidential", "confidentiality"),
    ]

    findings = detect_missing_clauses(
        "Master Services Agreement",
        clauses,
        evidence_by_category={},
    )
    titles = {finding.title for finding in findings}

    assert "Missing security controls clause" in titles
    assert "Missing indemnification clause" in titles
    assert "Missing limitation of liability clause" in titles
    assert "Missing termination rights clause" not in titles


def test_unknown_document_has_no_assumed_checklist():
    assert detect_missing_clauses("Unknown", [], {}) == []
