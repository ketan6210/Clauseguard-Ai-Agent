# ClauseGuard implementation notes

The MVP follows the supplied build guide through document processing, classification, policy retrieval, deterministic risk rules, persistence, human review, Q&A, reporting, dashboard, Docker, and CI.

Retrieval now embeds the policy corpus with FastEmbed and indexes it in Qdrant on demand. Vector and lexical results are combined with reciprocal rank fusion and a clause-category boost. If Qdrant or the embedding model is unavailable, the same interface automatically uses a local lexical fallback rather than failing the review.

Before production use, add authentication, malware scanning, encrypted object storage, audit logging, tenant isolation, OCR, rate limits, retention controls, and a legal validation/evaluation program.
