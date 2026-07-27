import re
from collections.abc import Callable

from app.schemas.review import Clause, Finding
from app.services.number_parser import extract_measurements, extract_percentages


def _sentences(text: str) -> list[str]:
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.;])\s+(?=[A-Z])|\n+", text)
        if sentence.strip()
    ]


def _duration_hours(sentence: str) -> list[int]:
    values = []
    for item in extract_measurements(sentence):
        if item.unit == "hours":
            values.append(round(item.value))
        elif item.unit == "days":
            values.append(round(item.value * 24))
        elif item.unit == "weeks":
            values.append(round(item.value * 7 * 24))
        elif item.unit == "months":
            values.append(round(item.value * 30 * 24))
    return values


def _duration_days(sentence: str) -> list[int]:
    return [
        round(item.days)
        for item in extract_measurements(sentence)
        if item.unit in {"hours", "days", "weeks", "months", "years"}
    ]


def _collect(
    clauses: list[Clause],
    sentence_matches: Callable[[str], bool],
    value_parser: Callable[[str], list[float | int]],
) -> list[tuple[Clause, str, float | int]]:
    results = []
    for clause in clauses:
        for sentence in _sentences(clause.text):
            lowered = sentence.lower()
            if sentence_matches(lowered):
                results.extend((clause, sentence, value) for value in value_parser(sentence))
    return results


def _conflict_finding(
    title: str,
    risk_level: str,
    explanation: str,
    action: str,
    matches: list[tuple[Clause, str, float | int]],
) -> Finding:
    clauses = []
    excerpts = []
    for clause, sentence, _ in matches:
        if clause.id not in clauses:
            clauses.append(clause.id)
        if sentence not in excerpts:
            excerpts.append(sentence)
    return Finding(
        id=f"finding-conflict-{re.sub('[^a-z]+', '-', title.lower()).strip('-')}",
        clause_id=clauses[0] if clauses else None,
        title=title,
        risk_level=risk_level,
        confidence=0.9,
        explanation=explanation,
        recommended_action=action,
        contract_excerpt=" | ".join(excerpts)[:1000],
        evidence=[],
    )


def _append_value_conflict(
    findings: list[Finding],
    matches: list[tuple[Clause, str, float | int]],
    title: str,
    risk_level: str,
    unit: str,
    action: str,
) -> None:
    values = sorted({value for _, _, value in matches})
    if len(values) < 2:
        return
    rendered = ", ".join(f"{value:g}" if isinstance(value, float) else str(value) for value in values)
    findings.append(
        _conflict_finding(
            title,
            risk_level,
            f"The document contains inconsistent values: {rendered} {unit}.",
            action,
            matches,
        )
    )


def detect_clause_conflicts(clauses: list[Clause]) -> list[Finding]:
    findings: list[Finding] = []

    payment_matches = _collect(
        clauses,
        lambda sentence: any(term in sentence for term in ("invoice", "payment terms", "amounts are due", "payable net")),
        lambda sentence: [
            *[int(value) for value in re.findall(r"\bnet\s*[-:]?\s*(\d{1,3})\b", sentence, re.IGNORECASE)],
            *_duration_days(sentence),
        ],
    )
    _append_value_conflict(
        findings,
        payment_matches,
        "Conflicting payment terms",
        "High",
        "days",
        "Choose one controlling invoice-payment period and align the agreement and Order Form.",
    )

    deletion_matches = _collect(
        clauses,
        lambda sentence: any(term in sentence for term in ("delete", "deletion", "retain customer data", "return customer data")),
        _duration_days,
    )
    _append_value_conflict(
        findings,
        deletion_matches,
        "Conflicting data deletion periods",
        "High",
        "days",
        "Use one controlling deletion period and state how backups, models, logs, and derived data are handled.",
    )

    breach_matches = _collect(
        clauses,
        lambda sentence: ("security incident" in sentence or "data breach" in sentence)
        and any(term in sentence for term in ("notify", "notice", "notification")),
        _duration_hours,
    )
    _append_value_conflict(
        findings,
        breach_matches,
        "Conflicting breach notification periods",
        "High",
        "hours",
        "Use a single notification deadline no longer than 72 hours across the MSA and DPA.",
    )

    uptime_matches = _collect(
        clauses,
        lambda sentence: "uptime" in sentence or "availability" in sentence,
        lambda sentence: [value for value in extract_percentages(sentence) if value >= 90],
    )
    _append_value_conflict(
        findings,
        uptime_matches,
        "Conflicting service-level commitments",
        "Medium",
        "percent",
        "Align the uptime commitment, measurement method, exclusions, and remedies in every schedule.",
    )

    cure_matches = _collect(
        clauses,
        lambda sentence: ("terminate" in sentence or "termination" in sentence) and "cure" in sentence,
        _duration_days,
    )
    _append_value_conflict(
        findings,
        cure_matches,
        "Conflicting termination cure periods",
        "High",
        "days",
        "Set consistent cure periods or state clearly which provision controls.",
    )

    precedence = [
        (clause, sentence, 1)
        for clause in clauses
        for sentence in _sentences(clause.text)
        if any(term in sentence.lower() for term in ("will control", "controls over", "order of precedence"))
    ]
    controlling_subjects = set()
    for _, sentence, _ in precedence:
        lowered = sentence.lower()
        if "order form" in lowered and "control" in lowered:
            controlling_subjects.add("Order Form")
        if ("data processing addendum" in lowered or "dpa" in lowered) and "control" in lowered:
            controlling_subjects.add("Data Processing Addendum")
        if "agreement controls" in lowered or "agreement will control" in lowered:
            controlling_subjects.add("Master Agreement")
    if len(controlling_subjects) > 1:
        findings.append(
            _conflict_finding(
                "Conflicting document precedence",
                "High",
                f"Multiple documents are described as controlling: {', '.join(sorted(controlling_subjects))}.",
                "Add one unambiguous order-of-precedence clause covering the MSA and every schedule.",
                precedence,
            )
        )

    return findings
