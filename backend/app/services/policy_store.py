import json
import logging
import math
import re
import uuid
from functools import lru_cache
from pathlib import Path

from app.core.config import settings
from app.schemas.review import Evidence


POLICY_PATH = Path(__file__).resolve().parents[1] / "data" / "policies.json"
logger = logging.getLogger(__name__)


def load_policies() -> list[dict]:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def keyword_search(query: str, limit: int = 5) -> list[Evidence]:
    query_tokens = _tokens(query)
    scored = []
    for policy in load_policies():
        corpus = _tokens(" ".join((policy["title"], policy["category"], policy["text"], policy["approved_clause"])))
        overlap = len(query_tokens & corpus)
        score = overlap / math.sqrt(max(1, len(query_tokens) * len(corpus)))
        if score:
            scored.append(_evidence(policy, score))
    return sorted(scored, key=lambda item: item.score, reverse=True)[:limit]


def _evidence(policy: dict, score: float) -> Evidence:
    return Evidence(source_id=policy["id"], title=policy["title"], section=policy["section"], text=policy["text"], score=round(score, 4))


def _fallback_vector_search(query: str, limit: int = 5) -> list[Evidence]:
    synonyms = {"incident": "breach notification security", "erase": "delete deletion", "invoice": "payment net", "inspect": "audit", "renew": "renewal cancellation", "cap": "liability fees"}
    expanded = query.lower() + " " + " ".join(value for key, value in synonyms.items() if key in query.lower())
    return keyword_search(expanded, limit)


def _policy_document(policy: dict) -> str:
    return "\n".join((policy["title"], policy["category"].replace("_", " "), policy["text"], policy["approved_clause"]))


@lru_cache
def _embedding_model():
    from fastembed import TextEmbedding

    return TextEmbedding(model_name=settings.embedding_model)


@lru_cache
def _qdrant_client():
    from qdrant_client import QdrantClient

    return QdrantClient(url=settings.qdrant_url, timeout=5, check_compatibility=False)


def _embed(texts: list[str]) -> list[list[float]]:
    return [vector.tolist() if hasattr(vector, "tolist") else list(vector) for vector in _embedding_model().embed(texts)]


def ensure_collection(vector_size: int | None = None) -> None:
    from qdrant_client.models import Distance, VectorParams

    client = _qdrant_client()
    if client.collection_exists(settings.qdrant_collection):
        return
    if vector_size is None:
        vector_size = len(_embed(["ClauseGuard policy index"])[0])
    client.create_collection(
        collection_name=settings.qdrant_collection,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )


def index_policies() -> None:
    from qdrant_client.models import PointStruct

    # Check connectivity before loading a potentially large embedding model.
    _qdrant_client().get_collections()
    policies = load_policies()
    vectors = _embed([_policy_document(policy) for policy in policies])
    if not vectors:
        return
    ensure_collection(len(vectors[0]))
    points = [
        PointStruct(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"clauseguard:{policy['id']}")),
            vector=vector,
            payload=policy,
        )
        for policy, vector in zip(policies, vectors, strict=True)
    ]
    _qdrant_client().upsert(collection_name=settings.qdrant_collection, points=points, wait=True)


@lru_cache(maxsize=1)
def _ensure_index_ready() -> bool:
    if not settings.qdrant_enabled:
        return False
    try:
        index_policies()
        return True
    except Exception as exc:
        logger.warning("Qdrant vector retrieval unavailable; using local fallback: %s", exc)
        return False


def _query_qdrant(vector: list[float], limit: int):
    client = _qdrant_client()
    if hasattr(client, "query_points"):
        response = client.query_points(
            collection_name=settings.qdrant_collection,
            query=vector,
            limit=limit,
            with_payload=True,
        )
        return response.points
    return client.search(
        collection_name=settings.qdrant_collection,
        query_vector=vector,
        limit=limit,
        with_payload=True,
    )


def vector_search(query: str, limit: int = 5) -> list[Evidence]:
    if not query.strip() or limit < 1:
        return []
    if not _ensure_index_ready():
        return _fallback_vector_search(query, limit)
    try:
        hits = _query_qdrant(_embed([query])[0], limit)
        return [_evidence(hit.payload, float(hit.score)) for hit in hits if hit.payload]
    except Exception as exc:
        logger.warning("Qdrant query failed; using local fallback: %s", exc)
        return _fallback_vector_search(query, limit)


def hybrid_search(query: str, category: str | None = None, limit: int = 5) -> list[Evidence]:
    if limit < 1:
        return []
    policies_by_id = {policy["id"]: policy for policy in load_policies()}
    results: dict[str, Evidence] = {}
    scores: dict[str, float] = {}
    candidate_limit = max(limit * 3, 10)
    # Reciprocal rank fusion keeps scores comparable across vector and lexical engines.
    for result_set in (vector_search(query, candidate_limit), keyword_search(query, candidate_limit)):
        for rank, item in enumerate(result_set, start=1):
            results[item.source_id] = item
            scores[item.source_id] = scores.get(item.source_id, 0.0) + 1 / (60 + rank)
    for source_id in scores:
        if category and policies_by_id.get(source_id, {}).get("category") == category:
            scores[source_id] += 0.02
    ranked = sorted(scores, key=scores.get, reverse=True)[:limit]
    max_score = max((scores[source_id] for source_id in ranked), default=1)
    return [
        results[source_id].model_copy(update={"score": round(scores[source_id] / max_score, 4)})
        for source_id in ranked
    ]
