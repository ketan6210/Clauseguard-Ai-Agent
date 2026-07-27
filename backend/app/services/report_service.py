from app.schemas.review import Clause, Finding


def deduplicate_findings(findings: list[Finding]) -> list[Finding]:
    unique: dict[tuple[str | None, str], Finding] = {}
    for finding in findings:
        key = (finding.clause_id, finding.title.lower().strip())
        current = unique.get(key)
        if current is None or finding.confidence > current.confidence:
            unique[key] = finding
    return list(unique.values())


def create_review_summary(contract_type: str, clauses: list[Clause], findings: list[Finding]) -> str:
    high = sum(item.risk_level in {"High", "Critical"} for item in findings)
    missing = sum(item.clause_id is None for item in findings)
    return f"Reviewed {len(clauses)} clauses in a {contract_type}. Found {len(findings)} issue(s), including {high} high-risk and {missing} missing-clause finding(s). Human review is required before relying on these results."


def create_report_json(review) -> dict:
    return review.model_dump(mode="json") if hasattr(review, "model_dump") else dict(review)
