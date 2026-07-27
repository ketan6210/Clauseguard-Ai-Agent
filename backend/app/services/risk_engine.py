import math
import re

from app.schemas.review import Clause, Evidence, Finding


NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "ten": 10, "twelve": 12, "thirty": 30, "forty-five": 45, "sixty": 60, "seventy-two": 72, "ninety": 90, "one hundred twenty": 120}


def extract_number_of_days(text: str) -> int | None:
    lowered = text.lower()
    match = re.search(r"\b(\d{1,3})\s+(?:business\s+|calendar\s+)?days?\b", lowered)
    if match:
        return int(match.group(1))
    for word, value in sorted(NUMBER_WORDS.items(), key=lambda item: len(item[0]), reverse=True):
        if re.search(rf"\b{re.escape(word)}\s+(?:business\s+|calendar\s+)?days?\b", lowered):
            return value
    hours = re.search(r"\b(\d{1,3})\s+hours?\b", lowered)
    return math.ceil(int(hours.group(1)) / 24) if hours else None


def _finding(clause: Clause, title: str, level: str, explanation: str, action: str, evidence: list[Evidence]) -> Finding:
    return Finding(id=f"finding-{clause.id}-{re.sub('[^a-z]+', '-', title.lower()).strip('-')}", clause_id=clause.id, title=title, risk_level=level, confidence=0.92, explanation=explanation, recommended_action=action, contract_excerpt=clause.text[:500], evidence=evidence)


def analyze_clause_risk(clause: Clause, evidence: list[Evidence]) -> list[Finding]:
    text = clause.text.lower()
    days = extract_number_of_days(text)
    if clause.clause_type == "data_breach_notification" and days and days > 3:
        return [_finding(clause, "Breach notification exceeds 72 hours", "High", f"The clause permits notification after {days} days, exceeding the 72-hour policy.", "Require notification within 72 hours of discovery.", evidence)]
    if clause.clause_type == "renewal" and ("automatic" in text or "auto-renew" in text) and days and days > 30:
        return [_finding(clause, "Excessive renewal cancellation notice", "High" if days > 90 else "Medium", f"Cancellation requires {days} days notice; policy permits no more than 30.", "Reduce the non-renewal notice period to 30 days.", evidence)]
    if clause.clause_type == "payment_terms":
        net = re.search(r"\bnet\s*(\d{1,3})\b", text)
        if net and int(net.group(1)) > 45:
            return [_finding(clause, "Payment terms exceed Net 45", "Medium", f"Payment is Net {net.group(1)}, outside the standard policy.", "Negotiate Net 45 or obtain Finance approval.", evidence)]
    if clause.clause_type == "liability":
        months = re.search(r"(?:one|1)\s+months?", text)
        if months:
            return [_finding(clause, "Liability cap below policy", "High", "The liability cap is only one month of fees; policy requires at least 12 months.", "Raise the cap to at least 12 months of fees.", evidence)]
    return []


def detect_missing_clauses(contract_type: str, clauses: list[Clause], evidence_by_category: dict[str, list[Evidence]]) -> list[Finding]:
    required = {"Vendor Agreement": {"data_deletion": "High", "audit_rights": "Medium"}, "Data Processing Agreement": {"data_deletion": "High", "audit_rights": "Medium"}}
    present = {clause.clause_type for clause in clauses}
    findings = []
    for category, level in required.get(contract_type, {}).items():
        if category in present:
            continue
        title = f"Missing {category.replace('_', ' ')} clause"
        findings.append(Finding(id=f"finding-missing-{category}", title=title, risk_level=level, confidence=0.95, explanation=f"No {category.replace('_', ' ')} clause was detected, but it is required for this contract type.", recommended_action="Add the approved policy language before execution.", contract_excerpt="No matching clause found.", evidence=evidence_by_category.get(category, [])))
    return findings
