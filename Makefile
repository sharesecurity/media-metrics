# Media Metrics — Quick Commands
# Ports: backend=8010, minio=9010/9011, postgres=5434, qdrant=6333

.PHONY: up down logs restart-backend frontend reset status ingest analyze stats

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

## Ingest sample articles via API
ingest:
	curl -s -X POST http://localhost:8010/api/ingest/start \
	  -H "Content-Type: application/json" \
	  -d '{"source": "gdelt", "limit": 50}' | python3 -m json.tool

## Trigger analysis of all unanalyzed articles
analyze:
	curl -s -X POST http://localhost:8010/api/analysis/run-all | python3 -m json.tool

## Check article stats
stats:
	curl -s http://localhost:8010/api/articles/stats | python3 -m json.tool
