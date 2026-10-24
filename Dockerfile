# Multi-stage production Dockerfile
# Stage 1: Build & wheels preparation
FROM python:3.11-slim as builder

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Final lightweight runtime
FROM python:3.11-slim as runner

# Create a non-root dedicated service user (Task 1 & Task 4 security requirement)
RUN groupadd -g 1001 appgroup && \
    useradd -u 1001 -g appgroup -s /bin/bash -m appuser

WORKDIR /app

# Copy installed python dependencies from builder
COPY --from=builder /root/.local /home/appuser/.local

# Copy application code, artifacts, and configs
COPY src/ /app/src/
COPY artifacts/ /app/artifacts/

# Set ownership
RUN chown -R appuser:appgroup /app

USER appuser
ENV PATH=/home/appuser/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1
ENV MODEL_PATH=/app/artifacts/model_v1.0.0.joblib

# Expose FastAPI HTTP port
EXPOSE 8000

# Healthcheck instruction
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" || exit 1

# Default launch command: Uvicorn ASGI server with configurable concurrency
CMD ["uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
