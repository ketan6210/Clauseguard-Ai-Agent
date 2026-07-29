import json

import pytest

from app.schemas.review import Clause, Evidence, Finding
from app.services import llm_service


def _clause(number: int) -> Clause:
    return Clause(
        id=f"clause-{number}",
        clause_type="publicity",
        text=f"Provider may use Customer logo in campaign {number}.",
        page=number,
        confidence=0.9,
    )


def _finding(number: int, clause: Clause) -> Finding:
    return Finding(
        id=f"finding-{number}",
        clause_id=clause.id,
        title=f"Publicity risk {number}",
        risk_level="Medium",
        confidence=0.8,
        explanation="The provider can use the customer logo.",
        recommended_action="Require written consent.",
        contract_excerpt=clause.text,
        evidence=[
            Evidence(
                source_id=f"policy-{number}",
                title="Publicity policy",
                section="Marketing",
                text="Written consent is required.",
                score=0.8,
            )
        ],
    )


class _Response:
    def __init__(self, content: str):
        self.content = content

    def raise_for_status(self):
        return None

    def json(self):
        return {"message": {"content": self.content}}


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (
            '```json\n{"results": [{"finding_id": "f-1"}]}\n```\nDone.',
            {"results": [{"finding_id": "f-1"}]},
        ),
        (
            'Use [1] as an example. Actual output: {"results": []} trailing text',
            {"results": []},
        ),
        (
            '<think>private analysis</think>\ufeff[{"title": "A {safe} title"}]',
            [{"title": "A {safe} title"}],
        ),
    ],
)
def test_parse_json_payload_handles_local_model_wrappers(content, expected):
    key = "results" if isinstance(expected, dict) else "findings"

    payload = llm_service._parse_json_payload(
        content,
        expected_array_key=key,
        allow_bare_array=True,
    )

    assert payload == expected


def test_parse_json_payload_rejects_malformed_or_wrong_shape():
    with pytest.raises(ValueError):
        llm_service._parse_json_payload(
            "The answer is null.",
            expected_array_key="results",
        )
    with pytest.raises(ValueError):
        llm_service._parse_json_payload(
            '{"unrelated": []}',
            expected_array_key="results",
        )


def test_residual_risk_batches_continue_after_failure_and_deduplicate(monkeypatch):
    clauses = [_clause(1), _clause(2)]
    calls = []

    def fake_post(*args, **kwargs):
        calls.append(kwargs["json"])
        if len(calls) == 1:
            return _Response("truncated {")
        item = {
            "clause_id": "clause-2",
            "title": " Broad   publicity right ",
            "category": "publicity",
            "severity": "Medium",
            "confidence": 0.82,
            "explanation": "The provider may use the customer logo.",
            "recommended_action": "Require prior written consent.",
        }
        duplicate = {**item, "title": "broad publicity RIGHT"}
        return _Response(f"```json\n{json.dumps([item, duplicate])}\n```\nDone")

    monkeypatch.setattr(llm_service.settings, "ollama_enabled", True)
    monkeypatch.setattr(llm_service.settings, "llm_risk_second_pass_enabled", True)
    monkeypatch.setattr(llm_service, "_RESIDUAL_CLAUSE_BATCH_SIZE", 1)
    monkeypatch.setattr(llm_service.httpx, "post", fake_post)

    findings = llm_service.analyze_residual_risks(clauses, [])

    assert len(calls) == 2
    assert [item.clause_id for item in findings] == ["clause-2"]
    assert findings[0].title == "Broad   publicity right"


def test_residual_risk_deduplicates_input_clauses_and_existing_findings(monkeypatch):
    clause = _clause(1)
    existing = _finding(1, clause).model_copy(
        update={"title": "  Broad PUBLICITY   right "}
    )
    calls = []
    response_item = {
        "clause_id": clause.id,
        "title": "broad publicity right",
        "category": "publicity",
        "severity": "Medium",
        "confidence": 0.82,
        "explanation": "The provider may use the customer logo.",
        "recommended_action": "Require prior written consent.",
    }

    def fake_post(*args, **kwargs):
        calls.append(kwargs["json"])
        return _Response(json.dumps([response_item]))

    monkeypatch.setattr(llm_service.settings, "ollama_enabled", True)
    monkeypatch.setattr(llm_service.settings, "llm_risk_second_pass_enabled", True)
    monkeypatch.setattr(llm_service.httpx, "post", fake_post)

    findings = llm_service.analyze_residual_risks([clause, clause], [existing])

    assert len(calls) == 1
    assert findings == []


def test_residual_risk_suppresses_same_clause_category_duplicate(monkeypatch):
    clause = Clause(
        id="clause-liability",
        clause_type="liability",
        text="Provider liability is capped at three months of fees.",
        confidence=0.9,
    )
    existing = _finding(1, clause).model_copy(
        update={"clause_id": clause.id, "title": "Liability cap below policy"}
    )
    response_item = {
        "clause_id": clause.id,
        "title": "Limitation of Liability",
        "category": "limitation_of_liability",
        "severity": "High",
        "confidence": 0.9,
        "explanation": "The cap is narrow.",
        "recommended_action": "Increase the cap.",
    }
    monkeypatch.setattr(llm_service.settings, "ollama_enabled", True)
    monkeypatch.setattr(llm_service.settings, "llm_risk_second_pass_enabled", True)
    monkeypatch.setattr(
        llm_service.httpx,
        "post",
        lambda *args, **kwargs: _Response(
            json.dumps({"findings": [response_item]})
        ),
    )

    assert llm_service.analyze_residual_risks([clause], [existing]) == []


def test_verification_batches_all_findings_and_preserves_other_batches(monkeypatch):
    clause = _clause(1)
    findings = [_finding(number, clause) for number in range(81)]
    calls = []

    def fake_post(*args, **kwargs):
        prompt = kwargs["json"]["messages"][1]["content"]
        records = json.loads(prompt.split("Findings:\n", 1)[1])
        calls.append(records)
        if len(calls) == 2:
            return _Response('{"results": [')
        results = [
            {
                "finding_id": record["finding_id"],
                "supported": True,
                "ambiguity": "low",
                "policy_stance": "violates",
                "evidence_ids": [clause.id, record["policy_evidence"][0]["id"]],
            }
            for record in records
        ]
        return _Response(
            f"```json\n{json.dumps({'results': results})}\n```\nVerified."
        )

    monkeypatch.setattr(llm_service.settings, "ollama_enabled", True)
    monkeypatch.setattr(
        llm_service.settings,
        "llm_finding_verification_enabled",
        True,
    )
    monkeypatch.setattr(llm_service, "_VERIFICATION_BATCH_SIZE", 20)
    monkeypatch.setattr(llm_service.httpx, "post", fake_post)

    verified = llm_service.verify_findings_with_qwen(findings, [clause])

    assert [len(batch) for batch in calls] == [20, 20, 20, 20, 1]
    assert len(verified) == 61
    assert "finding-20" not in verified
    assert "finding-40" in verified
    assert "finding-80" in verified


def test_verification_rejects_cross_batch_ids_and_malformed_evidence(monkeypatch):
    clause = _clause(1)
    findings = [_finding(number, clause) for number in range(3)]
    calls = []

    def fake_post(*args, **kwargs):
        calls.append(kwargs["json"])
        if len(calls) == 1:
            results = [
                {
                    "finding_id": "finding-0",
                    "supported": True,
                    "ambiguity": "low",
                    "policy_stance": "violates",
                    "evidence_ids": [clause.id, "policy-0"],
                },
                {
                    "finding_id": "finding-1",
                    "supported": True,
                    "ambiguity": "low",
                    "policy_stance": "violates",
                    "evidence_ids": clause.id,
                },
                {
                    "finding_id": "finding-2",
                    "supported": True,
                    "ambiguity": "low",
                    "policy_stance": "violates",
                    "evidence_ids": [clause.id, "policy-2"],
                },
            ]
        else:
            results = [
                {
                    "finding_id": "finding-2",
                    "supported": True,
                    "ambiguity": "low",
                    "policy_stance": "violates",
                    "evidence_ids": ["invented-evidence"],
                }
            ]
        return _Response(json.dumps({"results": results}))

    monkeypatch.setattr(llm_service.settings, "ollama_enabled", True)
    monkeypatch.setattr(
        llm_service.settings,
        "llm_finding_verification_enabled",
        True,
    )
    monkeypatch.setattr(llm_service, "_VERIFICATION_BATCH_SIZE", 2)
    monkeypatch.setattr(llm_service.httpx, "post", fake_post)

    verified = llm_service.verify_findings_with_qwen(findings, [clause])

    assert set(verified) == {"finding-0"}
