# ClauseGuard RAG AI

ClauseGuard is a full-stack AI contract and compliance review application powered by
hybrid RAG and the free local **Qwen3 4B** model through **Ollama**. It parses PDF,
DOCX, TXT, and Markdown files; classifies clauses; compares them with company
policies; flags deterministic risks, conflicts, and missing language; generates
grounded cited answers; and records reviewer decisions.

> ClauseGuard assists legal and compliance reviewers. It is not legal advice and does not replace legal counsel. Use synthetic documents in public demos.

## What works

- Contract upload and text extraction with page references
- Hierarchy-aware contract classification with primary agreement and attachment detection
- Hierarchical clause extraction with repeated header/footer and contents-page filtering
- Legal-number normalization for written, numeric, and parenthetical durations
- Expanded legal clause taxonomy and multi-finding deterministic risk rules
- Cross-clause conflict detection for payment, deletion, breach, SLA, cure, and precedence terms
- Contract-specific required-clause checklists
- Category-filtered policy evidence, severity calibration, and duplicate-finding suppression
- Qdrant vector retrieval with FastEmbed, BM25-style lexical matching, and policy citations
- Review-scoped contract-clause embeddings and combined contract/policy RAG
- Rules for breach notice, renewal, liability, payment, data deletion, and audit rights
- SQLite review persistence and approve/reject workflow
- Contract Q&A grounded in document excerpts and policy evidence
- Optional free local Qwen3 generation through Ollama, with citation validation and automatic fallback
- Responsive React/TypeScript dashboard
- Docker Compose, backend tests, and CI

Policy embeddings are indexed lazily on the first semantic search, and contract clauses are indexed per review. Q&A retrieves contract and policy evidence separately and returns validated citations for both. If Qdrant or the embedding model is unavailable, retrieval automatically uses the local lexical fallback so document review remains available. Set `QDRANT_ENABLED=false` to explicitly use fallback mode.

Q&A always works in free extractive mode. It can optionally use a locally running
Qwen3 model through Ollama; no API key, token purchase, or per-request payment is
required. Generated answers are accepted only when their citations match retrieved
contract or policy evidence. Otherwise ClauseGuard automatically returns the
extractive evidence answer.

## AI and RAG stack

- **Local LLM:** Qwen3 4B (`qwen3:4b`) served by Ollama
- **RAG sources:** review-scoped contract clauses plus company policy documents
- **Retrieval:** Qdrant/FastEmbed semantic search combined with lexical matching
- **Grounding:** retrieved evidence IDs are supplied to the model and displayed as citations
- **Safety:** unknown citations or incomplete model answers are rejected automatically
- **Fallback:** deterministic extractive answers remain available when Ollama or Qdrant is offline

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

### Enable the free local LLM

Install [Ollama](https://ollama.com), then run:

```bash
ollama serve
ollama pull qwen3:4b
```

Set `OLLAMA_ENABLED=true` in `backend/.env` (copy `.env.example` if needed), then
restart the backend. The default endpoint is `http://127.0.0.1:11434`, and the
frontend labels each response as either `Local AI (Qwen)` or `Evidence fallback`.

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
                                      ├─ document parser + clause classifier
                                      ├─ deterministic risk/conflict engine
                                      ├─ contract + policy hybrid RAG
                                      ├─ Ollama + Qwen3 4B cited Q&A
                                      └─ SQLite + cited report
```

## Tests

```bash
cd backend && pytest
cd frontend && npm run build
```

## Next production steps

Add OCR and authentication, move persistence to PostgreSQL/object storage, and add
larger evaluation datasets before enabling generative answers by default in a
production deployment.
