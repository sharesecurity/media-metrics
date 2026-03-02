# Media Metrics

News bias analysis platform. Ingests news articles and analyzes them for political lean, sentiment, writing style, and other bias indicators using local LLMs (Ollama) and rule-based methods.

## Quick Start

### Prerequisites
- Docker Desktop running
- Ollama installed natively with `deepseek-r1:8b` pulled:
  ```
  ollama pull deepseek-r1:8b
  ollama pull nomic-embed-text
  ```
- Node.js 20+ for the frontend

### 1. Start backend services
```bash
make up
# or: docker compose up -d
```

Services started:
- PostgreSQL → localhost:5432
- Qdrant (vector DB) → localhost:6333
- MinIO (object storage) → localhost:9000 (console: 9001)
- FastAPI backend → http://localhost:8000
- API docs → http://localhost:8000/docs

### 2. Start frontend
```bash
make frontend
# or: cd frontend && npm install && npm run dev
```
Frontend → http://localhost:5173

### 3. Load sample data
In the frontend, go to **Dashboard** and click **"Ingest Articles"** — this loads 8 sample articles (same climate bill story from NYT, Fox, Reuters, AP, Guardian, WashPost, Breitbart, NPR) ideal for bias comparison.

Then click **"Analyze All"** to run bias analysis via Ollama.

### 4. Explore
- **Dashboard** — stats, source counts, political lean overview
- **Articles** — browse and search all articles
- **Article Detail** — full bias analysis for a single article
- **Bias Analysis** — compare sources, scatter charts
- **AI Chat** — ask questions about your data

## Architecture

```
frontend (React/Vite) → backend (FastAPI) → PostgreSQL
                                          → Qdrant (embeddings)
                                          → MinIO (/Volumes/LabStorage/media_metrics/)
                                          → Ollama (native, localhost:11434)
```

## Data

Large data files are stored at `/Volumes/LabStorage/media_metrics/` to keep them separate from other projects on that volume.

## Useful Commands

```bash
make logs        # Watch backend logs
make stats       # Article count stats
make ingest      # Trigger ingest via CLI
make analyze     # Analyze all unanalyzed articles
make reset       # Full reset (destroys all data)
```
