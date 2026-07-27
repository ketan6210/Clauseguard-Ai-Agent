import re

from app.schemas.review import Clause, DocumentPage


CLAUSE_KEYWORDS = {
    "data_breach_notification": ("breach", "security incident", "notify", "notification"),
    "data_deletion": ("delete", "deletion", "return customer data", "destroy data"),
    "data_retention": ("retain", "retention"),
    "payment_terms": ("payment", "net 30", "net 45", "net 60", "invoice"),
    "renewal": ("renew", "renewal", "auto-renew"),
    "termination": ("terminate", "termination"),
    "liability": ("liable", "liability", "limitation of liability"),
    "indemnification": ("indemnify", "indemnification"),
    "audit_rights": ("audit", "inspection rights"),
    "governing_law": ("governing law", "governed by"),
    "security_controls": ("security controls", "information security", "encryption"),
    "confidentiality": ("confidential", "non-disclosure", "nondisclosure"),
}


def classify_contract_type(full_text: str) -> str:
    text = full_text.lower()
    candidates = [
        ("Data Processing Agreement", ("data processing agreement", "data processor", "controller")),
        ("NDA", ("non-disclosure agreement", "nondisclosure agreement", "receiving party")),
        ("Employment Agreement", ("employment agreement", "employee")),
        ("Vendor Agreement", ("vendor agreement", "vendor", "supplier")),
        ("Service Agreement", ("service agreement", "services", "service provider")),
        ("Internal Policy", ("internal policy", "policy applies")),
    ]
    for label, keywords in candidates:
        if any(keyword in text for keyword in keywords):
            return label
    return "Unknown"


def classify_clause(text: str) -> str:
    lowered = text.lower()
    scores = {category: sum(keyword in lowered for keyword in keywords) for category, keywords in CLAUSE_KEYWORDS.items()}
    category, score = max(scores.items(), key=lambda item: item[1])
    return category if score else "other"


def _segments(text: str) -> list[str]:
    blocks = re.split(r"\n\s*\n|(?=\n\s*(?:\d+(?:\.\d+)*[.)]?|[A-Z][A-Z ]{3,}:?)\s+)", text)
    if len([b for b in blocks if b.strip()]) <= 1:
        blocks = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
    return [re.sub(r"\s+", " ", block).strip() for block in blocks if block.strip()]


def extract_clauses(pages: list[DocumentPage]) -> list[Clause]:
    clauses: list[Clause] = []
    for page in pages:
        for text in _segments(page.text):
            if len(text) < 15:
                continue
            clause_type = classify_clause(text)
            clauses.append(Clause(id=f"clause-{len(clauses) + 1}", clause_type=clause_type, text=text, page=page.page_number, confidence=0.88 if clause_type != "other" else 0.55))
    return clauses
