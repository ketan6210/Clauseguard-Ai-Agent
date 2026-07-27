from app.services.clause_classifier import classify_contract_type, extract_clauses
from app.services.document_parser import parse_document
from app.services.policy_store import hybrid_search, load_policies
from app.services.report_service import create_review_summary
from app.services.risk_engine import analyze_clause_risk, detect_missing_clauses


def run_review(file_path: str) -> dict:
    pages = parse_document(file_path)
    full_text = "\n".join(page.text for page in pages)
    contract_type = classify_contract_type(full_text)
    clauses = extract_clauses(pages)
    evidence_by_clause = {clause.id: hybrid_search(clause.text, clause.clause_type) for clause in clauses}
    findings = [finding for clause in clauses for finding in analyze_clause_risk(clause, evidence_by_clause[clause.id])]
    policies = load_policies()
    missing_categories = {"data_deletion", "audit_rights"}
    category_evidence = {category: hybrid_search(next(policy["text"] for policy in policies if policy["category"] == category), category) for category in missing_categories}
    findings.extend(detect_missing_clauses(contract_type, clauses, category_evidence))
    summary = create_review_summary(contract_type, clauses, findings)
    return {"pages": pages, "full_text": full_text, "contract_type": contract_type, "clauses": clauses, "findings": findings, "summary": summary}
