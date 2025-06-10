# LightRAG Docker Deployment Guide

This guide provides detailed instructions for deploying LightRAG using Docker and Docker Compose.

## Overview

The Docker configuration in this repository allows you to:

1. Run LightRAG in a containerized environment
2. Use either local LLMs (via Ollama) or cloud LLMs (via OpenAI)
3. Persist data between container restarts
4. Scale resources based on your system capabilities
5. **NEW**: Deploy integrated WebUI + API in a single production container

## 🆕 **Integrated WebUI Deployment**

LightRAG now supports **production-ready integrated deployment** with WebUI and API served from a single container:

### **Quick Production Start**
```bash
# Single-container deployment (API + WebUI)
docker compose --profile prod up -d

# Access WebUI: http://localhost:9621/webui/
# Access API docs: http://localhost:9621/docs
```

### **Development Mode (Preserved)**
```bash
# Development workflow (separate services)
docker compose --profile dev up -d    # Backend on 9621
cd lightrag_webui && npm run dev      # Frontend on 5173
```

### **Deployment Profiles**

| Profile | Container Count | Ports | WebUI | Use Case |
|---------|-----------------|-------|-------|----------|
| `dev` | 1 | 9621 (API only) | Separate dev server (5173) | Development |
| `prod` | 1 | 9621 (API + WebUI) | Integrated | Production, Homelab |
| `ci` | 1 | Build validation | N/A | CI/CD, Testing |

**Multi-Instance Example:**
```bash
# Production instance 1 (port 9621)
docker compose --env-file .env.prod1 --profile prod up -d

# Production instance 2 (port 9622) 
docker compose --env-file .env.prod2 --profile prod up -d
```

### **Production Features**
- ✅ **Single Port Deployment**: Everything on port 9621
- ✅ **Multi-Context Support**: Full context switching functionality
- ✅ **Authentication**: JWT-based with admin:admin123 default
- ✅ **Health Monitoring**: `/health` endpoint with WebUI status
- ✅ **Static Asset Serving**: Optimized asset delivery
- ✅ **SPA Routing**: Complete single-page application support

## Prerequisites

- Docker and Docker Compose installed
- [Ollama](https://ollama.ai/) (optional, for local LLM processing)
- OpenAI API key (optional, for cloud LLM processing)

## Multi-Instance Deployment

LightRAG supports running multiple instances on the same Docker host by using environment variables to avoid conflicts:

### Running Multiple Instances

Create separate environment files for each instance:

**Instance 1 (.env.instance1):**
```bash
CONTAINER_NAME=lightrag-instance1
INSTANCE_NAME=instance1
PORT=9621
DOMAIN=lightrag1.localhost
```

**Instance 2 (.env.instance2):**
```bash
CONTAINER_NAME=lightrag-instance2
INSTANCE_NAME=instance2
PORT=9622
DOMAIN=lightrag2.localhost
```

Deploy each instance:
```bash
# Start instance 1
docker compose --env-file .env.instance1 --profile prod up -d

# Start instance 2  
docker compose --env-file .env.instance2 --profile prod up -d
```

**Key Variables for Multi-Instance:**
- `CONTAINER_NAME`: Unique container name (e.g., `lightrag-app1`, `lightrag-app2`)
- `INSTANCE_NAME`: Unique data directory name (e.g., `app1`, `app2`)
- `PORT`: Unique port mapping (e.g., `9621`, `9622`, `9623`)
- `DOMAIN`: Unique domain for Traefik routing (prod profile only)

**Data Isolation:**
Each instance will store data in separate directories:
- Instance 1: `./data/instance1/`
- Instance 2: `./data/instance2/`

This ensures complete data isolation between instances.

## Quick Start

### Automated Setup

Run the provided setup script which will guide you through the configuration process:

```bash
./lightrag-setup-script.sh
```

The script will:
1. Create necessary directories
2. Configure LightRAG for either Ollama or OpenAI
3. Create Docker configuration files
4. Create a customized .env file

> **Note:** The setup script generates several files that are not version-controlled:
> - `start.sh` and `stop.sh` (convenience scripts)
> - `.env` (environment configuration)
> - `data/` directory (for storage)
>
> Templates for these files are available as `start.sh.template` and `stop.sh.template`.

### Manual Setup

If you prefer to set up manually:

1. Copy `.env.example` to `.env` and customize it
2. Create data directories:
   ```bash
   mkdir -p data/rag_storage inputs
   ```
3. Create start and stop scripts from their templates:
   ```bash
   cp start.sh.template start.sh
   cp stop.sh.template stop.sh
   chmod +x start.sh stop.sh
   ```
4. Start the containers:
   ```bash
   docker compose up -d
   ```

## Configuration Options

### Multi-Instance Variables

For running multiple instances, these variables control naming and data isolation:

```
# Container and instance identification
CONTAINER_NAME=lightrag-myapp     # Unique container name
INSTANCE_NAME=myapp               # Unique data directory name
PORT=9621                         # Unique port number

# Production routing (if using Traefik)
DOMAIN=lightrag.mydomain.com      # Unique domain
```

### LLM Provider Options

#### Option 1: Ollama (Local)

For using local LLMs with Ollama, set the following in your `.env` file:

```
LLM_BINDING=ollama
LLM_MODEL=llama3:8b
LLM_BINDING_HOST=http://host.docker.internal:11434
EMBEDDING_BINDING=ollama
EMBEDDING_BINDING_HOST=http://host.docker.internal:11434
EMBEDDING_MODEL=bge-m3
EMBEDDING_DIM=1024
```

Make sure Ollama is running on your host machine before starting LightRAG.

#### Option 2: OpenAI (Cloud)

For using OpenAI's cloud services, set:

```
LLM_BINDING=openai
LLM_MODEL=gpt-4o-mini
LLM_BINDING_HOST=https://api.openai.com/v1
LLM_BINDING_API_KEY=your-openai-api-key
OPENAI_API_KEY=your-openai-api-key
EMBEDDING_BINDING=openai
EMBEDDING_BINDING_HOST=https://api.openai.com/v1
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIM=1536
```

Replace `your-openai-api-key` with your actual API key.

### Resource Allocation

Adjust these values in your `.env` file based on your system's capabilities:

```
MEMORY_LIMIT=8G
MEMORY_RESERVATION=4G
```

For systems with:
- 32GB+ RAM: Consider `MEMORY_LIMIT=16G`
- 16GB RAM: Use `MEMORY_LIMIT=8G`
- 8GB RAM: Use `MEMORY_LIMIT=4G`

### Authentication

By default, the system uses basic authentication:
- Username: `admin`
- Password: `admin123`

For production deployments, change these in your `.env` file:

```
AUTH_ACCOUNTS=admin:your-secure-password
TOKEN_SECRET=your-secure-token-key
```

## Data Persistence

The following directories are persisted:

- `./data`: Contains all LightRAG data (graph database, vector storage, etc.)
- `./inputs`: Place your documents here for processing

## Monitoring and Logs

To view container logs:

```bash
docker compose logs
```

For continuous monitoring:

```bash
docker compose logs -f
```

## Troubleshooting

### Ollama Connectivity Issues

If you're using Ollama and encounter connectivity issues:

1. Ensure Ollama is running: `ollama serve`
2. Verify the host mapping in Docker Compose
3. Try using `localhost` instead of `host.docker.internal` if on Linux

### Memory Issues

If you encounter out-of-memory errors:

1. Reduce `MEMORY_LIMIT` in `.env`
2. Consider using a smaller LLM model
3. Reduce `MAX_PARALLEL_INSERT` to decrease concurrent processing

### Container Won't Start

Check logs for errors:

```bash
docker compose logs
# For specific instance
docker compose --env-file .env.instance1 logs
```

Common issues include:
- Port conflicts (change `PORT` in `.env` or use different values per instance)
- Container name conflicts (ensure `CONTAINER_NAME` is unique)
- Missing or invalid API keys
- Insufficient disk space
- Data directory conflicts (ensure `INSTANCE_NAME` is unique)

## Advanced Usage

### Custom Models

You can use any model supported by Ollama or OpenAI by changing the `LLM_MODEL` and `EMBEDDING_MODEL` values in your `.env` file.

### Scaling

For production deployments, consider:
1. Adding a reverse proxy (like Nginx) for HTTPS support
2. Using Docker Swarm or Kubernetes for horizontal scaling
3. Implementing proper backup strategies for your data directory

## Contributing

Contributions to improve the Docker setup are welcome! Please submit pull requests with clear descriptions of your changes and why they're beneficial.

## License

This project is licensed under the terms of the Apache 2.0 license, following the original [LightRAG](https://github.com/HKUDS/LightRAG) project. 