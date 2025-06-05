# Multi-stage build for LightRAG with integrated WebUI
ARG BUILD_ENV=production

# Stage 1: Build WebUI
FROM node:20-alpine AS ui-builder
WORKDIR /ui

# Copy package files first for better caching
COPY lightrag_webui/package*.json ./
COPY lightrag_webui/yarn.lock* ./

# Install dependencies with legacy peer deps to handle version conflicts
RUN npm install --legacy-peer-deps

# Copy source code and build
COPY lightrag_webui/ ./
RUN npm run build-no-bun

# Stage 2: Backend build
FROM python:3.12-slim AS backend-builder
WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    pkg-config \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements files first to leverage Docker cache
COPY requirements.txt .
COPY lightrag/api/requirements.txt ./lightrag/api/

# Install Python dependencies
RUN pip install --user --no-cache-dir -r requirements.txt
RUN pip install --user --no-cache-dir -r lightrag/api/requirements.txt

# Copy the rest of the application
COPY . .

# Install LightRAG with API support
RUN pip install --user --no-cache-dir ".[api]"

# Stage 3: Production runtime
FROM python:3.12-slim AS prod
WORKDIR /app

# Install runtime dependencies (curl for health checks)
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=backend-builder /root/.local /root/.local
COPY --from=backend-builder /app/lightrag /app/lightrag
COPY --from=backend-builder /app/setup.py /app/

# Copy built WebUI from ui-builder stage
COPY --from=ui-builder /ui/dist /app/static

# Copy the main application (no longer need the launcher script)
# COPY run_webui_server.py /app/

# Make sure scripts in .local are usable
ENV PATH=/root/.local/bin:$PATH

# Create necessary directories
RUN mkdir -p /app/data/rag_storage /app/data/inputs /app/data/contexts

# Environment variables
ENV WORKING_DIR=/app/data/rag_storage
ENV INPUT_DIR=/app/data/inputs
ENV CONTEXTS_DIR=/app/data/contexts
ENV ENABLE_MULTI_CONTEXT=true
ENV DEFAULT_CONTEXT=default
ENV MAX_CONTEXTS=10

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:9621/health || exit 1

# Expose port
EXPOSE 9621

# Default command for the application - use uvicorn with the main.py app
CMD ["uvicorn", "lightrag.api.main:app", "--host", "0.0.0.0", "--port", "9621"]
