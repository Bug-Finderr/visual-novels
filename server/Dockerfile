# Backend image for Cloud Run.  Build context = ./server
#   docker build -t storyplex-api ./server
# Python 3.12 (onnxruntime, pulled in by rembg for sprite background removal,
# has no 3.13 wheels yet).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

# Native libs for Pillow / onnxruntime image processing.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install deps first so the layer caches across code changes.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Cloud Run injects $PORT (default 8080). uvicorn (not gunicorn) so the TTS
# WebSocket route works out of the box.
EXPOSE 8080
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
