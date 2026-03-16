# ─────────────────────────────────────────
#  SafeVoice AI — Dockerfile
# ─────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Run as non-root user for security
RUN useradd -m -u 1000 safevoice
USER safevoice

# Cloud Run expects port 8080
EXPOSE 8080

CMD ["uvicorn", "backend.api.routes:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "4"]
