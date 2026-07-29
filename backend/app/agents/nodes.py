from app.services.clause_classifier import classify_contract_type, extract_clauses
from app.services.confidence_service import score_findings
from app.core.config import settings
from app.services.conflict_detector import detect_clause_conflicts
from app.services.contract_store import index_contract_clauses
from app.services.document_parser import parse_document
from app.services.llm_service import analyze_residual_risks
from app.services.policy_store import hybrid_search, load_policies
from app.services.report_service import create_review_summary, deduplicate_findings
from app.services.risk_engine import analyze_clause_risk, detect_missing_clauses


def run_review(file_path: str, review_id: str | None = None) -> dict:
    pages = parse_document(file_path)
    full_text = "\n".join(page.text for page in pages)
    contract_type = classify_contract_type(full_text)
    clauses = extract_clauses(pages)
    if review_id:
        index_contract_clauses(review_id, clauses)
    policies = load_policies()
    policy_categories = {policy["id"]: policy["category"] for policy in policies}
    evidence_by_clause = {}
    for clause in clauses:
        retrieved = hybrid_search(clause.text, clause.clause_type)
        evidence_by_clause[clause.id] = [
            item
            for item in retrieved
            if policy_categories.get(item.source_id) == clause.clause_type
            and item.score >= settings.policy_retrieval_min_score
        ][:3]
    findings = [finding for clause in clauses for finding in analyze_clause_risk(clause, evidence_by_clause[clause.id])]
    findings.extend(detect_clause_conflicts(clauses))
    missing_categories = {policy["category"] for policy in policies}
    category_evidence = {
        category: hybrid_search(
            next(policy["text"] for policy in policies if policy["category"] == category),
            category,
        )
        for category in missing_categories
    }
    findings.extend(detect_missing_clauses(contract_type, clauses, category_evidence))
    findings.extend(analyze_residual_risks(clauses, findings))
    findings = deduplicate_findings(findings)
    findings = score_findings(clauses, findings)
    summary = create_review_summary(contract_type, clauses, findings)
    return {"pages": pages, "full_text": full_text, "contract_type": contract_type, "clauses": clauses, "findings": findings, "summary": summary}
