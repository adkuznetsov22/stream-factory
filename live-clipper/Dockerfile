FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web ./
RUN npx vite build --outDir /dist

FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY live_clipper ./live_clipper
COPY --from=web /dist ./live_clipper/static/dist
EXPOSE 8080
ENV LC_DATA_DIR=/data
CMD ["python", "-m", "live_clipper", "run"]
