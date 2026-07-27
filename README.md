# ClauseGuard RAG AI

ClauseGuard is a full-stack contract and compliance review MVP. It parses PDF, DOCX, TXT, and Markdown files; classifies clauses; compares them with company policies; flags deterministic risks and missing language; provides citations; and records reviewer decisions.

> ClauseGuard assists legal and compliance reviewers. It is not legal advice and does not replace legal counsel. Use synthetic documents in public demos.

## What works

- Contract upload and text extraction with page references
- Keyword-based contract and clause classification
- Qdrant vector retrieval with FastEmbed, BM25-style lexical matching, and policy citations
- Rules for breach notice, renewal, liability, payment, data deletion, and audit rights
- SQLite review persistence and approve/reject workflow
- Contract Q&A grounded in document excerpts and policy evidence
- Responsive React/TypeScript dashboard
- Docker Compose, backend tests, and CI

Policy embeddings are indexed lazily on the first semantic search. If Qdrant is unavailable or the embedding model cannot load, retrieval automatically uses the local lexical fallback so document review remains available. Set `QDRANT_ENABLED=false` to explicitly use fallback mode.

## Run locally

Backend (Python 3.11+):

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Frontend (Node 20+), in another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`, or use API docs at `http://localhost:8000/docs`. Upload [the sample vendor agreement](sample_documents/vendor_agreement.txt) to trigger multiple findings.

## Run with Docker

```bash
docker compose up --build
```

Open `http://localhost:3000`. Qdrant's dashboard is exposed at `http://localhost:6333/dashboard`; policies are embedded and indexed automatically on the first review.

## API

| Method | Route | Purpose |
|---|---|---|
| GET | `/health` | Service health |
| POST | `/reviews/upload` | Upload and analyze a document |
| GET | `/reviews/{id}` | Fetch a saved review |
| POST | `/reviews/{id}/ask` | Ask a grounded question |
| POST | `/reviews/{id}/decision` | Approve or reject a finding |
| GET | `/reviews/{id}/report` | Downloadable JSON-shaped report |

## Architecture

```text
React dashboard → FastAPI routes → review workflow
                                      ├─ document parser
                                      ├─ clause classifier
                                      ├─ policy retrieval
                                      ├─ deterministic risk engine
                                      └─ SQLite + cited report
```

## Tests

```bash
cd backend && pytest
cd frontend && npm run build
```

## Next production steps

Add OCR and authentication, move persistence to PostgreSQL/object storage, add evaluation datasets, and introduce LLM explanations only after retrieved evidence is available.
