# Media Metrics — Quick Commands

.PHONY: up down logs backend-logs reset frontend

## Start all Docker services (postgres, qdrant, minio, backend)
up:
	docker compose up -d

## Stop all services
down:
	docker compose down

## View backend logs live
logs:
	docker compose logs -f backend

## Restart just the backend (after code changes)
restart-backend:
	docker compose restart backend

## Start frontend dev server
frontend:
	cd frontend && npm install && npm run dev

## Full reset — destroy all data volumes and restart
reset:
	docker compose down -v
	docker compose up -d

## Check status
status:
	docker compose ps

## Ingest sample articles via API
ingest:
	curl -s -X POST http://localhost:8000/api/ingest/start \
	  -H "Content-Type: application/json" \
	  -d '{"source": "gdelt", "limit": 50}' | python3 -m json.tool

## Trigger analysis of all unanalyzed articles
analyze:
	curl -s -X POST http://localhost:8000/api/analysis/run-all | python3 -m json.tool

## Check article stats
stats:
	curl -s http://localhost:8000/api/articles/stats | python3 -m json.tool
