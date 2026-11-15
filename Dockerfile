# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080 \
    UNICORN_RADAR_DB_PATH=/tmp/analyses.sqlite3

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir \
        "fastapi>=0.115.0" \
        "uvicorn>=0.32.0" \
        "httpx>=0.27.2" \
        "pydantic>=2.9.0" \
        "psycopg[binary]>=3.2.0" \
        "valkey>=6.0.0" \
        "google-genai>=1.0.0" \
    && useradd --system --uid 10001 appuser

COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY docs/ ./docs/
COPY .github/workflows/ ./.github/workflows/
COPY demo.py README.md .env.example ./

# Pre-build deterministic 10,785-node snapshot during image build for instant Cloud Run cold starts
RUN python demo.py build && chown -R 10001:10001 /app/backend/data

USER 10001
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8080') + '/api/health', timeout=4).close()"

CMD ["sh", "-c", "exec uvicorn backend.app:app --host 0.0.0.0 --port \"${PORT:-8080}\" --no-access-log"]
