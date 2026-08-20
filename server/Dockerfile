# Backend image for Cloud Run / Render.  Build context = ./server
#   docker build -t storyplex-api ./server
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

WORKDIR /app

# Install deps first so the layer caches across code changes.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Cloud Run / Render both inject $PORT (default 8080). uvicorn (not gunicorn)
# so the TTS WebSocket route works out of the box. Migrations run on every
# boot — `alembic upgrade head` is a no-op once the DB is current, so this
# stays safe across restarts/redeploys without a separate migrate step.
EXPOSE 8080
CMD ["sh", "-c", "python -m alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
