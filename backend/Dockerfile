FROM ghcr.io/astral-sh/uv:python3.12-bookworm

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN uv pip install --system yt-dlp

COPY backend/pyproject.toml ./pyproject.toml
COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./alembic.ini
COPY backend/start.sh ./start.sh

RUN uv pip install --system .
RUN chmod +x /app/start.sh

EXPOSE 8000
CMD ["/app/start.sh"]
