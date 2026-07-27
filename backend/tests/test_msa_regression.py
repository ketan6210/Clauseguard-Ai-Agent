from pathlib import Path

from app.services.clause_classifier import classify_document, extract_clauses
from app.services.conflict_detector import detect_clause_conflicts
from app.services.document_parser import parse_document
from app.services.risk_engine import analyze_clause_risk


FIXTURE = Path(__file__).resolve().parents[2] / "sample_documents" / "msa_regression.txt"


def test_msa_regression_pipeline():
    pages = parse_document(FIXTURE)
    full_text = "\n".join(page.text for page in pages)
    classification = classify_document(full_text)
    clauses = extract_clauses(pages)
    risks = [
        finding
        for clause in clauses
        for finding in analyze_clause_risk(clause, [])
    ]
    conflicts = detect_clause_conflicts(clauses)
    titles = {finding.title for finding in risks + conflicts}

    assert classification.primary_type == "Master Services Agreement"
    assert classification.attachments == (
        "Data Processing Addendum",
        "Order Form",
    )
    assert 8 <= len(clauses) <= 12
    assert {
        "Excessive renewal cancellation notice",
        "One-sided termination right",
        "Customer data may be used for AI training",
        "Overly broad customer-data license",
        "Excessive post-termination data retention",
        "Breach notification exceeds 72 hours",
        "Liability cap below policy",
        "Conflicting payment terms",
        "Conflicting data deletion periods",
        "Conflicting breach notification periods",
    } <= titles
