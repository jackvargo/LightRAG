#!/bin/bash
# LightRAG Setup Script
# This script helps set up LightRAG with Docker

set -e

echo "=== Setting up LightRAG with Docker ==="

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
  echo "Error: Docker is not running. Please start Docker Desktop and try again."
  exit 1
fi

# Create project directories
mkdir -p data/rag_storage
mkdir -p inputs

# Check if Ollama is installed and ask for LLM preference
USE_OLLAMA=true
OLLAMA_AVAILABLE=false

if command -v ollama >/dev/null 2>&1 || curl -s http://localhost:11434/api/version > /dev/null 2>&1; then
  OLLAMA_AVAILABLE=true
  echo "Ollama detected on your system."
  read -p "Would you like to use Ollama for local LLM processing? (y/n, default: y): " USE_OLLAMA_INPUT
  USE_OLLAMA_INPUT=${USE_OLLAMA_INPUT:-y}
  
  if [[ $USE_OLLAMA_INPUT =~ ^[Nn]$ ]]; then
    USE_OLLAMA=false
  fi
else
  echo "Ollama not detected. Will configure for OpenAI API."
  USE_OLLAMA=false
fi

# Ollama configuration
if [ "$USE_OLLAMA" = true ] && [ "$OLLAMA_AVAILABLE" = true ]; then
  echo "=== Configuring for Ollama LLM ==="
  
  # Suggest models to pull
  echo "Recommended models for Ollama:"
  echo "1. deepseek-r1:8b (8.5GB, recommended for systems with 16GB+ RAM)"
  echo "2. llama3:8b (8.5GB, recommended for systems with 16GB+ RAM)"
  echo "3. llama3:instruct (4.7GB, recommended for systems with 8GB+ RAM)"
  echo "4. mistral:7b (4.1GB, recommended for systems with 8GB+ RAM)"
  
  read -p "Would you like to pull any of these models now? (1/2/3/4/n, default: n): " PULL_MODEL
  PULL_MODEL=${PULL_MODEL:-n}
  
  case $PULL_MODEL in
    1)
      echo "Pulling deepseek-r1:8b model..."
      curl -s -X POST http://localhost:11434/api/pull -d '{"name": "deepseek-r1:8b"}'
      LLM_MODEL="deepseek-r1:8b"
      ;;
    2)
      echo "Pulling llama3:8b model..."
      curl -s -X POST http://localhost:11434/api/pull -d '{"name": "llama3:8b"}'
      LLM_MODEL="llama3:8b"
      ;;
    3)
      echo "Pulling llama3:instruct model..."
      curl -s -X POST http://localhost:11434/api/pull -d '{"name": "llama3:instruct"}'
      LLM_MODEL="llama3:instruct"
      ;;
    4)
      echo "Pulling mistral:7b model..."
      curl -s -X POST http://localhost:11434/api/pull -d '{"name": "mistral:7b"}'
      LLM_MODEL="mistral:7b"
      ;;
    *)
      echo "Skipping model pull. You can pull models later using Ollama."
      LLM_MODEL="llama3:8b"
      ;;
  esac
  
  echo "Pulling bge-m3 embedding model..."
  curl -s -X POST http://localhost:11434/api/pull -d '{"name": "bge-m3"}'
else
  echo "=== Configuring for OpenAI API ==="
  read -p "Enter your OpenAI API key (will be stored in .env file): " OPENAI_API_KEY
fi

# Add version selection
echo ""
echo "=== LightRAG Version Selection ==="
echo "1. Latest stable release (recommended)"
echo "2. Specific version"
echo "3. Development version (use local files)"
read -p "Select version option (1/2/3, default: 1): " VERSION_OPTION
VERSION_OPTION=${VERSION_OPTION:-1}

LIGHTRAG_VERSION="latest"
case $VERSION_OPTION in
  1)
    # Get the latest release tag from GitHub
    LATEST_VERSION=$(curl -s https://api.github.com/repos/HKUDS/LightRAG/releases/latest | grep -oP '"tag_name": "\K(.*)(?=")')
    if [ -z "$LATEST_VERSION" ]; then
      LATEST_VERSION="v0.3.0"  # Fallback if API call fails
    fi
    LIGHTRAG_VERSION=$LATEST_VERSION
    echo "Using latest stable release: $LIGHTRAG_VERSION"
    ;;
  2)
    read -p "Enter specific version (e.g., v0.3.0): " SPECIFIC_VERSION
    LIGHTRAG_VERSION=${SPECIFIC_VERSION:-v0.3.0}
    echo "Using specific version: $LIGHTRAG_VERSION"
    ;;
  3)
    LIGHTRAG_VERSION="main"
    echo "Using development version (local files)"
    ;;
esac

echo "=== Creating Dockerfile ==="
cat > Dockerfile << EOL
# Build stage
FROM python:3.11-slim AS builder

WORKDIR /app

# Install Rust and required build dependencies
RUN apt-get update && apt-get install -y \\
    curl \\
    build-essential \\
    pkg-config \\
    git \\
    && rm -rf /var/lib/apt/lists/* \\
    && curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y \\
    && . \$HOME/.cargo/env

# Get LightRAG based on selected version
EOL

# Add the appropriate download method based on version selection
if [ "$LIGHTRAG_VERSION" = "main" ]; then
  cat >> Dockerfile << EOL
# Use local files for development version
COPY . .
EOL
else
  cat >> Dockerfile << EOL
# Download specific release version
RUN curl -L https://github.com/HKUDS/LightRAG/archive/refs/tags/${LIGHTRAG_VERSION}.tar.gz | tar xz --strip-components=1
EOL
fi

cat >> Dockerfile << 'EOL'

# Install dependencies
ENV PATH="/root/.cargo/bin:${PATH}"
RUN pip install --user --no-cache-dir -r requirements.txt
RUN pip install --user --no-cache-dir -r lightrag/api/requirements.txt

# Install LightRAG with API support
RUN pip install --user --no-cache-dir ".[api]"

# Final stage
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies (curl for health checks and API interactions)
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local
COPY --from=builder /app/lightrag /app/lightrag
COPY --from=builder /app/setup.py /app/

# Make sure scripts in .local are usable
ENV PATH=/root/.local/bin:$PATH

# Create necessary directories
RUN mkdir -p /app/data/rag_storage /app/data/inputs

# Docker data directories
ENV WORKING_DIR=/app/data/rag_storage
ENV INPUT_DIR=/app/data/inputs

# Expose the default port
EXPOSE 9621

# Set entrypoint
ENTRYPOINT ["python", "-m", "lightrag.api.lightrag_server"]
EOL

echo "=== Creating docker-compose.yml ==="
cat > docker-compose.yml << 'EOL'
version: '3.8'

services:
  lightrag:
    build:
      context: .
      dockerfile: Dockerfile
    image: lightrag-server
    container_name: lightrag-server
    ports:
      # Expose the API server port, using PORT from .env or fallback to 9621
      - "${PORT:-9621}:${PORT:-9621}"
    volumes:
      # Mount working directory to container's expected path
      - ${LIGHTRAG_WORKING_DIR:-./data/rag_storage}:/app/data/rag_storage
      # Mount inputs directory to container's expected path
      - ${LIGHTRAG_INPUT_DIR:-./inputs}:/app/data/inputs
    env_file:
      # Load environment variables from .env file
      - .env
    # Add host.docker.internal mapping for Ollama when using local LLM
    # This allows the container to connect to Ollama running on the host
    # Required for macOS/Windows, auto-configured on Linux
    extra_hosts:
      - "host.docker.internal:host-gateway"
    restart: unless-stopped
    # Resource limits to prevent container from using too much memory
    deploy:
      resources:
        limits:
          memory: ${MEMORY_LIMIT:-8G}
        reservations:
          memory: ${MEMORY_RESERVATION:-4G}

# Named volume for persistent data storage
volumes:
  lightrag_data:
    driver: local
EOL

# Determine system memory for resource allocation
if [ "$(uname)" == "Darwin" ]; then
  # macOS
  TOTAL_MEM_GB=$(( $(sysctl -n hw.memsize) / 1024 / 1024 / 1024 ))
elif [ "$(uname)" == "Linux" ]; then
  # Linux
  TOTAL_MEM_GB=$(( $(grep MemTotal /proc/meminfo | awk '{print $2}') / 1024 / 1024 ))
else
  # Default to 8GB if we can't determine
  TOTAL_MEM_GB=8
fi

# Set memory limits based on system memory
if [ $TOTAL_MEM_GB -ge 32 ]; then
  MEMORY_LIMIT="16G"
  MEMORY_RESERVATION="8G"
elif [ $TOTAL_MEM_GB -ge 16 ]; then
  MEMORY_LIMIT="8G"
  MEMORY_RESERVATION="4G"
else
  MEMORY_LIMIT="4G"
  MEMORY_RESERVATION="2G"
fi

echo "=== Creating .env file ==="
cat > .env << EOL
### LightRAG Configuration
### See https://github.com/HKUDS/LightRAG for documentation

### Server Configuration
HOST=0.0.0.0
PORT=9621
WORKERS=2
CORS_ORIGINS=*
WEBUI_TITLE=LightRAG
WEBUI_DESCRIPTION=Graph-based Retrieval Augmented Generation

### Directory Configuration
WORKING_DIR=/app/data/rag_storage
INPUT_DIR=/app/data/inputs

### Memory Resources
MEMORY_LIMIT=${MEMORY_LIMIT}
MEMORY_RESERVATION=${MEMORY_RESERVATION}

### Logging Configuration
LOG_LEVEL=INFO
VERBOSE=false
LOG_MAX_BYTES=10485760
LOG_BACKUP_COUNT=5

### Memory Optimization
MAX_GRAPH_NODES=500
MAX_PARALLEL_INSERT=2
CHUNK_SIZE=1000
CHUNK_OVERLAP_SIZE=100
EMBEDDING_BATCH_NUM=16
EMBEDDING_FUNC_MAX_ASYNC=8
MAX_EMBED_TOKENS=4096

### Settings for RAG query
HISTORY_TURNS=3
COSINE_THRESHOLD=0.2
TOP_K=30
MAX_TOKEN_TEXT_CHUNK=4000
MAX_TOKEN_RELATION_DESC=4000
MAX_TOKEN_ENTITY_DESC=4000

### Settings for document indexing
ENABLE_LLM_CACHE_FOR_EXTRACT=true
SUMMARY_LANGUAGE=English
MAX_TOKEN_SUMMARY=500

### LLM Configuration
TIMEOUT=150
TEMPERATURE=0.5
MAX_ASYNC=2
MAX_TOKENS=16384
EOL

# Add Ollama or OpenAI specific configuration
if [ "$USE_OLLAMA" = true ]; then
  cat >> .env << EOL
### Ollama LLM Configuration
LLM_BINDING=ollama
LLM_MODEL=${LLM_MODEL:-llama3:8b}
LLM_BINDING_HOST=http://host.docker.internal:11434

### Embedding Configuration (Ollama)
EMBEDDING_BINDING=ollama
EMBEDDING_BINDING_HOST=http://host.docker.internal:11434
EMBEDDING_MODEL=bge-m3
EMBEDDING_DIM=1024
EOL
else
  cat >> .env << EOL
### OpenAI LLM Configuration
LLM_BINDING=openai
LLM_MODEL=gpt-4o-mini
LLM_BINDING_HOST=https://api.openai.com/v1
LLM_BINDING_API_KEY=${OPENAI_API_KEY}
OPENAI_API_KEY=${OPENAI_API_KEY}

### OpenAI Embedding Configuration
EMBEDDING_BINDING=openai
EMBEDDING_BINDING_HOST=https://api.openai.com/v1
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIM=1536
EOL
fi

# Add common storage and auth configuration
cat >> .env << EOL

### Data storage selection
LIGHTRAG_KV_STORAGE=JsonKVStorage
LIGHTRAG_VECTOR_STORAGE=NanoVectorDBStorage
LIGHTRAG_GRAPH_STORAGE=NetworkXStorage
LIGHTRAG_DOC_STATUS_STORAGE=JsonDocStatusStorage

### Authentication (CHANGE THESE IN PRODUCTION)
AUTH_ACCOUNTS=admin:admin123
TOKEN_SECRET=your-secure-token-secret-key-change-me
TOKEN_EXPIRE_HOURS=48
EOL

# Create a backup of the .env file as .env.template for reference
cp .env .env.template

echo "=== Creating convenience scripts ==="
# Start script - copy from template
if [ -f "start.sh.template" ]; then
  cp start.sh.template start.sh
  chmod +x start.sh
else
  # Fallback in case template is missing
  cat > start.sh << 'EOL'
#!/bin/bash
echo "Starting LightRAG with Docker Compose..."
docker compose up -d
echo ""
echo "LightRAG is now running at: http://localhost:$(grep -o 'PORT=[0-9]*' .env | cut -d= -f2 || echo 9621)"
echo "Login with username: admin, password: admin123"
EOL
  chmod +x start.sh
fi

# Stop script - copy from template
if [ -f "stop.sh.template" ]; then
  cp stop.sh.template stop.sh
  chmod +x stop.sh
else
  # Fallback in case template is missing
  cat > stop.sh << 'EOL'
#!/bin/bash
echo "Stopping LightRAG..."
docker compose down
EOL
  chmod +x stop.sh
fi

echo "=== Setup complete! ==="
echo ""
echo "To start LightRAG, run:"
echo "  ./start.sh"
echo ""
echo "To stop LightRAG, run:"
echo "  ./stop.sh"
echo ""
echo "You can place your documents in the 'inputs' folder."
echo "Access the web interface at: http://localhost:9621"
echo "Default login: admin / admin123"
echo ""
echo "Configuration is stored in .env - edit this file to change settings."
echo "Please note that the first build may take some time as it downloads and installs dependencies."
