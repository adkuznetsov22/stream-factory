.PHONY: up down logs migrate preflight smoke reset

BASE_URL ?= http://localhost:8000

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f --tail=100 backend worker

migrate:
	docker compose exec backend alembic upgrade head

preflight:
	@curl -sf $(BASE_URL)/api/ops/health | python3 -m json.tool | head -30
	@echo ""
	@echo "--- Preflight OK check ---"
	@curl -sf $(BASE_URL)/api/ops/health | python3 -c "import sys,json; d=json.load(sys.stdin); ok=d.get('preflight',{}).get('ok'); print('PREFLIGHT:', 'OK' if ok else 'FAIL'); sys.exit(0 if ok else 1)"

smoke:
	python3 scripts/smoke_e2e.py

reset:
	@echo "WARNING: This will destroy all data (volumes)!"
	@read -p "Type 'yes' to confirm: " confirm && [ "$$confirm" = "yes" ] || exit 1
	docker compose down -v
