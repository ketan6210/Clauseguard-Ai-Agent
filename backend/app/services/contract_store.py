import logging
import math
import re
import uuid

from app.core.config import settings
from app.schemas.review import Clause, Evidence
from app.services.policy_store import _embed, _qdrant_client


logger = logging.getLogger(__name__)
_indexed_reviews: set[str] = set()


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def local_clause_search(query: str, clauses: list[Clause], limit: int = 5) -> list[Evidence]:
    query_tokens = _tokens(query)
    scored = []
    for clause in clauses:
        clause_tokens = _tokens(f"{clause.clause_type} {clause.text}")
        overlap = len(query_tokens & clause_tokens)
        if not overlap:
            continue
        score = overlap / math.sqrt(max(1, len(query_tokens) * len(clause_tokens)))
        scored.append(
            Evidence(
                source_id=clause.id,
                title=f"Contract clause {clause.id}",
                section=f"{clause.clause_type} · page {clause.page}",
                text=clause.text,
                score=round(score, 4),
            )
        )
    return sorted(scored, key=lambda item: item.score, reverse=True)[:limit]


def _ensure_clause_collection(vector_size: int) -> None:
    from qdrant_client.models import Distance, VectorParams

    client = _qdrant_client()
    if client.collection_exists(settings.qdrant_clause_collection):
        return
    client.create_collection(
        collection_name=settings.qdrant_clause_collection,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )


def index_contract_clauses(review_id: str, clauses: list[Clause]) -> bool:
    if not settings.qdrant_enabled or not clauses:
        return False
    if review_id in _indexed_reviews:
        return True
    try:
        from qdrant_client.models import PointStruct

        client = _qdrant_client()
        client.get_collections()
        vectors = _embed([f"{clause.clause_type}\n{clause.text}" for clause in clauses])
        _ensure_clause_collection(len(vectors[0]))
        points = [
            PointStruct(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"clauseguard:{review_id}:{clause.id}")),
                vector=vector,
                payload={
                    "review_id": review_id,
                    "clause_id": clause.id,
                    "clause_type": clause.clause_type,
                    "page": clause.page,
                    "text": clause.text,
                },
            )
            for clause, vector in zip(clauses, vectors, strict=True)
        ]
        client.upsert(
            collection_name=settings.qdrant_clause_collection,
            points=points,
            wait=True,
        )
        _indexed_reviews.add(review_id)
        return True
    except Exception as exc:
        logger.warning("Contract clause indexing unavailable; using local retrieval: %s", exc)
        return False


def _query_contract_clauses(review_id: str, query: str, limit: int) -> list[Evidence]:
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    response = _qdrant_client().query_points(
        collection_name=settings.qdrant_clause_collection,
        query=_embed([query])[0],
        query_filter=Filter(
            must=[
                FieldCondition(
                    key="review_id",
                    match=MatchValue(value=review_id),
                )
            ]
        ),
        limit=limit,
        with_payload=True,
    )
    return [
        Evidence(
            source_id=hit.payload["clause_id"],
            title=f"Contract clause {hit.payload['clause_id']}",
            section=f"{hit.payload['clause_type']} · page {hit.payload['page']}",
            text=hit.payload["text"],
            score=round(float(hit.score), 4),
        )
        for hit in response.points
        if hit.payload
    ]


def search_contract_clauses(
    review_id: str,
    query: str,
    clauses: list[Clause],
    limit: int = 5,
) -> list[Evidence]:
    if not query.strip() or limit < 1:
        return []
    if settings.qdrant_enabled:
        try:
            if index_contract_clauses(review_id, clauses):
                return _query_contract_clauses(review_id, query, limit)
        except Exception as exc:
            logger.warning("Contract vector query unavailable; using local retrieval: %s", exc)
    return local_clause_search(query, clauses, limit)
