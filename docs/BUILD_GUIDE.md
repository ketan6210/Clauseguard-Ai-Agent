# ClauseGuard implementation notes

The MVP follows the supplied build guide through document processing, classification, policy retrieval, deterministic risk rules, persistence, human review, Q&A, reporting, dashboard, Docker, and CI.

Retrieval now embeds the policy corpus with FastEmbed and indexes it in Qdrant on demand. Vector and lexical results are combined with reciprocal rank fusion and a clause-category boost. If Qdrant or the embedding model is unavailable, the same interface automatically uses a local lexical fallback rather than failing the review.

Extracted contract clauses are also indexed in a separate Qdrant collection with review ID, clause ID, category, page, and text metadata. The Q&A route filters contract retrieval by review ID, retrieves company policies independently, and returns separated contract and policy citations. The local fallback provides the same API shape without an external model or paid API.

Scanned PDF pages now use PyMuPDF's Tesseract OCR bridge when ordinary text
extraction returns no text. The Docker backend includes the English Tesseract data.

The optional Qwen risk second-pass is disabled by default. Its structured output is
validated against real clause IDs, an allowed legal taxonomy, severity values, and
a configurable confidence floor before it becomes a finding. Findings show whether
they came from deterministic rules or the local model.

The combined evidence index uses rule strength (18%), clause classification (10%),
contract relevance (9%), policy similarity (7%), retrieval quality (7%), explicit
policy-deviation support (13%), Qwen verification (12%), independent evidence
consistency (8%), legal specificity (7%), and extraction quality (9%). Missing
signals are omitted and active weights are renormalized. RRF is used only for
ranking; absolute similarity is preserved and is not treated as proof of violation.

Qwen verification is batched across all findings, validates exact clause and policy
IDs, returns policy stance, and isolates failed batches. Residual analysis covers
all clauses in bounded batches and safely recovers fenced or wrapped JSON.

The dashboard separates impact, evidence, and review priority. Human workflow
decisions are not calibration truth; separate valid/invalid/uncertain labels store
the score and pipeline version at label time.

Uploads are checked for empty, binary, spoofed, or structurally invalid content
before parsing. The frontend exposes overall risk, evidence health, severity and
verification coverage, priority sorting, full-text filtering, score provenance, and
separate workflow and factual-correctness controls.

The executable evaluation harness reads `backend/evaluation/cases.json` and reports
classification accuracy, finding precision/recall, and forbidden false positives.
Before production use, expand this corpus and add authentication, malware scanning,
encrypted object storage, audit logging, tenant isolation, rate limits, and
retention controls.
