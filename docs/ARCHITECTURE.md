# Stream Factory Architecture

## Overview
- **backend/**: FastAPI service exposing `/ping` plus `/api/accounts` (GET/POST). Reads configuration from environment via `pydantic-settings`. Uses SQLAlchemy async engine + Alembic migrations (`alembic/`).
- **frontend/**: Next.js (TypeScript, App Router) "Аккаунты" экран с табами платформ, поиском, карточками аккаунтов и модалкой добавления.
- **infra**: `docker-compose.yml` orchestrates PostgreSQL, backend, and frontend with healthchecks, shared network, and a persistent Postgres volume.

## Local run with Docker
1. Build and start everything:
   ```bash
   docker compose up --build
   ```
2. Services:
   - Backend: http://localhost:8000/ping
   - Frontend: http://localhost:3000/
   - Postgres: exposed inside the compose network at `db:5432`.

## Configuration
- Backend environment variables (prefixed `STREAM_FACTORY_`) can be set in the compose file or an `.env` file (e.g., `STREAM_FACTORY_DATABASE_URL`, `STREAM_FACTORY_ENVIRONMENT`). DB URL is async-compatible (`postgresql+asyncpg://...`).
- Postgres credentials are set via `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB` in `docker-compose.yml`.

## Structure
```
backend/
  app/
    db.py
    models.py
    schemas.py
    routes_accounts.py
    main.py
    settings.py
  Dockerfile
  pyproject.toml
  alembic.ini
  alembic/
    versions/
frontend/
  app config & source (TypeScript, App Router)
  Dockerfile
  package.json
  next.config.ts
infra
  docker-compose.yml
```
