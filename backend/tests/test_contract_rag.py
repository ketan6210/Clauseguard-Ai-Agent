from qdrant_client import QdrantClient

from app.schemas.review import Clause
from app.services import contract_store
from app.services import llm_service
from app.services.llm_service import answer_question


CLAUSES = [
    Clause(
        id="clause-breach",
        clause_type="data_breach_notification",
        text="Provider will notify Customer within five days after a data breach.",
        page=4,
        confidence=0.9,
    ),
    Clause(
        id="clause-payment",
        clause_type="payment_terms",
        text="Invoices are payable Net 30.",
        page=2,
        confidence=0.9,
    ),
]


def test_contract_clause_qdrant_round_trip(monkeypatch):
    client = QdrantClient(location=":memory:")

    def fake_embed(texts):
        return [
            [1.0, 0.0] if "breach" in text.lower() else [0.0, 1.0]
            for text in texts
        ]

    monkeypatch.setattr(contract_store, "_qdrant_client", lambda: client)
    monkeypatch.setattr(contract_store, "_embed", fake_embed)
    monkeypatch.setattr(contract_store.settings, "qdrant_enabled", True)
    contract_store._indexed_reviews.clear()

    assert contract_store.index_contract_clauses("review-rag", CLAUSES)
    results = contract_store.search_contract_clauses(
        "review-rag",
        "What is the breach notice?",
        CLAUSES,
        limit=1,
    )

    assert results[0].source_id == "clause-breach"
    assert "page 4" in results[0].section


def test_contract_search_has_no_cost_local_fallback(monkeypatch):
    monkeypatch.setattr(contract_store.settings, "qdrant_enabled", False)

    results = contract_store.search_contract_clauses(
        "review-local",
        "When must invoices be paid?",
        CLAUSES,
    )

    assert results[0].source_id == "clause-payment"


def test_extractive_rag_answer_separates_citation_types(monkeypatch):
    monkeypatch.setattr(contract_store.settings, "qdrant_enabled", False)
    monkeypatch.setattr(llm_service.settings, "ollama_enabled", False)
    contract = contract_store.local_clause_search("data breach notice", CLAUSES)
    response = answer_question("What is the breach notice?", contract, [])

    assert "[clause-breach]" in response.answer
    assert response.generation_mode == "extractive_fallback"
    assert response.contract_citations[0].source_id == "clause-breach"
    assert response.policy_citations == []
    assert response.citations == response.contract_citations


def test_local_llm_answer_accepts_grounded_citations(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "message": {
                    "content": (
                        "The provider must notify the customer within five days "
                        "[clause-breach]. Human legal review is required."
                    )
                }
            }

    monkeypatch.setattr(llm_service.settings, "ollama_enabled", True)
    monkeypatch.setattr(llm_service.httpx, "post", lambda *args, **kwargs: FakeResponse())
    contract = contract_store.local_clause_search("data breach notice", CLAUSES)

    response = answer_question("What is the breach notice?", contract, [])

    assert response.generation_mode == "local_llm"
    assert "[clause-breach]" in response.answer


def test_local_llm_rejects_invented_citations(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "message": {
                    "content": (
                        "Notice is immediate [invented-clause]. "
                        "Human legal review is required."
                    )
                }
            }

    monkeypatch.setattr(llm_service.settings, "ollama_enabled", True)
    monkeypatch.setattr(llm_service.httpx, "post", lambda *args, **kwargs: FakeResponse())
    contract = contract_store.local_clause_search("data breach notice", CLAUSES)

    response = answer_question("What is the breach notice?", contract, [])

    assert response.generation_mode == "extractive_fallback"
    assert "[clause-breach]" in response.answer
