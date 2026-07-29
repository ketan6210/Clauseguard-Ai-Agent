import json
import logging
import re
import uuid

import httpx

from app.core.config import settings
from app.schemas.review import Clause, Evidence, Finding, QuestionResponse


logger = logging.getLogger(__name__)
_CITATION_PATTERN = re.compile(r"\[([A-Za-z0-9_-]+)\]")
_JSON_FENCE_PATTERN = re.compile(
    r"```(?:json)?\s*(.*?)```",
    flags=re.IGNORECASE | re.DOTALL,
)
_MAX_JSON_RESPONSE_CHARS = 1_000_000
_MAX_JSON_DECODE_ATTEMPTS = 100
# Small batches keep local-model prompts bounded and isolate malformed responses.
_RESIDUAL_CLAUSE_BATCH_SIZE = 12
_RESIDUAL_FINDINGS_PER_BATCH = 2
_MAX_RESIDUAL_FINDINGS = 5
_MAX_EXISTING_TITLES_PER_BATCH = 40
_VERIFICATION_BATCH_SIZE = 8
_ALLOWED_RISK_CATEGORIES = {
    "termination",
    "indemnification",
    "limitation_of_liability",
    "auto_renewal",
    "data_use",
    "data_deletion",
    "data_breach_notification",
    "audit_rights",
    "payment_terms",
    "confidentiality",
    "intellectual_property",
    "non_compete",
    "publicity",
    "arbitration",
}
_RISK_CATEGORY_BY_CLAUSE_TYPE = {
    "liability": "limitation_of_liability",
    "renewal": "auto_renewal",
    "ai_training": "data_use",
    "data_licensing": "data_use",
    "publicity_rights": "publicity",
    "restrictive_covenants": "non_compete",
    "arbitration_costs": "arbitration",
    "dispute_resolution": "arbitration",
}


def _parse_json_payload(
    content: object,
    *,
    expected_array_key: str | None = None,
    allow_bare_array: bool = False,
) -> dict | list:
    """Decode one JSON object/array from a bounded local-model response."""
    if not isinstance(content, str):
        raise ValueError("Local model JSON content must be text")
    if not content.strip():
        raise ValueError("Local model returned empty JSON content")
    if len(content) > _MAX_JSON_RESPONSE_CHARS:
        raise ValueError("Local model JSON content exceeds the safety limit")

    text = re.sub(
        r"<think>.*?</think>",
        "",
        content,
        flags=re.IGNORECASE | re.DOTALL,
    ).strip("\ufeff \t\r\n")
    candidates = [match.group(1) for match in _JSON_FENCE_PATTERN.finditer(text)]
    candidates.append(text)
    decoder = json.JSONDecoder()
    attempts = 0
    for candidate in candidates:
        stripped = candidate.lstrip("\ufeff \t\r\n")
        starts = [0]
        starts.extend(
            match.start()
            for match in re.finditer(r"[\[{]", stripped)
            if match.start() != 0
        )
        for start in starts:
            attempts += 1
            if attempts > _MAX_JSON_DECODE_ATTEMPTS:
                raise ValueError("Local model JSON content has too many candidates")
            try:
                payload, _ = decoder.raw_decode(stripped, start)
            except json.JSONDecodeError:
                continue
            if expected_array_key is None:
                if isinstance(payload, (dict, list)):
                    return payload
                continue
            if isinstance(payload, dict):
                values = payload.get(expected_array_key)
            elif allow_bare_array and isinstance(payload, list):
                values = payload
            else:
                continue
            if isinstance(values, list) and all(
                isinstance(value, dict) for value in values
            ):
                return payload
    raise ValueError("Local model response did not contain valid JSON")


def _request_qwen_json(
    prompt: str,
    *,
    system_prompt: str,
    num_predict: int,
    expected_array_key: str,
    allow_bare_array: bool = False,
) -> dict | list:
    response = httpx.post(
        f"{settings.ollama_url.rstrip('/')}/api/chat",
        json={
            "model": settings.ollama_model,
            "stream": False,
            "think": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "options": {"temperature": 0, "num_predict": num_predict},
        },
        timeout=settings.ollama_timeout_seconds,
    )
    response.raise_for_status()
    body = response.json()
    if not isinstance(body, dict):
        raise ValueError("Local model response body must be an object")
    message = body.get("message")
    if not isinstance(message, dict):
        raise ValueError("Local model response is missing its message")
    return _parse_json_payload(
        message.get("content"),
        expected_array_key=expected_array_key,
        allow_bare_array=allow_bare_array,
    )


def _finding_key(clause_id: str | None, title: str) -> tuple[str, str]:
    return clause_id or "", " ".join(title.casefold().split())


def _batches(items: list, size: int):
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _unique_evidence(items: list[Evidence], limit: int = 5) -> list[Evidence]:
    unique = {}
    for item in items:
        if item.source_id not in unique:
            unique[item.source_id] = item
    return list(unique.values())[:limit]


def _extractive_answer(
    contract_citations: list[Evidence],
    policy_citations: list[Evidence],
) -> str:
    if not contract_citations:
        return (
            "I could not find a clearly relevant clause in this document. "
            "A human reviewer should verify the source contract."
        )
    contract_summary = " ".join(
        f"[{item.source_id}] {item.text}" for item in contract_citations[:3]
    )
    policy_summary = " ".join(
        f"[{item.source_id}] {item.text}" for item in policy_citations[:2]
    )
    answer = f"Relevant contract language: {contract_summary[:1500]}"
    if policy_summary:
        answer += f"\n\nRelevant company policy: {policy_summary[:700]}"
    return answer + "\n\nThis is an evidence retrieval result and requires human legal review."


def _ollama_answer(
    question: str,
    contract_citations: list[Evidence],
    policy_citations: list[Evidence],
) -> str | None:
    if not settings.ollama_enabled or not contract_citations:
        return None
    evidence = "\n".join(
        f"[{item.source_id}] {item.title} ({item.section}): {item.text}"
        for item in contract_citations + policy_citations
    )
    prompt = f"""/no_think
Question: {question}

Evidence:
{evidence}

Answer the question using only the evidence above. Cite every factual statement with
the exact evidence ID in square brackets, for example [clause-12]. Clearly distinguish
contract terms from company policy. If the evidence is insufficient, say so. Be concise,
do not invent terms or citations, and end with: "Human legal review is required."
"""
    try:
        response = httpx.post(
            f"{settings.ollama_url.rstrip('/')}/api/chat",
            json={
                "model": settings.ollama_model,
                "stream": False,
                "think": False,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are ClauseGuard, a contract-review assistant. "
                            "Ground every answer in the supplied evidence. "
                            "Return only the final answer, never analysis or reasoning."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                "options": {"temperature": 0.1, "num_predict": 500},
            },
            timeout=settings.ollama_timeout_seconds,
        )
        response.raise_for_status()
        answer = response.json()["message"]["content"].strip()
        answer = re.sub(r"<think>.*?</think>", "", answer, flags=re.DOTALL).strip()
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        logger.warning("Local Ollama generation failed; using extractive fallback: %s", exc)
        return None

    allowed_ids = {
        item.source_id for item in contract_citations + policy_citations
    }
    cited_ids = set(_CITATION_PATTERN.findall(answer))
    contract_ids = {item.source_id for item in contract_citations}
    if (
        not answer
        or not cited_ids
        or not cited_ids.issubset(allowed_ids)
        or not cited_ids.intersection(contract_ids)
        or not answer.endswith("Human legal review is required.")
    ):
        logger.warning("Local Ollama answer failed citation validation; using fallback")
        return None
    return answer


def answer_question(
    question: str,
    contract_evidence: list[Evidence],
    policy_evidence: list[Evidence],
) -> QuestionResponse:
    contract_citations = _unique_evidence(contract_evidence)
    policy_citations = _unique_evidence(policy_evidence, limit=3)
    answer = _ollama_answer(question, contract_citations, policy_citations)
    generation_mode = "local_llm" if answer else "extractive_fallback"
    answer = answer or _extractive_answer(contract_citations, policy_citations)
    citations = _unique_evidence(contract_citations + policy_citations, limit=8)
    return QuestionResponse(
        answer=answer,
        citations=citations,
        contract_citations=contract_citations,
        policy_citations=policy_citations,
        generation_mode=generation_mode,
    )


def generate_finding_explanation(clause, evidence, rule_result) -> str:
    return rule_result or "The clause differs from the retrieved company policy and requires human review."


def analyze_residual_risks(
    clauses: list[Clause],
    existing_findings: list[Finding],
) -> list[Finding]:
    """Run an optional, conservative second pass over exact extracted clauses."""
    if not settings.ollama_enabled or not settings.llm_risk_second_pass_enabled:
        return []
    unique_clauses = []
    seen_clause_ids = set()
    for clause in clauses:
        if clause.id in seen_clause_ids:
            continue
        seen_clause_ids.add(clause.id)
        unique_clauses.append(clause)
    existing_pairs = {
        _finding_key(item.clause_id, item.title) for item in existing_findings
    }
    clause_types = {
        clause.id: _RISK_CATEGORY_BY_CLAUSE_TYPE.get(
            clause.clause_type, clause.clause_type
        )
        for clause in unique_clauses
    }
    existing_clause_categories = {
        (item.clause_id, clause_types.get(item.clause_id or ""))
        for item in existing_findings
        if item.clause_id
    }
    findings = []

    for batch_number, clause_batch in enumerate(
        _batches(unique_clauses, _RESIDUAL_CLAUSE_BATCH_SIZE),
        start=1,
    ):
        batch_clause_map = {clause.id: clause for clause in clause_batch}
        clause_text = "\n".join(
            f"[{clause.id}] type={clause.clause_type}; page={clause.page}; "
            f"text={clause.text[:800]}"
            for clause in clause_batch
        )
        existing_titles = sorted(
            {
                item.title[:200]
                for item in existing_findings
                if item.clause_id in batch_clause_map
            }
        )[:_MAX_EXISTING_TITLES_PER_BATCH]
        prompt = f"""/no_think
Review only the contract clauses below for material risks missed by a deterministic
rule engine. Return one JSON object with a "findings" array only. Each finding object
must contain clause_id, title,
category, severity, confidence, explanation, and recommended_action. Only report a
risk directly supported by the exact clause. Allowed categories:
{", ".join(sorted(_ALLOWED_RISK_CATEGORIES))}. Allowed severities: Low, Medium,
High, Critical. Confidence must be a number from 0 to 1. Do not repeat existing
findings for these clauses: {", ".join(existing_titles) or "none"}.
Return at most {_RESIDUAL_FINDINGS_PER_BATCH} findings for this batch. Prefer an
empty array over a speculative finding.

Clauses:
{clause_text}
"""
        try:
            payload = _request_qwen_json(
                prompt,
                system_prompt=(
                    "You are a conservative contract risk reviewer. "
                    "Return grounded JSON only, never reasoning."
                ),
                num_predict=2000,
                expected_array_key="findings",
                allow_bare_array=True,
            )
            if isinstance(payload, list):
                items = payload
            else:
                items = payload.get("findings", [])
            if not isinstance(items, list):
                raise ValueError("Risk response findings must be an array")
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            logger.warning(
                "Local LLM risk second-pass batch %s failed: %s",
                batch_number,
                exc,
            )
            continue

        for item in items[:_RESIDUAL_FINDINGS_PER_BATCH]:
            if not isinstance(item, dict):
                continue
            clause = batch_clause_map.get(str(item.get("clause_id", "")))
            title = str(item.get("title", "")).strip()
            category = str(item.get("category", "")).strip()
            severity = str(item.get("severity", "")).strip()
            try:
                confidence = float(item.get("confidence", 0))
            except (TypeError, ValueError):
                continue
            finding_key = _finding_key(clause.id if clause else None, title)
            if (
                clause is None
                or not title
                or category not in _ALLOWED_RISK_CATEGORIES
                or severity not in {"Low", "Medium", "High", "Critical"}
                or not 0 <= confidence <= 1
                or confidence < settings.llm_risk_min_confidence
                or finding_key in existing_pairs
                or (clause.id, category) in existing_clause_categories
            ):
                continue
            existing_pairs.add(finding_key)
            existing_clause_categories.add((clause.id, category))
            if len(findings) >= _MAX_RESIDUAL_FINDINGS:
                continue
            finding_uuid = uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"{clause.id}:{finding_key[1]}",
            )
            findings.append(
                Finding(
                    id=f"llm-{finding_uuid}",
                    clause_id=clause.id,
                    title=title,
                    risk_level=severity,
                    confidence=min(confidence, 0.9),
                    explanation=str(item.get("explanation", "")).strip(),
                    recommended_action=str(
                        item.get("recommended_action", "")
                    ).strip(),
                    contract_excerpt=clause.text[:1000],
                    analysis_source="local_llm",
                )
            )
    return findings


def verify_findings_with_qwen(
    findings: list[Finding],
    clauses: list[Clause],
) -> dict[str, dict]:
    """Return validated model assessments; never let the model set the final score."""
    if (
        not settings.ollama_enabled
        or not settings.llm_finding_verification_enabled
        or not findings
    ):
        return {}
    clause_map = {clause.id: clause for clause in clauses}
    clause_inventory = [
        {"id": clause.id, "type": clause.clause_type, "page": clause.page}
        for clause in clauses
    ]
    records = []
    allowed_evidence: dict[str, set[str]] = {}
    seen_finding_ids = set()
    for finding in findings:
        if finding.id in seen_finding_ids:
            continue
        seen_finding_ids.add(finding.id)
        clause = clause_map.get(finding.clause_id or "")
        evidence_ids = {item.source_id for item in finding.evidence}
        if clause:
            evidence_ids.add(clause.id)
        allowed_evidence[finding.id] = evidence_ids
        records.append(
            {
                "finding_id": finding.id,
                "title": finding.title[:200],
                "explanation": finding.explanation[:800],
                "clause_id": finding.clause_id,
                "contract_text": (
                    clause.text[:900]
                    if clause
                    else finding.contract_excerpt[:900]
                ),
                "clause_inventory": clause_inventory if clause is None else [],
                "policy_evidence": [
                    {"id": item.source_id, "text": item.text[:500]}
                    for item in finding.evidence[:3]
                ],
            }
        )
    # Each batch is independently validated; a timeout or malformed response does
    # not discard assessments already accepted from other batches.
    verified = {}
    for batch_number, record_batch in enumerate(
        _batches(records, _VERIFICATION_BATCH_SIZE),
        start=1,
    ):
        prompt = f"""/no_think
Verify whether each proposed contract finding is directly supported by its supplied
contract text and policy evidence. Return JSON only as an object with a "results"
array. Each result must contain finding_id, supported (boolean), ambiguity
("low", "medium", or "high"), policy_stance ("violates", "compliant", or
"insufficient"), and evidence_ids (only IDs supplied in that finding).
For a supported clause finding, cite its exact clause ID. When policy evidence is
provided, also cite at least one supplied policy ID. Do not assess legal severity
and do not invent evidence IDs.

Findings:
{json.dumps(record_batch)}
"""
        try:
            payload = _request_qwen_json(
                prompt,
                system_prompt=(
                    "You verify evidence support conservatively. "
                    "Return structured JSON only."
                ),
                num_predict=1800,
                expected_array_key="results",
            )
            results = payload.get("results", []) if isinstance(payload, dict) else []
            if not isinstance(results, list):
                raise ValueError("Verification results must be an array")
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            logger.warning(
                "Local Qwen finding-verification batch %s failed: %s",
                batch_number,
                exc,
            )
            continue

        batch_finding_ids = {str(record["finding_id"]) for record in record_batch}
        for item in results:
            if not isinstance(item, dict):
                continue
            finding_id = str(item.get("finding_id", ""))
            ambiguity = str(item.get("ambiguity", ""))
            policy_stance = str(item.get("policy_stance", ""))
            supported = item.get("supported")
            raw_evidence_ids = item.get("evidence_ids", [])
            if (
                finding_id not in batch_finding_ids
                or finding_id in verified
                or ambiguity not in {"low", "medium", "high"}
                or policy_stance not in {"violates", "compliant", "insufficient"}
                or not isinstance(supported, bool)
                or not isinstance(raw_evidence_ids, list)
                or not all(isinstance(value, str) for value in raw_evidence_ids)
            ):
                continue
            evidence_ids = set(raw_evidence_ids)
            record = next(
                value for value in record_batch
                if value["finding_id"] == finding_id
            )
            required_clause_id = record.get("clause_id")
            policy_ids = {
                value["id"] for value in record.get("policy_evidence", [])
            }
            if (
                # Positive verification requires the exact contract clause and,
                # when supplied, at least one applicable policy citation.
                not evidence_ids.issubset(allowed_evidence.get(finding_id, set()))
                or (supported and not evidence_ids)
                or (supported and required_clause_id and required_clause_id not in evidence_ids)
                or (supported and policy_ids and not evidence_ids.intersection(policy_ids))
            ):
                continue
            verified[finding_id] = {
                "supported": supported,
                "ambiguity": ambiguity,
                "policy_stance": policy_stance,
                "evidence_ids": sorted(evidence_ids),
            }
    return verified
