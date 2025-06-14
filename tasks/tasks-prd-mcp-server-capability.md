# Task List: LightRAG MCP Server Capability

Based on PRD: [prd-mcp-server-capability.md](./prd-mcp-server-capability.md)

## Relevant Files

### Completed Development Setup Files
- `lightrag_mcp/pyproject.toml` - UV dependency management configuration with comprehensive dependencies and tool settings
- `lightrag_mcp/__init__.py` - Package initialization with metadata and version information  
- `lightrag_mcp/README.md` - Basic package documentation and usage instructions
- `.feature-branch-source` - Development tracking file documenting branch creation and progress

### Phase 1: LightRAG API Extensions (Planned)
- `lightrag/api/routers/document_routes.py` - Add document content and chunk retrieval endpoints
- `lightrag/api/routers/query_routes.py` - Add relationship data to query responses
- `tests/api/test_document_routes.py` - Unit tests for new document endpoints
- `tests/api/test_query_extensions.py` - Unit tests for enhanced query functionality

### Development and CI/CD Files (Planned)
- `.github/workflows/mcp-ci.yml` - GitHub Actions workflow for automated testing and deployment
- `.env.example` - Example environment variables for development setup
- `.env.test` - Test environment configuration
- `.pre-commit-config.yaml` - Pre-commit hooks configuration
- `docs/development/mcp-development-workflow.md` - Development workflow documentation

### Phase 2: MCP Server Implementation
- `lightrag_mcp/` - New directory for MCP server implementation
- `lightrag_mcp/main.py` - FastAPI application entry point for MCP server
- `lightrag_mcp/auth.py` - OAuth 2.1 authentication implementation
- `lightrag_mcp/protocol/` - MCP protocol implementation directory
- `lightrag_mcp/protocol/server.py` - Core MCP server protocol handler
- `lightrag_mcp/protocol/tools.py` - MCP tools implementation
- `lightrag_mcp/protocol/resources.py` - MCP resources implementation
- `lightrag_mcp/protocol/prompts.py` - MCP prompts implementation
- `lightrag_mcp/services/` - Business logic services directory
- `lightrag_mcp/services/lightrag_client.py` - HTTP client for LightRAG API communication
- `lightrag_mcp/services/cache_service.py` - Redis-based session caching
- `lightrag_mcp/services/context_service.py` - Context management service
- `lightrag_mcp/config.py` - Configuration management
- `lightrag_mcp/models/` - Pydantic models directory
- `lightrag_mcp/models/mcp_models.py` - MCP protocol data models
- `lightrag_mcp/models/lightrag_models.py` - LightRAG API response models
- `lightrag_mcp/prompts/templates.json` - Configurable prompt templates
- `lightrag_mcp/requirements.txt` - MCP server dependencies
- `lightrag_mcp/Dockerfile` - Container configuration
- `tests/mcp/` - MCP server test directory
- `tests/mcp/test_tools.py` - Unit tests for MCP tools
- `tests/mcp/test_resources.py` - Unit tests for MCP resources
- `tests/mcp/test_auth.py` - Unit tests for authentication
- `tests/mcp/integration/` - Integration test directory
- `tests/mcp/integration/test_full_workflow.py` - End-to-end MCP workflow tests

### Notes

- All tests should be run using `pytest` from the project root
- Use `pytest tests/api/` for LightRAG API tests and `pytest tests/mcp/` for MCP server tests
- Integration tests require both LightRAG and MCP servers to be running
- Git branches should follow the pattern `feature/mcp-<task-description>` for clear tracking

## Tasks

- [ ] 1.0 Setup Development Environment and Branch Strategy
  - [x] 1.1 Create main feature branch `feature/mcp-server-implementation` from main
  - [x] 1.2 Setup UV virtual environment: `uv venv .venv-mcp && source .venv-mcp/bin/activate`
  - [x] 1.3 Create `lightrag_mcp/pyproject.toml` with UV dependency management
  - [x] 1.4 Install MCP dependencies with UV: `uv add mcp fastapi redis pytest httpx uvicorn`
  - [ ] 1.5 Install development tools: `uv add --dev black isort flake8 mypy pre-commit`
  - [ ] 1.6 Create `.gitignore` entries for MCP artifacts (`.venv-mcp/`, `lightrag_mcp/__pycache__/`, `.env.mcp`)
  - [ ] 1.7 Setup pre-commit hooks: `pre-commit install` with black, isort, flake8, mypy
  - [ ] 1.8 Create `.env.example` and `.env.test` files for environment configuration
  - [ ] 1.9 Document development workflow in `docs/development/mcp-development-workflow.md`
  - [ ] 1.10 Setup GitHub Actions workflow for CI/CD (`.github/workflows/mcp-ci.yml`)
  - [ ] 1.11 Configure automated testing, linting, and deployment pipelines

- [ ] 2.0 Implement LightRAG API Extensions with Tests (Phase 1)
  - [ ] 2.1 Create branch `feature/mcp-lightrag-api-extensions` from main feature branch
  - [ ] 2.2 Add document content retrieval endpoint `GET /documents/{doc_id}/content`
  - [ ] 2.3 Add processed chunks endpoint `GET /documents/{doc_id}/chunks`
  - [ ] 2.4 Modify query endpoints to include optional `include_relationships` parameter
  - [ ] 2.5 Update document status models to include MIME type and file path metadata
  - [ ] 2.6 Create comprehensive test suite for new endpoints using pytest
  - [ ] 2.7 Test document content retrieval with various file types (PDF, TXT, DOCX)
  - [ ] 2.8 Test chunk retrieval and validate chunk metadata structure
  - [ ] 2.9 Test relationship data inclusion in query responses
  - [ ] 2.10 Create API documentation updates for new endpoints
  - [ ] 2.11 Run full LightRAG test suite to ensure no regressions
  - [ ] 2.12 Submit pull request with Phase 1 changes for review and merge

- [ ] 3.0 Create MCP Server Foundation with Authentication
  - [ ] 3.1 Create branch `feature/mcp-server-foundation` from main feature branch
  - [ ] 3.2 Initialize `lightrag_mcp/` directory structure with `__init__.py` files
  - [ ] 3.3 Create `lightrag_mcp/main.py` with basic FastAPI application setup
  - [ ] 3.4 Implement OAuth 2.1 authentication in `lightrag_mcp/auth.py`
  - [ ] 3.5 Setup environment configuration in `lightrag_mcp/config.py`
  - [ ] 3.6 Create LightRAG API client in `lightrag_mcp/services/lightrag_client.py`
  - [ ] 3.7 Implement health check and discovery endpoints
  - [ ] 3.8 Create authentication middleware for request validation
  - [ ] 3.9 Add comprehensive logging configuration
  - [ ] 3.10 Create unit tests for authentication and configuration
  - [ ] 3.11 Test OAuth 2.1 flow with mock authorization server
  - [ ] 3.12 Validate LightRAG API connectivity and authentication

- [ ] 4.0 Implement Core MCP Protocol and Tool Framework
  - [ ] 4.1 Create branch `feature/mcp-core-protocol` from main feature branch
  - [ ] 4.2 Implement MCP JSON-RPC protocol handler in `lightrag_mcp/protocol/server.py`
  - [ ] 4.3 Setup WebSocket and SSE support for real-time communication
  - [ ] 4.4 Create MCP capability negotiation and initialization
  - [ ] 4.5 Implement error handling with detailed error messages
  - [ ] 4.6 Create base tool framework in `lightrag_mcp/protocol/tools.py`
  - [ ] 4.7 Add tool discovery and metadata endpoints
  - [ ] 4.8 Implement streaming response handling for long-running operations
  - [ ] 4.9 Create connection lifecycle management (connect, disconnect, cleanup)
  - [ ] 4.10 Add comprehensive protocol validation and error responses
  - [ ] 4.11 Create unit tests for protocol implementation
  - [ ] 4.12 Test MCP client connection and basic protocol flow

- [ ] 5.0 Build MCP Tools for Context and Query Management
  - [ ] 5.1 Create branch `feature/mcp-tools-implementation` from main feature branch
  - [ ] 5.2 Implement `list_contexts` tool for available context enumeration
  - [ ] 5.3 Implement `switch_context` tool with progress status updates
  - [ ] 5.4 Implement `get_context_info` tool for context metadata
  - [ ] 5.5 Implement `query` tool with all mode parameters (naive, local, global, hybrid, mix)
  - [ ] 5.6 Implement semantic tools: `find_concept`, `get_relationships`, `search_docs`
  - [ ] 5.7 Implement `search_documents` tool with snippet and source references
  - [ ] 5.8 Implement `get_summary` tool for chat-style responses
  - [ ] 5.9 Implement `explore_graph` tool with configurable depth (default 1, max 5)
  - [ ] 5.10 Add relationship depth parameters to all content retrieval tools
  - [ ] 5.11 Implement `clear_cache` tool for session cache management
  - [ ] 5.12 Implement `help` tool with usage guidance and best practices
  - [ ] 5.13 Create comprehensive tool tests with mocked LightRAG responses
  - [ ] 5.14 Test error handling and fallback scenarios for each tool
  - [ ] 5.15 Validate tool parameter validation and response formatting

- [ ] 6.0 Add Document Resources and Prompt Templates
  - [ ] 6.1 Create branch `feature/mcp-resources-prompts` from main feature branch
  - [ ] 6.2 Implement `get_full_document` tool using Phase 1 LightRAG API
  - [ ] 6.3 Implement `get_processed_chunks` tool using Phase 1 LightRAG API
  - [ ] 6.4 Create MCP resources implementation in `lightrag_mcp/protocol/resources.py`
  - [ ] 6.5 Implement document resources with proper MIME types and file:// URIs
  - [ ] 6.6 Implement chunk resources with metadata and relationships
  - [ ] 6.7 Create prompt templates JSON configuration system
  - [ ] 6.8 Implement built-in prompt templates (documentation search, architecture discovery, best practices, code review)
  - [ ] 6.9 Implement User Story Context Builder prompt template
  - [ ] 6.10 Create configurable prompt loading and validation
  - [ ] 6.11 Add resource subscription and change notification support
  - [ ] 6.12 Test document and chunk resource retrieval with various file types
  - [ ] 6.13 Test prompt template loading and parameter substitution
  - [ ] 6.14 Validate MCP resource compliance with specification

- [ ] 7.0 Implement Session Management and Production Deployment
  - [ ] 7.1 Create branch `feature/mcp-session-deployment` from main feature branch
  - [ ] 7.2 Implement Redis session storage in `lightrag_mcp/services/cache_service.py`
  - [ ] 7.3 Add session-based caching with configurable TTL
  - [ ] 7.4 Implement cache invalidation on context switches
  - [ ] 7.5 Add rate limiting per user/session using Redis
  - [ ] 7.6 Create Docker configuration in `lightrag_mcp/Dockerfile`
  - [ ] 7.7 Setup environment-based configuration for different deployment environments
  - [ ] 7.8 Implement comprehensive health checks and monitoring endpoints
  - [ ] 7.9 Add production logging and error tracking
  - [ ] 7.10 Create deployment documentation with environment setup
  - [ ] 7.11 Create integration tests that validate full MCP workflow
  - [ ] 7.12 Test session persistence across connection drops
  - [ ] 7.13 Test rate limiting and cache performance under load
  - [ ] 7.14 Validate production deployment with Docker compose
  - [ ] 7.15 Run full CI/CD pipeline test on feature branch
  - [ ] 7.16 Create monitoring dashboard and alerting configuration
  - [ ] 7.17 Submit final pull request and merge feature branch to main 