# LightRAG MCP Server Development Workflow

This document outlines the complete development workflow for the LightRAG Model Context Protocol (MCP) Server, including setup, development practices, testing, and deployment procedures.

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Development Environment Setup](#development-environment-setup)
- [Project Structure](#project-structure)
- [Development Workflow](#development-workflow)
- [Testing Strategy](#testing-strategy)
- [Code Quality Standards](#code-quality-standards)
- [Integration with LightRAG](#integration-with-lightrag)
- [Deployment](#deployment)
- [Troubleshooting](#troubleshooting)

## Overview

The LightRAG MCP Server provides intelligent access to LightRAG knowledge graphs through the standardized Model Context Protocol (MCP). This enables AI agents and applications to interact with LightRAG's powerful knowledge graph capabilities.

### Key Features
- **Context Management**: Switch between different knowledge contexts
- **Semantic Search**: Find concepts, relationships, and documents
- **Query Processing**: Support for multiple query modes (naive, local, global, hybrid)
- **Document Access**: Retrieve full documents and processed chunks
- **Authentication**: OAuth 2.1 security with session management

## Prerequisites

### System Requirements
- **Python**: 3.10+ (required by MCP protocol)
- **Node.js**: 18+ (for WebUI development)
- **Docker**: Latest version (for containerized development)
- **UV**: Latest version (for Python dependency management)
- **Git**: Latest version

### Development Tools
- **IDE**: VS Code, PyCharm, or similar with Python support
- **Terminal**: Bash or equivalent
- **Redis**: For session caching (can be containerized)

## Development Environment Setup

### 1. Repository Setup

```bash
# Clone and navigate to project
git clone https://github.com/LightRAG-team/LightRAG.git
cd LightRAG

# Switch to MCP development branch
git checkout feature/mcp-server-implementation
```

### 2. UV Virtual Environment Setup

```bash
# Create and activate UV virtual environment for MCP development
uv venv .venv-mcp
source .venv-mcp/bin/activate

# Navigate to MCP package directory
cd lightrag_mcp

# Sync dependencies using UV
uv sync

# Activate MCP package virtual environment
source .venv/bin/activate
```

### 3. Environment Configuration

```bash
# Create environment file from template
cp .env.example .env

# Edit .env with your configuration
# Key settings:
# - LIGHTRAG_API_URL=http://localhost:9621
# - REDIS_URL=redis://localhost:6379/0
# - JWT_SECRET_KEY=your-secure-secret
```

### 4. Pre-commit Hooks Setup

```bash
# Install pre-commit hooks (run from lightrag_mcp directory)
pre-commit install

# Test hooks (optional)
pre-commit run --all-files
```

## Project Structure

```
LightRAG/
├── lightrag_mcp/                 # MCP Server Package
│   ├── __init__.py              # Package initialization
│   ├── pyproject.toml           # UV dependency management
│   ├── README.md                # Package documentation
│   ├── .env.example             # Development environment template
│   ├── .env.test                # Test environment configuration
│   ├── .pre-commit-config.yaml  # Code quality hooks
│   ├── .venv/                   # UV virtual environment
│   ├── main.py                  # FastAPI application entry point (planned)
│   ├── auth.py                  # OAuth 2.1 authentication (planned)
│   ├── config.py                # Configuration management (planned)
│   ├── protocol/                # MCP protocol implementation (planned)
│   ├── services/                # Business logic services (planned)
│   ├── models/                  # Pydantic data models (planned)
│   └── prompts/                 # Configurable prompt templates (planned)
├── tests/mcp/                   # MCP server tests (planned)
├── docs/development/            # Development documentation
├── docker-compose.yml           # Main container orchestration
├── env.example                  # Main project environment template
└── tasks/                       # Task management and tracking
```

## Development Workflow

### 1. Branch Management

```bash
# Create feature branch for specific MCP functionality
git checkout -b feature/mcp-<task-description>

# Example branches:
# - feature/mcp-lightrag-api-extensions
# - feature/mcp-server-foundation
# - feature/mcp-core-protocol
```

### 2. Development Cycle

1. **Setup**: Activate virtual environment and verify dependencies
   ```bash
   cd lightrag_mcp && source .venv/bin/activate
   ```

2. **Code**: Implement features following code quality standards
   ```bash
   # Write code with proper type hints
   # Follow black formatting (88 character line length)
   # Organize imports with isort
   ```

3. **Test**: Run tests locally before committing
   ```bash
   # Unit tests
   pytest tests/mcp/

   # Integration tests (requires running services)
   pytest tests/mcp/integration/

   # Code quality checks
   pre-commit run --all-files
   ```

4. **Commit**: Use conventional commit messages
   ```bash
   git add .
   git commit -m "feat: implement MCP context switching tool"
   ```

### 3. Integration with Existing LightRAG Services

The MCP server integrates with the existing LightRAG Docker infrastructure:

```bash
# Start main LightRAG services
docker-compose up -d

# Verify LightRAG API is running
curl http://localhost:9621/health

# Start MCP server (when implemented)
cd lightrag_mcp
uvicorn main:app --host localhost --port 8000 --reload
```

### 4. Environment Variables Integration

**Main LightRAG Environment** (`/.env`):
- Core LightRAG configuration
- Database connections
- LLM and embedding settings

**MCP-Specific Environment** (`/lightrag_mcp/.env`):
- MCP server configuration
- Authentication settings
- Redis session configuration
- Rate limiting and performance settings

## Testing Strategy

### 1. Test Structure

```
tests/mcp/
├── unit/                    # Unit tests for individual components
│   ├── test_auth.py        # Authentication tests
│   ├── test_tools.py       # MCP tools tests
│   └── test_resources.py   # MCP resources tests
├── integration/            # Integration tests
│   ├── test_full_workflow.py  # End-to-end MCP workflow
│   └── test_lightrag_integration.py  # LightRAG API integration
└── fixtures/               # Test data and fixtures
```

### 2. Testing Commands

```bash
# Run all MCP tests
pytest tests/mcp/

# Run specific test categories
pytest tests/mcp/unit/          # Unit tests only
pytest tests/mcp/integration/   # Integration tests only

# Run with coverage
pytest tests/mcp/ --cov=lightrag_mcp --cov-report=html

# Run specific test file
pytest tests/mcp/unit/test_auth.py -v
```

### 3. Test Environment Setup

```bash
# Use test environment configuration
cp lightrag_mcp/.env.test lightrag_mcp/.env

# Start test dependencies (Redis, mock services)
docker-compose -f docker-compose.test.yml up -d
```

## Code Quality Standards

### 1. Automated Quality Checks

Pre-commit hooks automatically enforce:

- **Black**: Code formatting (88 character line length)
- **isort**: Import statement organization
- **Flake8**: Code linting and style checking
- **MyPy**: Static type checking
- **YAML/TOML**: Configuration file validation

### 2. Code Style Guidelines

```python
# Type hints are required
def process_query(query: str, context: str) -> QueryResult:
    """Process a query against the specified context."""
    pass

# Use descriptive variable names
lightrag_response = await client.query(query_text)

# Follow asyncio patterns for async code
async def handle_mcp_request(request: MCPRequest) -> MCPResponse:
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=request.dict())
    return MCPResponse.parse_obj(response.json())
```

### 3. Documentation Standards

- **Docstrings**: Required for all public functions and classes
- **Type hints**: Required for all function signatures
- **Comments**: Explain complex logic and business rules
- **README updates**: Keep package documentation current

## Integration with LightRAG

### 1. API Communication

The MCP server communicates with LightRAG through its REST API:

```python
# Example integration pattern
import httpx
from lightrag_mcp.config import settings

async def query_lightrag(query: str, mode: str = "hybrid") -> dict:
    """Query LightRAG API with authentication."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.LIGHTRAG_API_URL}/query",
            json={"query": query, "mode": mode},
            auth=(settings.LIGHTRAG_API_USERNAME, settings.LIGHTRAG_API_PASSWORD),
            timeout=settings.LIGHTRAG_API_TIMEOUT
        )
        response.raise_for_status()
        return response.json()
```

### 2. Context Management

The MCP server manages LightRAG contexts through the context switching API:

```bash
# Context switching workflow
curl -X POST http://localhost:9621/switch_context \
  -H "Content-Type: application/json" \
  -d '{"context_name": "new_context"}' \
  -u admin:admin123
```

### 3. Data Flow

```
MCP Client → MCP Server → LightRAG API → Knowledge Graph
    ↑            ↓            ↓             ↓
    └─── MCP Response ← Cache ← Response ← Data
```

## Deployment

### 1. Development Deployment

```bash
# Start all services using Docker Compose
docker-compose up -d

# Start MCP server in development mode
cd lightrag_mcp
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Production Deployment

```bash
# Build MCP server image
docker build -t lightrag-mcp-server lightrag_mcp/

# Deploy with production configuration
docker-compose -f docker-compose.prod.yml up -d
```

### 3. Health Checks

```bash
# Verify services are running
curl http://localhost:9621/health     # LightRAG API
curl http://localhost:8000/health     # MCP Server
curl http://localhost:6379/ping       # Redis
```

## Troubleshooting

### Common Issues

1. **Virtual Environment Issues**
   ```bash
   # Recreate UV environment
   rm -rf .venv-mcp lightrag_mcp/.venv
   uv venv .venv-mcp
   cd lightrag_mcp && uv sync
   ```

2. **Pre-commit Hook Failures**
   ```bash
   # Fix formatting issues
   pre-commit run --all-files

   # Skip hooks for urgent commits (not recommended)
   git commit --no-verify -m "urgent fix"
   ```

3. **Docker Connection Issues**
   ```bash
   # Reset Docker environment
   docker-compose down
   docker-compose up -d

   # Check container logs
   docker-compose logs lightrag
   ```

4. **Port Conflicts**
   ```bash
   # Check port usage
   lsof -i :8000  # MCP Server
   lsof -i :9621  # LightRAG API
   lsof -i :6379  # Redis
   ```

### Debug Mode

```bash
# Enable debug logging
export MCP_SERVER_DEBUG=true
export LOG_LEVEL=DEBUG

# Start with verbose logging
uvicorn main:app --log-level debug --reload
```

### Getting Help

1. **Check logs**: Always start by checking application logs
2. **Verify configuration**: Ensure environment variables are correct
3. **Test connectivity**: Verify all services can communicate
4. **Consult documentation**: Refer to MCP protocol specification
5. **Create issues**: Report bugs in the GitHub repository

## Next Steps

After completing the development setup:

1. **Implement LightRAG API Extensions** (Phase 1)
2. **Build MCP Server Foundation** (Phase 2)
3. **Develop MCP Protocol Implementation** (Phase 3)
4. **Create MCP Tools and Resources** (Phase 4)
5. **Add Production Features** (Phase 5)

For detailed task breakdown, see `tasks/tasks-prd-mcp-server-capability.md`.
