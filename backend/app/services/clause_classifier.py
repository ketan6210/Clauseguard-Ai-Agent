import re
from dataclasses import dataclass

from app.schemas.review import Clause, DocumentPage


CLAUSE_KEYWORDS = {
    "ai_training": ("ai training", "train", "fine-tune", "machine-learning model", "machine learning model"),
    "feedback_rights": ("feedback", "suggestions", "ideas", "feature requests"),
    "data_commercialization": ("commercialize", "data broker", "advertising", "sell customer data"),
    "data_licensing": ("license to provider", "perpetual", "irrevocable", "sublicensable", "royalty-free"),
    "data_sharing": ("data sharing", "share customer data", "marketing partners", "transaction counterparties"),
    "unilateral_changes": ("unilateral", "service modification", "modify any feature", "discontinue any feature", "continued use constitutes acceptance", "failure to provide notice"),
    "price_changes": ("price changes", "increase fees", "fee increase", "change the fees"),
    "early_termination_fee": ("early termination", "termination charge", "remaining fees", "transition fee"),
    "termination_for_convenience": ("terminate for convenience", "termination for convenience"),
    "termination_cure_period": ("cure period", "fails to cure", "uncured breach"),
    "service_levels": ("service level", "uptime", "service credit", "availability"),
    "suspension": ("suspend access", "suspension", "suspend the services"),
    "warranty": ("warranty", "warranties", "as is"),
    "intellectual_property": ("intellectual property", "ownership of deliverables", "work product"),
    "subprocessors": ("subprocessor", "subprocessors", "subcontractor", "subcontractors", "sub-processors"),
    "cross_border_transfer": ("cross-border", "international transfer", "transfer to any country", "process data outside"),
    "assignment": ("assignment", "assign this agreement", "change of control"),
    "dispute_resolution": ("dispute resolution", "arbitration", "venue", "jurisdiction"),
    "arbitration_costs": ("arbitration fees", "advance all arbitration", "legal fees"),
    "publicity_rights": ("publicity", "customer lists", "case studies", "press releases", "use customer's name"),
    "restrictive_covenants": ("restrictive covenant", "non-compete", "non-competition", "non-solicit", "benchmarking restriction"),
    "data_deletion": ("data deletion", "delete customer data", "deletion", "return or delete", "destroy data"),
    "data_retention": ("data retention", "retention and deletion", "retain customer data", "retention period"),
    "payment_terms": ("payment terms", "net 30", "net 45", "net 60", "invoice", "amounts are due"),
    "renewal": ("automatic renewal", "automatically renew", "auto-renew", "non-renewal"),
    "indemnification": ("indemnity", "indemnify", "indemnification", "defend and hold harmless"),
    "liability": ("limitation of liability", "liability cap", "aggregate liability", "liable for"),
    "audit_rights": ("audit rights", "audit and compliance", "right to audit", "inspection rights"),
    "governing_law": ("governing law", "governed by"),
    "security_controls": ("security controls", "information security", "security program", "encryption", "safeguards"),
    "business_continuity": ("business continuity", "disaster recovery", "recovery time objective", "recovery point objective"),
    "insurance": ("cyber insurance", "insurance coverage", "certificate of insurance"),
    "data_use_restrictions": ("documented instructions", "solely to provide the services", "only as necessary to provide"),
    "confidentiality": ("confidential information", "confidentiality", "non-disclosure", "nondisclosure"),
    "termination": ("terminate", "termination"),
}

DOCUMENT_PATTERNS = {
    "Master Services Agreement": (
        r"\bmaster services agreement\b",
        r"\bmaster service agreement\b",
        r"\bmsa\b",
    ),
    "Data Processing Agreement": (
        r"\bdata processing agreement\b",
        r"\bdata processing addendum\b",
        r"\bdpa\b",
    ),
    "NDA": (
        r"\bnon[- ]disclosure agreement\b",
        r"\bmutual confidentiality agreement\b",
        r"\bnda\b",
    ),
    "Employment Agreement": (r"\bemployment agreement\b", r"\boffer of employment\b"),
    "Vendor Agreement": (r"\bvendor agreement\b", r"\bsupplier agreement\b"),
    "Service Agreement": (r"\bservices? agreement\b", r"\bprofessional services agreement\b"),
    "Internal Policy": (r"\binternal policy\b", r"\bcompany policy\b"),
}
TYPE_PRIORITY = list(DOCUMENT_PATTERNS)


@dataclass(frozen=True)
class DocumentClassification:
    primary_type: str
    attachments: tuple[str, ...]
    confidence: float
    scores: dict[str, int]


def _heading_score(text: str, pattern: str) -> int:
    score = 0
    for line_number, line in enumerate(text.splitlines()):
        cleaned = re.sub(r"\s+", " ", line).strip(" \t:.-")
        if not cleaned:
            continue
        if re.fullmatch(pattern, cleaned, re.IGNORECASE):
            score = max(score, 120 if line_number < 40 else 100)
        elif line_number < 40 and re.search(pattern, cleaned, re.IGNORECASE):
            score = max(score, 35)
    return score


def classify_document(full_text: str) -> DocumentClassification:
    normalized = re.sub(r"[ \t]+", " ", full_text)
    opening = normalized[:4000]
    scores: dict[str, int] = {}
    for label, patterns in DOCUMENT_PATTERNS.items():
        score = 0
        for pattern in patterns:
            score += min(len(re.findall(pattern, normalized, re.IGNORECASE)), 8) * 3
            if re.search(pattern, opening, re.IGNORECASE):
                score += 20
            score += _heading_score(normalized, pattern)
        scores[label] = score

    best_type = max(TYPE_PRIORITY, key=lambda label: (scores[label], -TYPE_PRIORITY.index(label)))
    best_score = scores[best_type]
    if best_score < 20:
        best_type = "Unknown"

    attachments: list[str] = []
    attachment_rules = (
        ("Data Processing Addendum", r"(?:schedule|appendix|addendum)\s+[A-Z0-9-]*.{0,40}\bdata processing (?:addendum|agreement)\b"),
        ("Order Form", r"(?:schedule|appendix)\s+[A-Z0-9-]*.{0,40}\border form\b"),
        ("Service Level Agreement", r"(?:schedule|appendix|addendum)\s+[A-Z0-9-]*.{0,40}\bservice level"),
        ("Security Addendum", r"(?:schedule|appendix|addendum)\s+[A-Z0-9-]*.{0,40}\bsecurity"),
    )
    for label, pattern in attachment_rules:
        if re.search(pattern, normalized, re.IGNORECASE | re.DOTALL):
            attachments.append(label)

    runner_up = max((score for label, score in scores.items() if label != best_type), default=0)
    margin = max(0, best_score - runner_up)
    confidence = 0.5 if best_type == "Unknown" else min(0.99, 0.72 + margin / 300)
    return DocumentClassification(
        primary_type=best_type,
        attachments=tuple(attachments),
        confidence=round(confidence, 2),
        scores=scores,
    )


def classify_contract_type(full_text: str) -> str:
    return classify_document(full_text).primary_type


def classify_clause(text: str) -> str:
    return classify_clause_with_confidence(text)[0]


def classify_clause_with_confidence(text: str) -> tuple[str, float]:
    lowered = text.lower()
    if (
        "security incident" in lowered
        or "data breach" in lowered
        or ("breach" in lowered and any(term in lowered for term in ("notify", "notification", "incident notice")))
    ):
        return "data_breach_notification", 0.97
    priority_rules = (
        ("feedback_rights", ("feedback customer", "feedback. customer", "9.2 feedback")),
        ("publicity_rights", ("publicity provider", "publicity. provider", "17.3 publicity")),
        ("arbitration_costs", ("advance all arbitration fees", "arbitration fees and")),
        ("early_termination_fee", ("early termination charge", "early termination fee")),
        ("termination_cure_period", ("fails to cure", "failure to cure", "cure period")),
        ("termination_for_convenience", ("terminate for convenience", "termination for convenience")),
    )
    for category, phrases in priority_rules:
        if any(phrase in lowered for phrase in phrases):
            return category, 0.96

    heading = lowered[:160]
    scores = {}
    for category, keywords in CLAUSE_KEYWORDS.items():
        score = 0
        for keyword in keywords:
            keyword_pattern = rf"(?<!\w){re.escape(keyword)}(?!\w)"
            if re.search(keyword_pattern, lowered):
                score += 1 + (1 if " " in keyword else 0)
            if re.search(keyword_pattern, heading):
                score += 2
        scores[category] = score
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    category, score = ranked[0]
    if not score:
        return "other", 0.35
    runner_up = ranked[1][1] if len(ranked) > 1 else 0
    margin = max(0, score - runner_up)
    confidence = min(0.97, 0.55 + min(score, 4) * 0.08 + min(margin, 3) * 0.04)
    return category, round(confidence, 4)


SECTION_HEADING = re.compile(
    r"^(?P<section>(?:\d+(?:\.\d+)*|[A-Z]-\d+(?:\.\d+)*))(?:[.)])?\s+(?P<title>[A-Z][^\n]{1,120})$"
)
INLINE_NUMBERED_CLAUSE = re.compile(
    r"^(?P<section>\d+(?:\.\d+)*)(?:[.)])?\s+"
    r"(?P<title>[A-Z][^.]{1,100}\.)\s+(?P<body>.+)$"
)
SCHEDULE_HEADING = re.compile(
    r"^(?:SCHEDULE|EXHIBIT|APPENDIX|ANNEX)\s+[A-Z0-9-]+(?:\s*[-:]\s*|\s+).+$",
    re.IGNORECASE,
)
DOCUMENT_HEADING = re.compile(
    r"^(?:MASTER SERVICES AGREEMENT|DATA PROCESSING (?:AGREEMENT|ADDENDUM)|"
    r"VENDOR AGREEMENT|PROFESSIONAL SERVICES AGREEMENT|SERVICE AGREEMENT|"
    r"EMPLOYMENT AGREEMENT|MUTUAL NON-DISCLOSURE AGREEMENT|NON-DISCLOSURE AGREEMENT)$",
    re.IGNORECASE,
)
SIGNATURE_HEADING = re.compile(r"^SIGNATURE PAGE$", re.IGNORECASE)
SCHEDULE_FIELD_HEADINGS = {
    "order number",
    "item",
    "details",
    "subscription",
    "users",
    "initial term",
    "annual fee",
    "implementation fee",
    "payment due",
    "availability target",
    "support",
    "data region",
}
INLINE_SCHEDULE_HEADING = re.compile(
    r"^(?:Special Terms|Security Certification|Model Training Opt-Out)\.\s+",
    re.IGNORECASE,
)


def _normalized_line(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip()


def _repeated_page_lines(pages: list[DocumentPage]) -> set[str]:
    counts: dict[str, int] = {}
    for page in pages:
        seen = {
            re.sub(r"\bpage\s+\d+\b", "page #", _normalized_line(line).lower())
            for line in page.text.splitlines()
            if 0 < len(_normalized_line(line)) <= 140
        }
        for line in seen:
            counts[line] = counts.get(line, 0) + 1
    threshold = max(2, len(pages) // 2)
    return {
        line
        for line, count in counts.items()
        if count >= threshold and not _looks_like_heading(line)
    }


def _clean_page_lines(page: DocumentPage, repeated: set[str]) -> list[str]:
    lines = []
    for raw_line in page.text.splitlines():
        line = _normalized_line(raw_line)
        normalized = re.sub(r"\bpage\s+\d+\b", "page #", line.lower())
        if not line or normalized in repeated or re.fullmatch(r"page\s+\d+", line, re.IGNORECASE):
            continue
        lines.append(line)
    return lines


def _is_contents_page(lines: list[str]) -> bool:
    opening = {line.upper() for line in lines[:8]}
    if "CONTENTS" not in opening and "TABLE OF CONTENTS" not in opening:
        return False
    short_entries = sum(
        bool(re.match(r"^(?:\d+(?:\.\d+)*|SCHEDULE|APPENDIX|EXHIBIT)\b", line, re.IGNORECASE))
        and len(line) < 100
        for line in lines
    )
    return short_entries >= 2


def _looks_like_heading(line: str) -> bool:
    return bool(
        SECTION_HEADING.match(line)
        or SCHEDULE_HEADING.match(line)
        or DOCUMENT_HEADING.match(line)
    )


def _is_schedule_field_heading(line: str) -> bool:
    return line.lower().strip(" :") in SCHEDULE_FIELD_HEADINGS


def extract_clauses(pages: list[DocumentPage]) -> list[Clause]:
    repeated = _repeated_page_lines(pages)
    clauses: list[Clause] = []
    current_lines: list[str] = []
    current_page = 1
    current_has_body = False
    ignore_remainder = False

    def flush() -> None:
        nonlocal current_lines, current_has_body
        text = re.sub(r"\s+", " ", " ".join(current_lines)).strip()
        if text and current_has_body and len(text) >= 15:
            clause_type, classification_confidence = classify_clause_with_confidence(text)
            clauses.append(
                Clause(
                    id=f"clause-{len(clauses) + 1}",
                    clause_type=clause_type,
                    text=text,
                    page=current_page,
                    confidence=classification_confidence,
                )
            )
        current_lines = []
        current_has_body = False

    for page in pages:
        lines = _clean_page_lines(page, repeated)
        if _is_contents_page(lines):
            continue
        for line in lines:
            if SIGNATURE_HEADING.match(line):
                flush()
                ignore_remainder = True
                break
            if ignore_remainder:
                continue
            if _is_schedule_field_heading(line):
                flush()
                current_lines = [line]
                current_page = page.page_number
                continue
            if INLINE_SCHEDULE_HEADING.match(line):
                flush()
                current_lines = [line]
                current_page = page.page_number
                current_has_body = True
                continue
            inline_clause = INLINE_NUMBERED_CLAUSE.match(line)
            if inline_clause:
                flush()
                current_lines = [
                    f"{inline_clause.group('section')}. {inline_clause.group('title')}",
                    inline_clause.group("body"),
                ]
                current_page = page.page_number
                current_has_body = True
                continue
            if _looks_like_heading(line):
                flush()
                current_lines = [line]
                current_page = page.page_number
                continue
            if not current_lines:
                current_page = page.page_number
            current_lines.append(line)
            current_has_body = True
    flush()
    return clauses
