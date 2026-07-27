# ClauseGuard implementation notes

The MVP follows the supplied build guide through document processing, classification, policy retrieval, deterministic risk rules, persistence, human review, Q&A, reporting, dashboard, Docker, and CI.

Retrieval now embeds the policy corpus with FastEmbed and indexes it in Qdrant on demand. Vector and lexical results are combined with reciprocal rank fusion and a clause-category boost. If Qdrant or the embedding model is unavailable, the same interface automatically uses a local lexical fallback rather than failing the review.

Extracted contract clauses are also indexed in a separate Qdrant collection with review ID, clause ID, category, page, and text metadata. The Q&A route filters contract retrieval by review ID, retrieves company policies independently, and returns separated contract and policy citations. The local fallback provides the same API shape without an external model or paid API.

Before production use, add authentication, malware scanning, encrypted object storage, audit logging, tenant isolation, OCR, rate limits, retention controls, and a legal validation/evaluation program.
