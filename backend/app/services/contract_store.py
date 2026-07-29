import logging
import math
import re
import uuid

from app.core.config import settings
from app.schemas.review import Clause, Evidence
from app.services.clause_classifier import classify_clause
from app.services.policy_store import _embed, _qdrant_client


logger = logging.getLogger(__name__)
_indexed_reviews: set[str] = set()


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


_QUERY_EXPANSIONS = {
    "data_breach_notification": "breach incident security notify notification notice hours days",
    "payment_terms": "payment invoice fee fees payable net days",
    "termination": "termination terminate convenience cause cure",
    "auto_renewal": "renew renewal automatic cancel cancellation notice",
    "limitation_of_liability": "liability cap damages limitation exposure",
    "indemnification": "indemnity indemnify defend claims",
    "data_deletion": "delete deletion erase return retain retention",
    "audit_rights": "audit inspect inspection records compliance",
    "data_use": "data use license training artificial intelligence ai commercialize",
}


def _query_context(query: str) -> tuple[set[str], str]:
    category = classify_clause(query)
    if category == "other":
        lowered = query.lower()
        category_keywords = {
            "payment_terms": ("invoice", "paid", "payable", "payment", "fee"),
            "data_breach_notification": ("breach", "incident", "notify", "notification"),
            "termination": ("terminate", "termination", "cure"),
            "auto_renewal": ("renew", "renewal", "cancel"),
            "limitation_of_liability": ("liability", "damages", "cap"),
            "indemnification": ("indemn", "defend", "claims"),
            "data_deletion": ("delete", "deletion", "erase", "retention"),
            "audit_rights": ("audit", "inspect", "inspection"),
        }
        category = next(
            (
                name
                for name, keywords in category_keywords.items()
                if any(keyword in lowered for keyword in keywords)
            ),
            "other",
        )
    expanded = query
    if category in _QUERY_EXPANSIONS:
        expanded += " " + _QUERY_EXPANSIONS[category]
    return _tokens(expanded), category


def local_clause_search(query: str, clauses: list[Clause], limit: int = 5) -> list[Evidence]:
    query_tokens, category = _query_context(query)
    scored = []
    for clause in clauses:
        clause_tokens = _tokens(f"{clause.clause_type} {clause.text}")
        overlap = len(query_tokens & clause_tokens)
        if not overlap:
            continue
        lexical_score = overlap / math.sqrt(max(1, len(query_tokens) * len(clause_tokens)))
        category_boost = 0.35 if category != "other" and clause.clause_type == category else 0
        score = min(1.0, lexical_score + category_boost)
        if score < settings.contract_retrieval_min_score:
            continue
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
                candidates = _query_contract_clauses(review_id, query, max(limit * 3, 10))
                query_tokens, category = _query_context(query)
                reranked = []
                for item in candidates:
                    clause_category = item.section.split(" · ", 1)[0]
                    lexical_overlap = len(query_tokens & _tokens(item.text))
                    lexical_score = lexical_overlap / max(1, len(query_tokens))
                    category_boost = 0.25 if category != "other" and clause_category == category else 0
                    score = min(1.0, item.score * 0.65 + lexical_score * 0.35 + category_boost)
                    if score >= settings.contract_retrieval_min_score:
                        reranked.append(item.model_copy(update={"score": round(score, 4)}))
                return sorted(reranked, key=lambda item: item.score, reverse=True)[:limit]
        except Exception as exc:
            logger.warning("Contract vector query unavailable; using local retrieval: %s", exc)
    return local_clause_search(query, clauses, limit)
