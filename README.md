# Stream Factory Monorepo

Backend (FastAPI), frontend (Next.js), and infrastructure configured for Docker Compose.

## Quick start
```bash
docker compose up --build
```
- Backend healthcheck: GET http://localhost:8000/ping → `{ "status": "ok" }`
- Frontend: http://localhost:3000/

## Services
- **backend**: FastAPI app (`backend/app/main.py`) with env-driven settings (`backend/app/settings.py`).
- Endpoints: `/api/accounts` (GET с фильтрами `platform`, `q`; POST создания; PATCH/GET by id), `/api/phones`, `/api/emails`, `/api/accounts/export`, `/api/accounts/import`.
- **frontend**: Next.js (TypeScript, App Router) экран "Аккаунты" с табами платформ, поиском, карточками и модалкой добавления.
- **db**: PostgreSQL 16 with persistent volume `db_data`.
- **data**: backend пишет артефакты задач в `./data` (монтируется в контейнер `/data`), там же сохраняются скачанные видео/превью/логи.

## Environment
- Backend settings use `STREAM_FACTORY_` prefix (e.g., `STREAM_FACTORY_DATABASE_URL`, `STREAM_FACTORY_ENVIRONMENT`).
- Postgres creds are set in `docker-compose.yml` and can be overridden via environment or an `.env` file.

## Development notes
- Build images individually if needed:
  - Backend: `docker build -t stream-factory-backend -f backend/Dockerfile .`
  - Frontend: `docker build -t stream-factory-frontend frontend`

### FFmpeg/FFprobe (backend)
- После изменений собираем backend: `docker compose build backend`
- Проверяем наличие инструментов внутри контейнера:
  ```bash
  docker compose exec backend bash -lc "ffmpeg -version | head -n 2 && ffprobe -version | head -n 2"
  ```
- yt-dlp для TikTok fallback: `docker compose exec backend yt-dlp --version`

### Артефакты задач (backend)
- Том для файлов: `./data` на хосте → `/data` в контейнере.
- Пересборка и запуск: `docker compose up -d --build`
- Проверить наличие артефактов после обработки:
  ```bash
  TASK_ID=1
  docker compose exec backend bash -lc "ls -lah /data/tasks/${TASK_ID}"
  ```
  Файлы доступны по HTTP: `/files/tasks/${TASK_ID}/thumb.jpg` и др.

## XLSX формат импорта/экспорта
Колонки: `platform`, `label`, `handle`, `url`, `phone_number`, `email`, `email_password`, `account_password`, `purchase_source_url`, `raw_import_blob`. Экспорт возвращает эти поля; импорт ожидает те же заголовки, обновляя/создавая аккаунты по `handle`.
