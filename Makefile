# Media Metrics — Quick Commands
# Ports: backend=8010, minio=9010/9011, postgres=5434, qdrant=6333, grafana=3001

.PHONY: up down logs restart-backend frontend reset status ingest analyze stats reanalyze migrate-minio

## Start all Docker services
up:
	docker compose up -d

## Stop all services
down:
	docker compose down

## Watch backend logs live
logs:
	docker compose logs -f backend

## Restart just the backend (after code changes)
restart-backend:
	docker compose restart backend

## Start frontend dev server (run in a separate terminal)
frontend:
	cd frontend && npm install && npm run dev

## Full reset — destroy all data volumes and restart fresh
reset:
	docker compose down -v
	docker compose up -d

## Check container status
status:
	docker compose ps

## Ingest embedded sample articles (48 articles, 7 stories, 8 outlets, Jan–Dec 2024)
ingest:
	curl -s -X POST http://localhost:8010/api/ingest/start \
	  -H "Content-Type: application/json" \
	  -d '{"source": "embedded", "limit": 50}' | python3 -m json.tool

## Ingest live articles via RSS feeds (requires internet)
ingest-rss:
	curl -s -X POST http://localhost:8010/api/ingest/start \
	  -H "Content-Type: application/json" \
	  -d '{"source": "rss", "limit": 15}' | python3 -m json.tool

## Trigger analysis of all unanalyzed articles
analyze:
	curl -s -X POST http://localhost:8010/api/analysis/run-all | python3 -m json.tool

## Check article stats
stats:
	curl -s http://localhost:8010/api/articles/stats | python3 -m json.tool

## Re-analyze ALL articles (rebuilds Qdrant embeddings; use after new data or model changes)
reanalyze:
	curl -s -X POST http://localhost:8010/api/analysis/force-reanalyze | python3 -m json.tool

## Migrate existing article text from Postgres into MinIO
migrate-minio:
	curl -s -X POST "http://localhost:8010/api/articles/migrate-to-minio?limit=500" | python3 -m json.tool

## Open Grafana dashboard (admin / media_metrics_2024)
grafana:
	open http://localhost:3001
