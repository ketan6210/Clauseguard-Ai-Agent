from app.schemas.review import Clause
from app.services import llm_service


CLAUSE = Clause(
    id="clause-7",
    clause_type="publicity",
    text="Provider may use Customer's name and logo in all marketing.",
    page=2,
    confidence=0.9,
)


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "message": {
                "content": (
                    '[{"clause_id":"clause-7","title":"Broad publicity right",'
                    '"category":"publicity","severity":"Medium","confidence":0.82,'
                    '"explanation":"The provider may use the customer logo.",'
                    '"recommended_action":"Require prior written consent."}]'
                )
            }
        }


def test_llm_second_pass_accepts_only_grounded_clause_findings(monkeypatch):
    monkeypatch.setattr(llm_service.settings, "ollama_enabled", True)
    monkeypatch.setattr(llm_service.settings, "llm_risk_second_pass_enabled", True)
    monkeypatch.setattr(llm_service.httpx, "post", lambda *args, **kwargs: FakeResponse())

    findings = llm_service.analyze_residual_risks([CLAUSE], [])

    assert len(findings) == 1
    assert findings[0].clause_id == "clause-7"
    assert findings[0].analysis_source == "local_llm"
    assert findings[0].contract_excerpt == CLAUSE.text


def test_llm_second_pass_rejects_unknown_clause(monkeypatch):
    monkeypatch.setattr(llm_service.settings, "ollama_enabled", True)
    monkeypatch.setattr(llm_service.settings, "llm_risk_second_pass_enabled", True)

    class UnknownClauseResponse(FakeResponse):
        def json(self):
            value = super().json()
            value["message"]["content"] = value["message"]["content"].replace(
                "clause-7", "invented-clause"
            )
            return value

    monkeypatch.setattr(
        llm_service.httpx, "post", lambda *args, **kwargs: UnknownClauseResponse()
    )

    assert llm_service.analyze_residual_risks([CLAUSE], []) == []
