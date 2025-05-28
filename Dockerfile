# Use a simpler setup without frontend build
# We'll copy pre-built frontend assets instead of building in Docker

# Backend build stage
FROM python:3.10 AS builder

WORKDIR /app

# Install Rust and required build dependencies
RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    pkg-config \
    git \
    && rm -rf /var/lib/apt/lists/* \
    && curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y \
    && . $HOME/.cargo/env

# Copy only requirements files first to leverage Docker cache
COPY requirements.txt .
COPY lightrag/api/requirements.txt ./lightrag/api/

# Install dependencies
ENV PATH="/root/.cargo/bin:${PATH}"
RUN pip install --user --no-cache-dir -r requirements.txt
RUN pip install --user --no-cache-dir -r lightrag/api/requirements.txt

# Copy the rest of the application
COPY . .

# Install LightRAG with API support
RUN pip install --user --no-cache-dir ".[api]"

# Final stage
FROM python:3.10

WORKDIR /app

# Install runtime dependencies (curl for health checks and API interactions)
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local
COPY --from=builder /app/lightrag /app/lightrag
COPY --from=builder /app/setup.py /app/

# Copy local pre-built frontend files
COPY lightrag/api/webui /app/lightrag/api/webui

# Make sure scripts in .local are usable
ENV PATH=/root/.local/bin:$PATH

# Create necessary directories
RUN mkdir -p /app/data/rag_storage /app/data/inputs /app/data/contexts

# Docker data directories
ENV WORKING_DIR=/app/data/rag_storage
ENV INPUT_DIR=/app/data/inputs
ENV CONTEXTS_DIR=/app/data/contexts

# Multi-Context Configuration
ENV ENABLE_MULTI_CONTEXT=true
ENV DEFAULT_CONTEXT=default
ENV MAX_CONTEXTS=10

# Expose the default port
EXPOSE 9621

# Set entrypoint
ENTRYPOINT ["python", "-m", "lightrag.api.lightrag_server"]
