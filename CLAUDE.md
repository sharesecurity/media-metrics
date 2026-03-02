# CLAUDE.md — Media Metrics

## Project Overview
News bias analysis platform. Ingests news articles and analyzes them for political lean, sentiment, writing style, and other bias indicators using local LLMs (Ollama) and rule-based methods.

Full project progress, backlog, session history, and key decisions are tracked in:
**`/Users/blindow/Documents/news_project/PROJECT.md`** — always read this first.

---

## Workflow Instructions
- Operate autonomously. Do not ask for confirmation before editing files, running tests, or committing code.
- After completing meaningful work, commit to the current branch with a clear message.
- Update `/Users/blindow/Documents/news_project/PROJECT.md` with any progress, new completed items, or backlog changes at the end of a session.

---

## Repo
- **Path:** `/Users/blindow/Documents/news_project/media_metrics/`
- **Branch:** `main` (worktrees under `.claude/worktrees/`)
- **GitHub:** https://github.com/sharesecurity/media-metrics
- **Git identity:** Brad Lindow

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | FastAPI + Python 3.12 (Docker) |
| Frontend | React 18 + Vite + Tailwind (local `npm run dev`) |
| Primary DB | PostgreSQL 16 (Docker, port 5434) |
| Vector DB | Qdrant (Docker, port 6333) |
| Object Storage | MinIO (Docker, port 9010/9011) |
| Local LLM | Ollama native (NOT Docker) — `deepseek-r1:8b` |
| Embeddings | `nomic-embed-text` via Ollama |

**Critical:** Ollama runs natively on the Mac. Docker containers reach it via `host.docker.internal:11434`.

---

## Ports

| Service | URL |
|---------|-----|
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8010 |
| API Docs | http://localhost:8010/docs |
| MinIO Console | http://localhost:9011 |
| PostgreSQL | localhost:5434 |
| Qdrant | localhost:6333 |

---

## How to Start Services

```bash
# Start all Docker services (postgres, qdrant, minio, backend)
cd /Users/blindow/Documents/news_project/media_metrics
make up

# Start frontend (separate terminal)
make frontend
```

---

## Key Paths

| Purpose | Path |
|---------|------|
| Backend source | `backend/app/` |
| Bias pipeline | `backend/app/pipelines/bias_analyzer.py` |
| GDELT ingest | `backend/app/pipelines/gdelt_ingest.py` |
| DB schema | `backend/db/init.sql` |
| Config | `backend/app/core/config.py` |
| Frontend pages | `frontend/src/pages/` |
| Large data files | `/Volumes/LabStorage/media_metrics/` |

---

## Architecture Notes

- Single config source: `app/core/config.py` (shims at `app/config.py` and `app/database.py`)
- **Routers:** articles, analysis, ingest, search, sources, authors, chat, trends
- **Bias pipeline:** VADER sentiment + Flesch-Kincaid readability + Ollama LLM — strips `<think>` tags
- **Qdrant:** embeddings upserted after each analysis; failures are non-critical (Postgres still saves)
- **Political lean scale:** −1.0 (far left) → 0.0 (neutral) → +1.0 (far right)
- **spaCy/torch/transformers removed** — caused Docker build failures (no g++ in image); add back with multi-stage Dockerfile when needed

---

## Current Backlog (from PROJECT.md)

1. Re-analyze all 48 articles to rebuild Qdrant embeddings (Qdrant was just wired in Session 6)
2. Wire up MinIO for large article storage (currently storing text in Postgres)
3. Author demographic inference (gender/ethnicity from name)
4. Grafana dashboard
5. Bias method editor UI
6. CommonCrawl / "All the News" Kaggle dataset for bulk historical data
7. Real GDELT live download (falls back to embedded 48 articles; needs end-to-end testing)
