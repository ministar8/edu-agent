# ── Stage 1: install dependencies ──
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies (compile cached)
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: runtime ──
FROM python:3.12-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY app/ app/

# Default env vars (overridden by docker-compose / .env)
ENV BACKEND_HOST=0.0.0.0 \
    BACKEND_PORT=8000 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

CMD ["python", "-m", "app.main"]
