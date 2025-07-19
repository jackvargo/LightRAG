"""
Comprehensive tests for new LightRAG MCP tools and enhanced functionality.

Tests the tools and features implemented in tasks 5.8-5.12:
- GetSummaryTool (Task 5.8)
- ExploreGraphTool (Task 5.9)
- Enhanced relationship depth parameters (Task 5.10)
- ClearCacheTool (Task 5.11)
- HelpTool (Task 5.12)
"""

import json
import uuid
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
from lightrag_mcp.protocol.server import ConnectionSession
from lightrag_mcp.protocol.tools import ToolCategory, ToolProgress, ToolResult
from lightrag_mcp.services.lightrag_client import APIError


@pytest.fixture
def mock_config():
    """Create test MCP configuration."""
    return MCPConfig()


@pytest.fixture
def mock_session():
    """Create test connection session."""
    return ConnectionSession(
        session_id="test_session_123",
        authenticated=True,
        context="test_context",
        connected_at=datetime.now(),
    )


@pytest.fixture
def mock_lightrag_client():
    """Create mock LightRAG client."""
    client = AsyncMock()
    # Default successful responses
    client.query.return_value = {
        "response": "Test response",
        "metadata": {"query_time": 1.5, "tokens_used": 150},
    }
    client.clear_cache.return_value = {"success": True, "status": "success"}
    return client


class TestGetSummaryTool:
    """Comprehensive tests for GetSummaryTool (Task 5.8)."""

    @pytest.fixture
    def tool(self, mock_config):
        """Create GetSummaryTool instance."""
        return GetSummaryTool(mock_config)

    def test_tool_properties(self, tool):
        """Test GetSummaryTool basic properties."""
        assert tool.name == "get_summary"
        assert "conversational, chat-style summaries" in tool.description
        assert tool.category == ToolCategory.QUERY_OPERATIONS
        assert tool.requires_context is True

        # Check parameters
        param_names = [p.name for p in tool.parameters]
        expected_params = [
            "query",
            "style",
            "length",
            "focus",
            "include_examples",
            "context_mode",
        ]
        for param in expected_params:
            assert param in param_names

    @pytest.mark.asyncio
    async def test_conversational_style_summary(
        self, tool, mock_session, mock_lightrag_client
    ):
        """Test conversational style summary generation."""
        with patch.object(
            tool, "get_lightrag_client", return_value=mock_lightrag_client
        ):
            mock_lightrag_client.query.return_value = {
                "response": "Let me explain the authentication system in a conversational way...",
                "metadata": {"query_time": 2.1, "tokens_used": 200},
            }

            parameters = {
                "query": "How does authentication work?",
                "style": "conversational",
                "length": "medium",
                "focus": "overview",
            }

            result = await tool.execute(mock_session, parameters)

            assert result.success
            assert "summary" in result.data
            assert result.data["style"] == "conversational"
            assert result.data["length"] == "medium"
            assert result.data["query"] == parameters["query"]
            assert result.data["context_mode"] == "smart"

            # Verify conversational formatting
            summary = result.data["summary"]
            assert len(summary) > 0

    @pytest.mark.asyncio
    async def test_technical_style_summary(
        self, tool, mock_session, mock_lightrag_client
    ):
        """Test detailed style summary with examples."""
        with patch.object(
            tool, "get_lightrag_client", return_value=mock_lightrag_client
        ):
            mock_lightrag_client.query.return_value = {
                "response": "Technical details: Authentication uses JWT tokens with RS256 encryption...",
                "metadata": {"query_time": 1.8, "tokens_used": 180},
            }

            parameters = {
                "query": "Authentication implementation details",
                "style": "detailed",
                "length": "long",
                "focus": "technical",
                "include_examples": True,
            }

            result = await tool.execute(mock_session, parameters)

            assert result.success
            assert result.data["include_examples"] is True
            assert result.data["focus"] == "technical"

            # Verify technical formatting
            summary = result.data["summary"]
            assert len(summary) > 0

    @pytest.mark.asyncio
    async def test_streaming_execution(self, tool, mock_session, mock_lightrag_client):
        """Test GetSummaryTool streaming execution."""
        with patch.object(
            tool, "get_lightrag_client", return_value=mock_lightrag_client
        ):
            parameters = {
                "query": "What is this project about?",
                "style": "conversational",
            }

            results = []
            async for result in tool.execute_streaming(mock_session, parameters):
                results.append(result)

            # Should have progress updates and final result
            assert len(results) >= 5  # Multiple progress steps + final result

            # Check progress sequence
            progress_results = [r for r in results if isinstance(r.data, ToolProgress)]
            assert len(progress_results) >= 4

            # Final result should be successful
            final_result = results[-1]
            assert final_result.success
            assert "summary" in final_result.data

    @pytest.mark.asyncio
    async def test_error_handling(self, tool, mock_session, mock_lightrag_client):
        """Test GetSummaryTool error handling."""
        with patch.object(
            tool, "get_lightrag_client", return_value=mock_lightrag_client
        ):
            mock_lightrag_client.query.side_effect = APIError("Query failed")

            parameters = {"query": "Test query"}
            result = await tool.execute(mock_session, parameters)

            assert not result.success
            assert "error" in result.error.lower()
            assert result.metadata["error_type"] == "api_error"


class TestExploreGraphTool:
    """Comprehensive tests for ExploreGraphTool (Task 5.9)."""

    @pytest.fixture
    def tool(self, mock_config):
        """Create ExploreGraphTool instance."""
        return ExploreGraphTool(mock_config)

    def test_tool_properties(self, tool):
        """Test ExploreGraphTool basic properties."""
        assert tool.name == "explore_graph"
        assert (
            "explore" in tool.description.lower()
            and "graph" in tool.description.lower()
        )
        assert tool.category == ToolCategory.GRAPH_EXPLORATION
        assert tool.requires_context is True

        # Check depth parameter constraints
        depth_param = next((p for p in tool.parameters if p.name == "depth"), None)
        assert depth_param is not None
        assert depth_param.minimum == 1
        assert depth_param.maximum == 5
        assert depth_param.default == 1

    @pytest.mark.asyncio
    async def test_basic_graph_exploration(
        self, tool, mock_session, mock_lightrag_client
    ):
        """Test basic graph exploration from starting entity."""
        with patch.object(
            tool, "get_lightrag_client", return_value=mock_lightrag_client
        ):
            # Mock entity search response
            mock_lightrag_client.query.side_effect = [
                # First call - find starting entity
                {"response": "Found entity: authentication\nEntity ID: auth_001"},
                # Second call - explore relationships
                {
                    "response": "Relationships:\n- authentication -> user_management (IMPLEMENTS)\n- authentication -> security (PART_OF)"
                },
            ]

            parameters = {
                "starting_entity": "authentication",
                "depth": 2,
                "exploration_mode": "bidirectional",
                "output_format": "network",
            }

            result = await tool.execute(mock_session, parameters)

            assert result.success
            assert "exploration_results" in result.data
            assert result.data["starting_entity"] == "authentication"
            assert result.data["depth"] == 2
            assert result.data["exploration_mode"] == "bidirectional"
            assert result.data["output_format"] == "network"

            # Verify relationship structure
            exploration_results = result.data["exploration_results"]
            assert "levels" in exploration_results or "nodes" in exploration_results

    @pytest.mark.asyncio
    async def test_hierarchical_output_format(
        self, tool, mock_session, mock_lightrag_client
    ):
        """Test hierarchical output format for graph exploration."""
        with patch.object(
            tool, "get_lightrag_client", return_value=mock_lightrag_client
        ):
            mock_lightrag_client.query.side_effect = [
                {"response": "Found entity: user_system"},
                {
                    "response": "Level 1 relationships:\n- user_system -> authentication (HAS_COMPONENT)\n- user_system -> authorization (HAS_COMPONENT)"
                },
            ]

            parameters = {
                "starting_entity": "user system",
                "depth": 1,
                "output_format": "hierarchical",
                "max_entities_per_level": 5,
            }

            result = await tool.execute(mock_session, parameters)

            assert result.success
            assert result.data["output_format"] == "hierarchical"

            exploration_results = result.data["exploration_results"]
            assert "hierarchy" in exploration_results or "levels" in exploration_results

    @pytest.mark.asyncio
    async def test_max_depth_exploration(
        self, tool, mock_session, mock_lightrag_client
    ):
        """Test exploration with maximum depth of 5."""
        with patch.object(
            tool, "get_lightrag_client", return_value=mock_lightrag_client
        ):
            # Mock responses for multiple depth levels
            mock_responses = [
                {"response": "Found entity: root_entity"},
                {"response": "Level 1: entity_1, entity_2"},
                {"response": "Level 2: entity_3, entity_4"},
                {"response": "Level 3: entity_5, entity_6"},
                {"response": "Level 4: entity_7, entity_8"},
                {"response": "Level 5: entity_9, entity_10"},
            ]
            mock_lightrag_client.query.side_effect = mock_responses

            parameters = {
                "starting_entity": "root entity",
                "depth": 5,  # Maximum allowed depth
                "exploration_mode": "outbound",
            }

            result = await tool.execute(mock_session, parameters)

            assert result.success
            assert result.data["depth"] == 5
            # Should have called query multiple times for different levels
            assert mock_lightrag_client.query.call_count >= 3

    @pytest.mark.asyncio
    async def test_streaming_execution_with_progress(
        self, tool, mock_session, mock_lightrag_client
    ):
        """Test ExploreGraphTool streaming with progress updates."""
        with patch.object(
            tool, "get_lightrag_client", return_value=mock_lightrag_client
        ):
            mock_lightrag_client.query.side_effect = [
                {"response": "Found: test_entity"},
                {"response": "Explored 3 relationships"},
            ]

            parameters = {"starting_entity": "test entity", "depth": 2}

            results = []
            async for result in tool.execute_streaming(mock_session, parameters):
                results.append(result)

            # Should have progress updates
            progress_results = [r for r in results if isinstance(r.data, ToolProgress)]
            assert len(progress_results) >= 4

            # Check progress values increase
            progress_values = [r.data.progress for r in progress_results]
            assert progress_values == sorted(progress_values)
            assert progress_values[-1] == 1.0  # Should end at 100%


class TestEnhancedRelationshipDepth:
    """Test enhanced relationship depth parameters (Task 5.10)."""

    @pytest.fixture
    def query_tool(self, mock_config):
        return QueryTool(mock_config)

    @pytest.fixture
    def find_concept_tool(self, mock_config):
        return FindConceptTool(mock_config)

    @pytest.fixture
    def get_relationships_tool(self, mock_config):
        return GetRelationshipsTool(mock_config)

    def test_query_tool_relationship_depth_parameters(self, query_tool):
        """Test QueryTool has relationship depth parameters."""
        param_names = [p.name for p in query_tool.parameters]
        assert "relationship_depth" in param_names
        assert "relationship_types" in param_names

        depth_param = next(
            (p for p in query_tool.parameters if p.name == "relationship_depth"), None
        )
        assert depth_param.minimum == 0
        assert depth_param.maximum == 3
        assert depth_param.default == 1

    @pytest.mark.asyncio
    async def test_query_with_relationship_depth(
        self, query_tool, mock_session, mock_lightrag_client
    ):
        """Test QueryTool with relationship depth traversal."""
        with patch.object(
            query_tool, "get_lightrag_client", return_value=mock_lightrag_client
        ):
            mock_lightrag_client.query.side_effect = [
                {"response": "Initial entities found", "relationships": []},
                {
                    "response": "Depth 1 relationships",
                    "relationships": [{"from": "A", "to": "B"}],
                },
                {
                    "response": "Depth 2 relationships",
                    "relationships": [{"from": "B", "to": "C"}],
                },
            ]

            parameters = {
                "query": "authentication system",
                "relationship_depth": 2,
                "relationship_types": "IMPLEMENTS,USES",
                "include_relationships": True,
            }

            result = await query_tool.execute(mock_session, parameters)

            assert result.success
            assert result.data["relationship_depth"] == 2
            assert "expanded_relationships" in result.data
            # Should have called LightRAG multiple times for depth traversal
            assert mock_lightrag_client.query.call_count >= 2

    def test_find_concept_tool_relationship_parameters(self, find_concept_tool):
        """Test FindConceptTool has relationship depth parameters."""
        param_names = [p.name for p in find_concept_tool.parameters]
        assert "include_relationships" in param_names
        assert "relationship_depth" in param_names
        assert "relationship_types" in param_names

    @pytest.mark.asyncio
    async def test_find_concept_with_relationships(
        self, find_concept_tool, mock_session, mock_lightrag_client
    ):
        """Test FindConceptTool with relationship expansion."""
        with patch.object(
            find_concept_tool, "get_lightrag_client", return_value=mock_lightrag_client
        ):
            mock_lightrag_client.query.side_effect = [
                {
                    "response": '---Entities---\n[{"entity": "authentication", "description": "Auth system"}]\n---'
                },
                {
                    "response": "Relationships for authentication",
                    "relationships": [{"from": "auth", "to": "user"}],
                },
            ]

            parameters = {
                "query": "security concepts",
                "include_relationships": True,
                "relationship_depth": 2,
                "top_k": 5,
            }

            result = await find_concept_tool.execute(mock_session, parameters)

            assert result.success
            assert "include_relationships" in result.data
            assert result.data["include_relationships"] is True

    def test_get_relationships_tool_depth_parameter(self, get_relationships_tool):
        """Test GetRelationshipsTool has multi-hop depth parameter."""
        param_names = [p.name for p in get_relationships_tool.parameters]
        assert "relationship_depth" in param_names

        depth_param = next(
            (
                p
                for p in get_relationships_tool.parameters
                if p.name == "relationship_depth"
            ),
            None,
        )
        assert depth_param.minimum == 1
        assert depth_param.maximum == 3
        assert depth_param.default == 1


class TestClearCacheTool:
    """Comprehensive tests for ClearCacheTool (Task 5.11)."""

    @pytest.fixture
    def tool(self, mock_config):
        """Create ClearCacheTool instance."""
        return ClearCacheTool(mock_config)

    def test_tool_properties(self, tool):
        """Test ClearCacheTool basic properties."""
        assert tool.name == "clear_cache"
        assert "clear various types of caches" in tool.description.lower()
        assert tool.category == ToolCategory.SYSTEM_UTILITIES
        assert tool.requires_context is False

        # Check cache_type parameter
        cache_type_param = next(
            (p for p in tool.parameters if p.name == "cache_type"), None
        )
        assert cache_type_param is not None
        assert cache_type_param.default == "session"

    @pytest.mark.asyncio
    async def test_session_cache_clearing(
        self, tool, mock_session, mock_lightrag_client
    ):
        """Test session cache clearing."""
        with patch.object(
            tool, "get_lightrag_client", return_value=mock_lightrag_client
        ):
            # Set up session with some cached data
            mock_session.resource_usage = {
                "messages_sent": 10,
                "messages_received": 8,
                "operations_started": 5,
            }
            mock_session.error_count = 2
            mock_session.last_error = "Previous error"

            parameters = {"cache_type": "session", "include_statistics": True}

            result = await tool.execute(mock_session, parameters)

            assert result.success
            assert result.data["cache_type"] == "session"
            assert result.data["cleared_items"]["session_data"] is True
            assert "summary" in result.data
            assert (
                "Session metrics have been reset" in result.data["recommendations"][0]
            )

            # Verify session was actually cleared
            assert mock_session.error_count == 0
            assert mock_session.last_error is None

    @pytest.mark.asyncio
    async def test_lightrag_cache_clearing(
        self, tool, mock_session, mock_lightrag_client
    ):
        """Test LightRAG cache clearing."""
        with patch.object(
            tool, "get_lightrag_client", return_value=mock_lightrag_client
        ):
            mock_lightrag_client.clear_cache.return_value = {
                "success": True,
                "status": "success",
            }

            parameters = {"cache_type": "lightrag", "include_statistics": True}

            result = await tool.execute(mock_session, parameters)

            assert result.success
            assert result.data["cleared_items"]["lightrag_cache"] is True
            mock_lightrag_client.clear_cache.assert_called_once()

    @pytest.mark.asyncio
    async def test_redis_cache_clearing(self, tool, mock_session):
        """Test Redis cache clearing."""
        with patch("lightrag_mcp.protocol.context_tools.redis_client") as mock_redis:
            mock_redis.keys.return_value = ["mcp:session:test:key1", "mcp:cache:key2"]
            mock_redis.delete.return_value = 2

            parameters = {"cache_type": "redis", "force_clear": False}

            result = await tool.execute(mock_session, parameters)

            assert result.success
            assert result.data["cleared_items"]["redis_keys"] == 2

    @pytest.mark.asyncio
    async def test_all_cache_clearing_with_confirmation(
        self, tool, mock_session, mock_lightrag_client
    ):
        """Test clearing all caches with proper confirmation."""
        with patch.object(
            tool, "get_lightrag_client", return_value=mock_lightrag_client
        ):
            parameters = {
                "cache_type": "all",
                "confirmation_token": "CONFIRM_CLEAR_ALL",
                "include_statistics": True,
            }

            result = await tool.execute(mock_session, parameters)

            assert result.success
            assert result.data["cache_type"] == "all"
            assert "Complete cache clear performed" in result.data["recommendations"]

    @pytest.mark.asyncio
    async def test_all_cache_clearing_without_confirmation(self, tool, mock_session):
        """Test that clearing all caches requires confirmation."""
        parameters = {"cache_type": "all", "confirmation_token": "WRONG_TOKEN"}

        result = await tool.execute(mock_session, parameters)

        assert not result.success
        assert "confirmation_token='CONFIRM_CLEAR_ALL'" in result.error
        assert result.metadata["error_type"] == "confirmation_required"

    @pytest.mark.asyncio
    async def test_streaming_cache_clearing(
        self, tool, mock_session, mock_lightrag_client
    ):
        """Test ClearCacheTool streaming execution."""
        with patch.object(
            tool, "get_lightrag_client", return_value=mock_lightrag_client
        ):
            parameters = {"cache_type": "session"}

            results = []
            async for result in tool.execute_streaming(mock_session, parameters):
                results.append(result)

            # Should have progress updates
            progress_results = [r for r in results if isinstance(r.data, ToolProgress)]
            assert len(progress_results) >= 3

            # Final result should be successful
            final_result = results[-1]
            assert final_result.success
            assert "cleared_items" in final_result.data


class TestHelpTool:
    """Comprehensive tests for HelpTool (Task 5.12)."""

    @pytest.fixture
    def tool(self, mock_config):
        """Create HelpTool instance."""
        return HelpTool(mock_config)

    def test_tool_properties(self, tool):
        """Test HelpTool basic properties."""
        assert tool.name == "help"
        assert "comprehensive help" in tool.description.lower()
        assert tool.category == ToolCategory.SYSTEM_UTILITIES
        assert tool.requires_context is False

        # Check parameters
        param_names = [p.name for p in tool.parameters]
        expected_params = [
            "topic",
            "tool_name",
            "help_format",
            "include_examples",
            "context_type",
        ]
        for param in expected_params:
            assert param in param_names

    @pytest.mark.asyncio
    async def test_overview_help_generation(self, tool, mock_session):
        """Test overview help generation."""
        parameters = {
            "topic": "overview",
            "help_format": "structured",
            "include_examples": True,
            "context_type": "intermediate",
        }

        result = await tool.execute(mock_session, parameters)

        assert result.success
        assert result.data["topic"] == "overview"
        assert "help_content" in result.data

        help_content = result.data["help_content"]
        assert "title" in help_content
        assert "sections" in help_content
        assert len(help_content["sections"]) >= 3
        assert "examples" in help_content

    @pytest.mark.asyncio
    async def test_tool_specific_help(self, tool, mock_session):
        """Test tool-specific help generation."""
        parameters = {
            "topic": "query",
            "help_format": "comprehensive",
            "include_examples": True,
            "context_type": "advanced",
        }

        result = await tool.execute(mock_session, parameters)

        assert result.success
        assert result.data["topic"] == "query"

        help_content = result.data["help_content"]
        assert "Query Tool - Detailed Guide" in help_content["title"]
        assert (
            len(help_content["sections"]) >= 4
        )  # Purpose, Parameters, Guidelines, Use Cases
        assert "examples" in help_content

    @pytest.mark.asyncio
    async def test_workflows_help(self, tool, mock_session):
        """Test workflows help generation."""
        parameters = {
            "topic": "workflows",
            "help_format": "structured",
            "context_type": "intermediate",
        }

        result = await tool.execute(mock_session, parameters)

        assert result.success
        help_content = result.data["help_content"]
        assert "workflows" in help_content["title"].lower()
        assert len(help_content["sections"]) >= 3  # Multiple workflow examples

    @pytest.mark.asyncio
    async def test_troubleshooting_help(self, tool, mock_session):
        """Test troubleshooting help generation."""
        parameters = {
            "topic": "troubleshooting",
            "help_format": "structured",
            "include_examples": True,
            "context_type": "developer",
        }

        result = await tool.execute(mock_session, parameters)

        assert result.success
        help_content = result.data["help_content"]
        assert "troubleshooting" in help_content["title"].lower()
        assert (
            "debugging_tools" in help_content
        )  # Developer context includes debugging tools

    @pytest.mark.asyncio
    async def test_best_practices_help(self, tool, mock_session):
        """Test best practices help generation."""
        parameters = {
            "topic": "best-practices",
            "help_format": "comprehensive",
            "include_examples": True,
            "context_type": "advanced",
        }

        result = await tool.execute(mock_session, parameters)

        assert result.success
        help_content = result.data["help_content"]
        assert "best practices" in help_content["title"].lower()
        assert "anti_patterns" in help_content  # Should include anti-patterns

    @pytest.mark.asyncio
    async def test_quick_format_help(self, tool, mock_session):
        """Test quick format help generation."""
        parameters = {
            "topic": "tools",
            "help_format": "quick",
            "context_type": "beginner",
        }

        result = await tool.execute(mock_session, parameters)

        assert result.success
        help_content = result.data["help_content"]
        # Quick format should have shorter content
        for section in help_content["sections"]:
            assert len(section["content"]) < 200  # Brief content

    @pytest.mark.asyncio
    async def test_invalid_topic_validation(self, tool, mock_session):
        """Test validation for invalid help topics."""
        parameters = {"topic": "invalid_topic", "help_format": "structured"}

        result = await tool.execute(mock_session, parameters)

        assert not result.success
        assert "invalid topic" in result.error.lower()
        assert result.metadata["error_type"] == "validation_error"

    @pytest.mark.asyncio
    async def test_streaming_help_generation(self, tool, mock_session):
        """Test HelpTool streaming execution."""
        parameters = {"topic": "overview", "help_format": "structured"}

        results = []
        async for result in tool.execute_streaming(mock_session, parameters):
            results.append(result)

        # Should have progress updates and final result
        progress_results = [r for r in results if isinstance(r.data, ToolProgress)]
        assert len(progress_results) >= 2

        # Final result should contain help content
        final_result = results[-1]
        assert final_result.success
        assert "help_content" in final_result.data


class TestToolIntegration:
    """Integration tests for all tools working together."""

    @pytest.mark.asyncio
    async def test_help_tool_lists_all_available_tools(self, mock_config, mock_session):
        """Test that help tool knows about all available tools."""
        help_tool = HelpTool(mock_config)

        parameters = {"topic": "tools", "help_format": "structured"}

        result = await help_tool.execute(mock_session, parameters)

        assert result.success
        help_content = result.data["help_content"]

        # Should mention all tool categories
        content_text = str(help_content).lower()
        assert "context management" in content_text
        assert "query operations" in content_text
        assert "semantic search" in content_text
        assert "graph exploration" in content_text
        assert "system utilities" in content_text

    @pytest.mark.asyncio
    async def test_all_tools_have_consistent_interfaces(self, mock_config):
        """Test that all tools follow consistent interface patterns."""
        tools = [
            GetSummaryTool(mock_config),
            ExploreGraphTool(mock_config),
            ClearCacheTool(mock_config),
            HelpTool(mock_config),
        ]

        for tool in tools:
            # All tools should have required properties
            assert hasattr(tool, "name")
            assert hasattr(tool, "description")
            assert hasattr(tool, "category")
            assert hasattr(tool, "parameters")
            assert hasattr(tool, "requires_context")
            assert hasattr(tool, "execute")
            assert hasattr(tool, "execute_streaming")

            # All tools should have valid categories
            assert isinstance(tool.category, ToolCategory)

            # All tools should have parameter lists
            assert isinstance(tool.parameters, list)


@pytest.mark.asyncio
async def test_error_handling_consistency():
    """Test that all tools handle errors consistently."""
    mock_config = MCPConfig()
    mock_session = ConnectionSession(session_id="test", authenticated=True)

    tools = [
        GetSummaryTool(mock_config),
        ExploreGraphTool(mock_config),
        ClearCacheTool(mock_config),
        HelpTool(mock_config),
    ]

    for tool in tools:
        # Test with invalid parameters
        result = await tool.execute(mock_session, {})

        # Tools should either succeed with defaults or fail gracefully
        if not result.success:
            assert result.error is not None
            assert "operation_id" in result.metadata or "error_type" in result.metadata


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
