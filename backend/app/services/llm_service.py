import logging
import re

import httpx

from app.core.config import settings
from app.schemas.review import Evidence, QuestionResponse


logger = logging.getLogger(__name__)
_CITATION_PATTERN = re.compile(r"\[([A-Za-z0-9_-]+)\]")


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
