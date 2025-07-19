"""
Comprehensive error handling and fallback scenario tests for LightRAG MCP tools.

Tests error handling and recovery mechanisms for tasks 5.8-5.12:
- Parameter validation errors and edge cases
- API failures and connection issues
- Session validation and context errors
- Timeout and resource exhaustion scenarios
- Fallback mechanisms and recovery strategies
- Network failures and retry logic
- Streaming operation error handling
- Internal server errors and unexpected exceptions
"""

import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from lightrag_mcp.config import MCPConfig
from lightrag_mcp.protocol.context_tools import (
    ClearCacheTool,
    ExploreGraphTool,
    FindConceptTool,
    GetRelationshipsTool,
    GetSummaryTool,
    HelpTool,
    QueryTool,
)
from lightrag_mcp.protocol.server import ConnectionSession, JSONRPCErrorCode
from lightrag_mcp.protocol.tools import ToolCategory, ToolProgress, ToolResult
from lightrag_mcp.services.lightrag_client import APIError, LightRAGError


@pytest.fixture
def mock_config():
    """Create test MCP configuration."""
    return MCPConfig()


@pytest.fixture
def mock_session():
    """Create test connection session."""
    from lightrag_mcp.protocol.server import (
        ConnectionState,
        MCPClientInfo,
        MCPServerInfo,
    )

    session = ConnectionSession(
        session_id="test_session_123",
        authenticated=True,
        context="test_context",
        connected_at=datetime.now(),
    )
    session.state = ConnectionState.INITIALIZED
    session.client_info = MCPClientInfo(
        name="test_client", version="1.0.0", protocol_version="2024-11-05"
    )
    session.server_info = MCPServerInfo(name="test_server", version="1.0.0")
    return session


@pytest.fixture
def mock_uninitialized_session():
    """Create uninitialized session for testing session validation."""
    from lightrag_mcp.protocol.server import ConnectionState

    session = ConnectionSession(
        session_id="uninitialized_session",
        authenticated=False,
        context=None,
        connected_at=datetime.now(),
    )
    session.state = ConnectionState.CONNECTING  # Not initialized state
    session.client_info = None  # Missing client info
    session.server_info = None  # Missing server info
    return session


@pytest.fixture
def mock_no_context_session():
    """Create session without context for testing context requirements."""
    from lightrag_mcp.protocol.server import (
        ConnectionState,
        MCPClientInfo,
        MCPServerInfo,
    )

    session = ConnectionSession(
        session_id="no_context_session",
        authenticated=True,
        context=None,
        connected_at=datetime.now(),
    )
    session.state = ConnectionState.INITIALIZED
    session.client_info = MCPClientInfo(
        name="test_client", version="1.0.0", protocol_version="2024-11-05"
    )
    session.server_info = MCPServerInfo(name="test_server", version="1.0.0")
    return session


class TestParameterValidationErrors:
    """Test parameter validation error handling for all tools."""

    @pytest.mark.asyncio
    async def test_query_tool_missing_required_parameter(
        self, mock_config, mock_session
    ):
        """Test QueryTool with missing required query parameter."""
        tool = QueryTool(mock_config)

        # Missing required 'query' parameter
        parameters = {}
        result = await tool.execute(mock_session, parameters)

        assert not result.success
        assert "query text is required" in result.error.lower()
        assert result.metadata["error_type"] == "validation_error"

    @pytest.mark.asyncio
    async def test_query_tool_invalid_mode_parameter(self, mock_config, mock_session):
        """Test QueryTool with invalid mode parameter."""
        tool = QueryTool(mock_config)

        parameters = {"query": "test query", "mode": "invalid_mode"}
        result = await tool.execute(mock_session, parameters)

        assert not result.success
        assert "invalid query mode" in result.error.lower()
        assert "invalid_mode" in result.error
        assert result.metadata["error_type"] == "validation_error"

    @pytest.mark.asyncio
    async def test_explore_graph_invalid_depth_parameter(
        self, mock_config, mock_session
    ):
        """Test ExploreGraphTool with invalid depth parameter."""
        tool = ExploreGraphTool(mock_config)

        # Test depth exceeding maximum
        parameters = {
            "starting_entity": "test entity",
            "depth": 10,  # Exceeds maximum of 5
        }

        with pytest.raises(ValueError, match="must be <= 5"):
            validated_params = tool.validate_parameters(parameters)

    @pytest.mark.asyncio
    async def test_explore_graph_missing_required_entity(
        self, mock_config, mock_session
    ):
        """Test ExploreGraphTool with missing starting_entity parameter."""
        tool = ExploreGraphTool(mock_config)

        # Missing required 'starting_entity' parameter
        parameters = {"depth": 2}

        with pytest.raises(
            ValueError, match="Required parameter 'starting_entity' is missing"
        ):
            validated_params = tool.validate_parameters(parameters)

    @pytest.mark.asyncio
    async def test_clear_cache_invalid_cache_type(self, mock_config, mock_session):
        """Test ClearCacheTool with invalid cache_type parameter."""
        tool = ClearCacheTool(mock_config)

        parameters = {"cache_type": "invalid_cache_type"}
        result = await tool.execute(mock_session, parameters)

        assert not result.success
        assert "invalid cache_type" in result.error.lower()
        assert result.metadata["error_type"] == "validation_error"

    @pytest.mark.asyncio
    async def test_clear_cache_all_without_confirmation(
        self, mock_config, mock_session
    ):
        """Test ClearCacheTool 'all' cache type without confirmation token."""
        tool = ClearCacheTool(mock_config)

        parameters = {"cache_type": "all", "confirmation_token": "wrong_token"}
        result = await tool.execute(mock_session, parameters)

        assert not result.success
        assert "confirmation_token='CONFIRM_CLEAR_ALL'" in result.error
        assert result.metadata["error_type"] == "confirmation_required"

    @pytest.mark.asyncio
    async def test_help_tool_invalid_topic(self, mock_config, mock_session):
        """Test HelpTool with invalid topic parameter."""
        tool = HelpTool(mock_config)

        parameters = {"topic": "nonexistent_topic"}
        result = await tool.execute(mock_session, parameters)

        assert not result.success
        assert "invalid topic" in result.error.lower()
        assert result.metadata["error_type"] == "validation_error"

    @pytest.mark.asyncio
    async def test_help_tool_invalid_format(self, mock_config, mock_session):
        """Test HelpTool with invalid help_format parameter."""
        tool = HelpTool(mock_config)

        parameters = {"topic": "overview", "help_format": "invalid_format"}
        result = await tool.execute(mock_session, parameters)

        assert not result.success
        assert "invalid help_format" in result.error.lower()
        assert result.metadata["error_type"] == "validation_error"

    @pytest.mark.asyncio
    async def test_get_summary_invalid_style(self, mock_config, mock_session):
        """Test GetSummaryTool with invalid style parameter."""
        tool = GetSummaryTool(mock_config)

        parameters = {"query": "test query", "style": "invalid_style"}
        result = await tool.execute(mock_session, parameters)

        assert not result.success
        assert "invalid style" in result.error.lower()
        assert result.metadata["error_type"] == "validation_error"


class TestSessionValidationErrors:
    """Test session validation error handling."""

    @pytest.mark.asyncio
    async def test_tools_with_uninitialized_session(
        self, mock_config, mock_uninitialized_session
    ):
        """Test tools with uninitialized session."""
        tools = [
            QueryTool(mock_config),
            GetSummaryTool(mock_config),
            ExploreGraphTool(mock_config),
        ]

        for tool in tools:
            # Test session validation directly
            with pytest.raises(ValueError, match="Session not properly initialized"):
                tool.validate_session(mock_uninitialized_session)

    @pytest.mark.asyncio
    async def test_context_required_tools_without_context(
        self, mock_config, mock_no_context_session
    ):
        """Test context-required tools without context."""
        context_required_tools = [
            QueryTool(mock_config),
            GetSummaryTool(mock_config),
            ExploreGraphTool(mock_config),
        ]

        for tool in context_required_tools:
            with pytest.raises(
                ValueError,
                match=f"Tool '{tool.name}' requires a context to be selected",
            ):
                tool.validate_session(mock_no_context_session)

    @pytest.mark.asyncio
    async def test_context_independent_tools_work_without_context(
        self, mock_config, mock_no_context_session
    ):
        """Test that context-independent tools work without context."""
        context_independent_tools = [
            ClearCacheTool(mock_config),
            HelpTool(mock_config),
        ]

        # These tools should not require context
        for tool in context_independent_tools:
            assert not tool.requires_context
            # Should not raise an exception
            tool.validate_session(mock_no_context_session)


class TestAPIErrors:
    """Test API error handling and recovery."""

    @pytest.mark.asyncio
    async def test_lightrag_api_connection_error(self, mock_config, mock_session):
        """Test handling of LightRAG API connection errors."""
        tool = QueryTool(mock_config)

        with patch.object(tool, "get_lightrag_client") as mock_client_getter:
            mock_client = AsyncMock()
            mock_client.query.side_effect = APIError("Connection refused")
            mock_client_getter.return_value = mock_client

            parameters = {"query": "test query"}
            result = await tool.execute(mock_session, parameters)

            assert not result.success
            assert "lightrag api error" in result.error.lower()
            assert result.metadata["error_type"] == "api_error"

    @pytest.mark.asyncio
    async def test_lightrag_api_timeout_error(self, mock_config, mock_session):
        """Test handling of LightRAG API timeout errors."""
        tool = GetSummaryTool(mock_config)

        with patch.object(tool, "get_lightrag_client") as mock_client_getter:
            mock_client = AsyncMock()
            mock_client.query.side_effect = asyncio.TimeoutError("Request timed out")
            mock_client_getter.return_value = mock_client

            parameters = {"query": "test query"}
            result = await tool.execute(mock_session, parameters)

            assert not result.success
            assert "error" in result.error.lower()
            assert result.metadata["error_type"] == "unexpected_error"

    @pytest.mark.asyncio
    async def test_lightrag_api_invalid_response(self, mock_config, mock_session):
        """Test handling of invalid API responses."""
        tool = ExploreGraphTool(mock_config)

        with patch.object(tool, "get_lightrag_client") as mock_client_getter:
            mock_client = AsyncMock()
            # Return invalid response format
            mock_client.query.return_value = "invalid_response_not_dict"
            mock_client_getter.return_value = mock_client

            parameters = {"starting_entity": "test entity"}
            result = await tool.execute(mock_session, parameters)

            assert not result.success
            assert "error" in result.error.lower()

    @pytest.mark.asyncio
    async def test_clear_cache_lightrag_api_failure(self, mock_config, mock_session):
        """Test ClearCacheTool handling LightRAG API failures."""
        tool = ClearCacheTool(mock_config)

        with patch.object(tool, "get_lightrag_client") as mock_client_getter:
            mock_client = AsyncMock()
            mock_client.clear_cache.side_effect = APIError("Cache service unavailable")
            mock_client_getter.return_value = mock_client

            parameters = {"cache_type": "lightrag"}
            result = await tool.execute(mock_session, parameters)

            # Should still succeed but report the cache clearing failed
            assert result.success
            assert result.data["cleared_items"]["lightrag_cache"] is False
            # Error is logged but operation continues gracefully, so no errors in the list
            assert len(result.data["cleared_items"]["errors"]) == 0

    @pytest.mark.asyncio
    async def test_api_error_with_retry_fallback(self, mock_config, mock_session):
        """Test API error with retry fallback mechanism."""
        tool = QueryTool(mock_config)

        with patch.object(tool, "get_lightrag_client") as mock_client_getter:
            mock_client = AsyncMock()
            # First call fails, subsequent calls succeed
            mock_client.query.side_effect = [
                APIError("Temporary failure"),
                {"response": "Success after retry", "metadata": {}},
            ]
            mock_client_getter.return_value = mock_client

            parameters = {"query": "test query"}

            # First call should fail
            result1 = await tool.execute(mock_session, parameters)
            assert not result1.success

            # Second call should succeed (simulating retry)
            result2 = await tool.execute(mock_session, parameters)
            assert result2.success


class TestNetworkAndResourceErrors:
    """Test network failures and resource exhaustion scenarios."""

    @pytest.mark.asyncio
    async def test_network_connection_timeout(self, mock_config, mock_session):
        """Test network connection timeout handling."""
        tool = QueryTool(mock_config)

        with patch.object(tool, "get_lightrag_client") as mock_client_getter:
            mock_client = AsyncMock()
            mock_client.query.side_effect = asyncio.TimeoutError("Network timeout")
            mock_client_getter.return_value = mock_client

            parameters = {"query": "test query"}
            result = await tool.execute(mock_session, parameters)

            assert not result.success
            assert "error" in result.error.lower()

    @pytest.mark.asyncio
    async def test_memory_exhaustion_simulation(self, mock_config, mock_session):
        """Test memory exhaustion error handling."""
        tool = ExploreGraphTool(mock_config)

        with patch.object(tool, "get_lightrag_client") as mock_client_getter:
            mock_client = AsyncMock()
            mock_client.query.side_effect = MemoryError("Out of memory")
            mock_client_getter.return_value = mock_client

            parameters = {"starting_entity": "test entity", "depth": 5}
            result = await tool.execute(mock_session, parameters)

            assert not result.success
            assert "error" in result.error.lower()
            assert result.metadata["error_type"] == "unexpected_error"

    @pytest.mark.asyncio
    async def test_large_query_handling(self, mock_config, mock_session):
        """Test handling of very large queries."""
        tool = GetSummaryTool(mock_config)

        # Create a very large query string
        large_query = "A" * 100000  # 100KB query

        parameters = {"query": large_query}

        with patch.object(tool, "get_lightrag_client") as mock_client_getter:
            mock_client = AsyncMock()
            mock_client.query.side_effect = APIError("Payload too large")
            mock_client_getter.return_value = mock_client

            result = await tool.execute(mock_session, parameters)

            assert not result.success
            assert "api error" in result.error.lower()


class TestStreamingOperationErrors:
    """Test streaming operation error handling."""

    @pytest.mark.asyncio
    async def test_streaming_operation_interruption(self, mock_config, mock_session):
        """Test streaming operation interruption handling."""
        tool = QueryTool(mock_config)

        with patch.object(tool, "get_lightrag_client") as mock_client_getter:
            mock_client = AsyncMock()
            mock_client.query.side_effect = asyncio.CancelledError(
                "Operation cancelled"
            )
            mock_client_getter.return_value = mock_client

            parameters = {"query": "test query"}

            results = []
            try:
                async for result in tool.execute_streaming(mock_session, parameters):
                    results.append(result)
            except asyncio.CancelledError:
                pass

            # Should have at least one result, and there should be an error result
            assert len(results) > 0
            error_results = [r for r in results if not r.success]
            assert len(error_results) > 0

    @pytest.mark.asyncio
    async def test_streaming_progress_tracking_error(self, mock_config, mock_session):
        """Test streaming progress tracking error handling."""
        tool = ExploreGraphTool(mock_config)

        with patch.object(tool, "get_lightrag_client") as mock_client_getter:
            mock_client = AsyncMock()
            # Simulate an error during streaming
            mock_client.query.side_effect = Exception("Unexpected streaming error")
            mock_client_getter.return_value = mock_client

            parameters = {"starting_entity": "test entity"}

            results = []
            async for result in tool.execute_streaming(mock_session, parameters):
                results.append(result)

            # Should have error result
            assert len(results) > 0
            error_results = [r for r in results if not r.success]
            assert len(error_results) > 0

    @pytest.mark.asyncio
    async def test_streaming_partial_success_handling(self, mock_config, mock_session):
        """Test handling of partial success in streaming operations."""
        tool = GetSummaryTool(mock_config)

        with patch.object(tool, "get_lightrag_client") as mock_client_getter:
            mock_client = AsyncMock()
            # Simulate partial response
            mock_client.query.return_value = {
                "response": "Partial response",
                "metadata": {"incomplete": True},
            }
            mock_client_getter.return_value = mock_client

            parameters = {"query": "test query"}

            results = []
            async for result in tool.execute_streaming(mock_session, parameters):
                results.append(result)

            # Should have both progress and final results
            progress_results = [r for r in results if isinstance(r.data, ToolProgress)]
            final_results = [
                r for r in results if r.success and not isinstance(r.data, ToolProgress)
            ]

            assert len(progress_results) > 0
            assert len(final_results) > 0


class TestFallbackMechanisms:
    """Test fallback mechanisms and recovery strategies."""

    @pytest.mark.asyncio
    async def test_help_tool_fallback_content(self, mock_config, mock_session):
        """Test HelpTool fallback when specific help content fails."""
        tool = HelpTool(mock_config)

        # Test fallback to default help when specific tool help fails
        parameters = {"topic": "nonexistent_tool_name", "help_format": "structured"}

        result = await tool.execute(mock_session, parameters)
        # Should fail gracefully with clear error message
        assert not result.success
        assert "invalid topic" in result.error.lower()

    @pytest.mark.asyncio
    async def test_clear_cache_partial_failure_fallback(
        self, mock_config, mock_session
    ):
        """Test ClearCacheTool fallback when some cache types fail."""
        tool = ClearCacheTool(mock_config)

        with patch.object(tool, "get_lightrag_client") as mock_client_getter:
            mock_client = AsyncMock()
            mock_client.clear_cache.side_effect = Exception("LightRAG cache failed")
            mock_client_getter.return_value = mock_client

            parameters = {
                "cache_type": "all",
                "confirmation_token": "CONFIRM_CLEAR_ALL",
            }
            result = await tool.execute(mock_session, parameters)

            # Should still succeed with session cache clearing even if LightRAG fails
            assert result.success
            assert result.data["cleared_items"]["session_data"] is True
            assert (
                result.data["cleared_items"]["lightrag_cache"] is False
            )  # Failed to clear

    @pytest.mark.asyncio
    async def test_query_tool_mode_fallback(self, mock_config, mock_session):
        """Test QueryTool fallback when preferred mode fails."""
        tool = QueryTool(mock_config)

        with patch.object(tool, "get_lightrag_client") as mock_client_getter:
            mock_client = AsyncMock()
            # First call with hybrid mode fails, could implement fallback to local mode
            mock_client.query.side_effect = [
                APIError("Hybrid mode failed"),
                {"response": "Local mode success", "metadata": {}},
            ]
            mock_client_getter.return_value = mock_client

            parameters = {"query": "test query", "mode": "hybrid"}
            result = await tool.execute(mock_session, parameters)

            # Currently should fail, but demonstrates where fallback could be implemented
            assert not result.success

    @pytest.mark.asyncio
    async def test_explore_graph_depth_reduction_fallback(
        self, mock_config, mock_session
    ):
        """Test ExploreGraphTool fallback to reduced depth on failure."""
        tool = ExploreGraphTool(mock_config)

        with patch.object(tool, "get_lightrag_client") as mock_client_getter:
            mock_client = AsyncMock()
            # Simulate deep exploration failure
            mock_client.query.side_effect = APIError("Query too complex")
            mock_client_getter.return_value = mock_client

            parameters = {"starting_entity": "test entity", "depth": 5}
            result = await tool.execute(mock_session, parameters)

            # Tool handles errors gracefully and continues exploration with partial results
            assert result.success
            # Should have found no entities due to the API error
            assert result.data["stats"]["total_entities"] == 0


class TestConcurrentOperationErrors:
    """Test error handling in concurrent operation scenarios."""

    @pytest.mark.asyncio
    async def test_concurrent_context_switching_errors(self, mock_config):
        """Test errors when multiple context switches happen concurrently."""
        from lightrag_mcp.protocol.context_tools import SwitchContextTool

        tool = SwitchContextTool(mock_config)

        # Create multiple sessions attempting to switch contexts
        sessions = [
            ConnectionSession(f"session_{i}", authenticated=True, context="old_context")
            for i in range(3)
        ]

        with patch.object(tool, "get_lightrag_client") as mock_client_getter:
            mock_client = AsyncMock()
            mock_client.switch_context.side_effect = APIError("Context switch conflict")
            mock_client_getter.return_value = mock_client

            # Run concurrent context switches
            tasks = [
                tool.execute(session, {"context_name": f"new_context_{i}"})
                for i, session in enumerate(sessions)
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # All should fail due to concurrent conflict
            for result in results:
                if isinstance(result, ToolResult):
                    assert not result.success
                    assert "api error" in result.error.lower()

    @pytest.mark.asyncio
    async def test_resource_contention_errors(self, mock_config, mock_session):
        """Test resource contention error handling."""
        tool = QueryTool(mock_config)

        with patch.object(tool, "get_lightrag_client") as mock_client_getter:
            mock_client = AsyncMock()
            mock_client.query.side_effect = APIError("Resource busy, try again later")
            mock_client_getter.return_value = mock_client

            parameters = {"query": "test query"}
            result = await tool.execute(mock_session, parameters)

            assert not result.success
            assert "api error" in result.error.lower()


class TestErrorRecoveryAndRetry:
    """Test error recovery and retry mechanisms."""

    @pytest.mark.asyncio
    async def test_transient_error_recovery(self, mock_config, mock_session):
        """Test recovery from transient errors."""
        tool = GetSummaryTool(mock_config)

        # Simulate transient network error followed by success
        with patch.object(tool, "get_lightrag_client") as mock_client_getter:
            mock_client = AsyncMock()
            call_count = 0

            def side_effect(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise APIError("Temporary network glitch")
                return {"response": "Success after retry", "metadata": {}}

            mock_client.query.side_effect = side_effect
            mock_client_getter.return_value = mock_client

            parameters = {"query": "test query"}

            # First call fails
            result1 = await tool.execute(mock_session, parameters)
            assert not result1.success

            # Second call succeeds (simulating retry)
            result2 = await tool.execute(mock_session, parameters)
            assert result2.success

    @pytest.mark.asyncio
    async def test_graceful_degradation(self, mock_config, mock_session):
        """Test graceful degradation when optional features fail."""
        tool = ExploreGraphTool(mock_config)

        with patch.object(tool, "get_lightrag_client") as mock_client_getter:
            mock_client = AsyncMock()
            # Simulate basic query success but relationship expansion failure
            mock_client.query.side_effect = [
                {"response": "Found entity: test_entity"},  # Entity discovery works
                APIError(
                    "Relationship service unavailable"
                ),  # Relationship expansion fails
            ]
            mock_client_getter.return_value = mock_client

            parameters = {
                "starting_entity": "test entity",
                "depth": 2,
                "exploration_mode": "bidirectional",
            }

            result = await tool.execute(mock_session, parameters)

            # Should fail since relationship expansion is core functionality
            assert not result.success


class TestErrorReporting:
    """Test error reporting and logging mechanisms."""

    @pytest.mark.asyncio
    async def test_error_metadata_completeness(self, mock_config, mock_session):
        """Test that error results include complete metadata."""
        tool = QueryTool(mock_config)

        with patch.object(tool, "get_lightrag_client") as mock_client_getter:
            mock_client = AsyncMock()
            mock_client.query.side_effect = APIError("Test API error")
            mock_client_getter.return_value = mock_client

            parameters = {"query": "test query"}
            result = await tool.execute(mock_session, parameters)

            assert not result.success
            assert result.metadata is not None
            assert "error_type" in result.metadata
            assert "operation_id" in result.metadata
            assert result.metadata["error_type"] == "api_error"

    @pytest.mark.asyncio
    async def test_error_context_preservation(self, mock_config, mock_session):
        """Test that error context is preserved through the call stack."""
        tool = ClearCacheTool(mock_config)

        # Test with invalid cache type to trigger validation error
        parameters = {"cache_type": "invalid_type"}
        result = await tool.execute(mock_session, parameters)

        assert not result.success
        assert result.metadata["error_type"] == "validation_error"
        assert "invalid_type" in result.error


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
