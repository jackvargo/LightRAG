"""
Pytest configuration and fixtures for MCP tests

This module provides common fixtures and configuration for MCP protocol tests.
"""

import asyncio
import uuid
from typing import AsyncGenerator, Generator
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from lightrag_mcp.config import MCPConfig
from lightrag_mcp.main import app
from lightrag_mcp.protocol.server import (
    ConnectionSession,
    MCPClientInfo,
    MCPProtocolServer,
    MCPProtocolValidator,
)


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_client() -> Generator[TestClient, None, None]:
    """Create a test client for the FastAPI application."""
    with TestClient(app) as client:
        yield client


@pytest.fixture
def mock_config() -> MagicMock:
    """Create a mock MCP configuration."""
    config = MagicMock(spec=MCPConfig)
    config.mcp = MagicMock()
    config.mcp.protocol_version = "2024-11-05"
    config.mcp.enable_tools = True
    config.mcp.enable_resources = True
    config.mcp.enable_prompts = True
    config.mcp.enable_logging = True
    config.mcp.max_message_size = 1024 * 1024  # 1MB
    config.mcp.max_parameter_depth = 10
    config.mcp.session_timeout_minutes = 30
    config.mcp.heartbeat_interval_seconds = 60

    # Add LightRAG client configuration attributes
    config.lightrag_url = "http://localhost:9621"
    config.lightrag_username = "admin"
    config.lightrag_password = "admin123"

    return config


@pytest.fixture
def protocol_validator() -> MCPProtocolValidator:
    """Create a protocol validator instance."""
    return MCPProtocolValidator()


@pytest_asyncio.fixture
async def protocol_server(mock_config) -> AsyncGenerator[MCPProtocolServer, None]:
    """Create a protocol server instance."""
    server = MCPProtocolServer(mock_config)
    yield server
    # Cleanup any remaining sessions
    for session_id in list(server.sessions.keys()):
        await server.cleanup_session(session_id)


@pytest_asyncio.fixture
async def test_session(protocol_server) -> AsyncGenerator[ConnectionSession, None]:
    """Create a test session."""
    session_id = f"test-session-{uuid.uuid4()}"
    session = await protocol_server.create_session(session_id)
    yield session
    # Cleanup
    if session_id in protocol_server.sessions:
        await protocol_server.cleanup_session(session_id)


@pytest_asyncio.fixture
async def initialized_session(
    protocol_server,
) -> AsyncGenerator[ConnectionSession, None]:
    """Create an initialized test session."""
    session_id = f"initialized-session-{uuid.uuid4()}"
    session = await protocol_server.create_session(session_id)

    # Initialize the session
    client_info = MCPClientInfo(
        name="test-client", version="1.0.0", protocol_version="2024-11-05"
    )
    capabilities = {"tools": {}, "resources": {}, "prompts": {}}

    await protocol_server.initialize_session(session, client_info, capabilities)

    yield session

    # Cleanup
    if session_id in protocol_server.sessions:
        await protocol_server.cleanup_session(session_id)


@pytest.fixture
def sample_valid_request() -> dict:
    """Create a sample valid JSON-RPC request."""
    return {
        "jsonrpc": "2.0",
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "clientInfo": {"name": "test-client", "version": "1.0.0"},
            "capabilities": {"tools": {}},
        },
        "id": "test-request-123",
    }


@pytest.fixture
def sample_valid_response() -> dict:
    """Create a sample valid JSON-RPC response."""
    return {
        "jsonrpc": "2.0",
        "result": {
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "lightrag-mcp-server", "version": "0.1.0"},
            "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
        },
        "id": "test-request-123",
    }


@pytest.fixture
def sample_error_response() -> dict:
    """Create a sample JSON-RPC error response."""
    return {
        "jsonrpc": "2.0",
        "error": {
            "code": -32600,
            "message": "Invalid Request",
            "data": {"details": "The JSON sent is not a valid Request object."},
        },
        "id": "test-request-123",
    }


@pytest.fixture
def sample_tool_call_request() -> dict:
    """Create a sample tool call request."""
    return {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "test_tool",
            "arguments": {"param1": "value1", "param2": 42, "param3": True},
        },
        "id": "tool-call-123",
    }


@pytest.fixture
def sample_invalid_requests() -> list:
    """Create a list of sample invalid JSON-RPC requests for testing."""
    return [
        # Missing jsonrpc field
        {"method": "test", "id": "1"},
        # Invalid jsonrpc version
        {"jsonrpc": "1.0", "method": "test", "id": "2"},
        # Missing method field
        {"jsonrpc": "2.0", "id": "3"},
        # Invalid method name format
        {"jsonrpc": "2.0", "method": "123invalid", "id": "4"},
        # Invalid ID format (too long)
        {"jsonrpc": "2.0", "method": "test", "id": "a" * 100},
    ]


@pytest.fixture
def sample_invalid_responses() -> list:
    """Create a list of sample invalid JSON-RPC responses for testing."""
    return [
        # Missing both result and error
        {"jsonrpc": "2.0", "id": "1"},
        # Has both result and error
        {
            "jsonrpc": "2.0",
            "result": {"status": "success"},
            "error": {"code": -32000, "message": "Error"},
            "id": "2",
        },
        # Invalid jsonrpc version
        {"jsonrpc": "1.0", "result": {"status": "success"}, "id": "3"},
        # Missing jsonrpc field
        {"result": {"status": "success"}, "id": "4"},
    ]


# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "performance: Performance tests")
    config.addinivalue_line("markers", "slow: Slow running tests")


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers based on test location."""
    for item in items:
        # Add markers based on test file location
        if "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        elif "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        elif "performance" in str(item.fspath):
            item.add_marker(pytest.mark.performance)
            item.add_marker(pytest.mark.slow)


# Async test configuration
@pytest_asyncio.fixture(scope="session")
def asyncio_mode():
    """Set asyncio mode for pytest-asyncio."""
    return "auto"
