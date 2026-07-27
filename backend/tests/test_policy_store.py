from types import SimpleNamespace

from qdrant_client import QdrantClient

from app.services import policy_store


def test_policy_library_covers_core_rag_categories():
    categories = {policy["category"] for policy in policy_store.load_policies()}

    assert {
        "ai_training",
        "data_licensing",
        "security_controls",
        "business_continuity",
        "insurance",
        "subprocessors",
        "indemnification",
        "service_levels",
        "publicity_rights",
        "arbitration_costs",
    } <= categories


def test_vector_search_uses_qdrant_payload(monkeypatch):
    hit = SimpleNamespace(
        payload={
            "id": "POL-AUDIT-001",
            "title": "Audit Rights Policy",
            "category": "audit_rights",
            "section": "Assurance",
            "text": "The company must have the right to audit vendor security controls annually.",
            "approved_clause": "Company may audit Vendor annually.",
        },
        score=0.91,
    )
    monkeypatch.setattr(policy_store, "_ensure_index_ready", lambda: True)
    monkeypatch.setattr(policy_store, "_embed", lambda texts: [[0.1, 0.2]])
    monkeypatch.setattr(policy_store, "_query_qdrant", lambda vector, limit: [hit])

    results = policy_store.vector_search("Can we inspect the vendor controls?")

    assert results[0].source_id == "POL-AUDIT-001"
    assert results[0].score == 0.91


def test_vector_search_falls_back_without_qdrant(monkeypatch):
    monkeypatch.setattr(policy_store, "_ensure_index_ready", lambda: False)

    results = policy_store.vector_search("erase customer information")

    assert results
    assert results[0].source_id == "POL-DELETE-001"


def test_hybrid_search_boosts_matching_category(monkeypatch):
    monkeypatch.setattr(policy_store, "_ensure_index_ready", lambda: False)

    results = policy_store.hybrid_search(
        "Vendor requirements and company policy",
        category="liability",
        limit=3,
    )

    assert results[0].source_id == "POL-LIABILITY-001"
    assert results[0].score == 1.0


def test_policy_index_round_trip_with_in_memory_qdrant(monkeypatch):
    client = QdrantClient(location=":memory:")
    policies = policy_store.load_policies()
    audit_index = next(index for index, policy in enumerate(policies) if policy["id"] == "POL-AUDIT-001")

    def fake_embed(texts):
        if len(texts) == 1:
            return [[1.0, 0.0]]
        return [[1.0, 0.0] if index == audit_index else [0.0, 1.0] for index, _ in enumerate(texts)]

    monkeypatch.setattr(policy_store, "_qdrant_client", lambda: client)
    monkeypatch.setattr(policy_store, "_embed", fake_embed)
    policy_store.index_policies()
    monkeypatch.setattr(policy_store, "_ensure_index_ready", lambda: True)

    results = policy_store.vector_search("audit vendor security controls", limit=1)

    assert results[0].source_id == "POL-AUDIT-001"
