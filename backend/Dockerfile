# API service: FastAPI + Docker CLI to spawn sandbox containers. No Manim/Kokoro.
FROM python:3.11-slim

# Client only — this container never runs its own daemon.
RUN apt-get update && apt-get install -y --no-install-recommends \
    docker-cli \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

# Only what api/ imports.
COPY config/__init__.py config/config.py config/
COPY graph/__init__.py graph/progress.py graph/
COPY api/ api/

ENV PYTHONPATH=/app
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
