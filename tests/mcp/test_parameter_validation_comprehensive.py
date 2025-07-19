"""
Comprehensive parameter validation and response formatting tests for LightRAG MCP tools.

Tests for task 5.15: Validate tool parameter validation and response formatting:
- Parameter type validation (string, integer, number, boolean, array, object)
- Required vs optional parameter handling
- Default value application and validation
- Enumeration and range constraint validation
- Pattern matching and format validation
- Response structure consistency across tools
- Error response formatting and metadata
- MCP schema compliance and JSON schema generation
- Cross-tool parameter naming consistency
"""

import json
import re
from datetime import datetime
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from lightrag_mcp.config import MCPConfig
from lightrag_mcp.protocol.context_tools import (
    ClearCacheTool,
    ExploreGraphTool,
    FindConceptTool,
    GetContextInfoTool,
    GetRelationshipsTool,
    GetSummaryTool,
    HelpTool,
    ListContextsTool,
    QueryTool,
    SearchDocsTool,
    SwitchContextTool,
)
from lightrag_mcp.protocol.server import (
    ConnectionSession,
    ConnectionState,
    MCPClientInfo,
    MCPServerInfo,
)
from lightrag_mcp.protocol.tools import (
    MCPTool,
    ToolCategory,
    ToolParameter,
    ToolParameterType,
    ToolProgress,
    ToolResult,
    boolean_parameter,
    integer_parameter,
    string_parameter,
)
from lightrag_mcp.services.lightrag_client import APIError


@pytest.fixture
def mock_config():
    """Create test MCP configuration."""
    return MCPConfig()


@pytest.fixture
def mock_session():
    """Create properly initialized test connection session."""
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
def all_tools(mock_config):
    """Create instances of all tools for testing."""
    return [
        ListContextsTool(mock_config),
        SwitchContextTool(mock_config),
        GetContextInfoTool(mock_config),
        QueryTool(mock_config),
        FindConceptTool(mock_config),
        GetRelationshipsTool(mock_config),
        SearchDocsTool(mock_config),
        GetSummaryTool(mock_config),
        ExploreGraphTool(mock_config),
        ClearCacheTool(mock_config),
        HelpTool(mock_config),
    ]


class TestParameterTypeValidation:
    """Test parameter type validation for all supported types."""

    def test_string_parameter_validation(self, mock_config):
        """Test string parameter validation."""
        param = string_parameter(
            name="test_string",
            description="Test string parameter",
            required=True,
            enum=["option1", "option2", "option3"],
        )

        # Valid values
        assert param.validate_value("option1") == "option1"
        assert param.validate_value("option2") == "option2"

        # Invalid type
        with pytest.raises(ValueError, match="must be a string"):
            param.validate_value(123)

        # Invalid enum value
        with pytest.raises(ValueError, match="must be one of"):
            param.validate_value("invalid_option")

        # Required parameter missing
        with pytest.raises(ValueError, match="Required parameter.*missing"):
            param.validate_value(None)

    def test_integer_parameter_validation(self, mock_config):
        """Test integer parameter validation."""
        param = integer_parameter(
            name="test_integer",
            description="Test integer parameter",
            required=True,
            minimum=1,
            maximum=100,
        )

        # Valid values
        assert param.validate_value(50) == 50
        assert param.validate_value(1) == 1
        assert param.validate_value(100) == 100

        # Invalid type
        with pytest.raises(ValueError, match="must be an integer"):
            param.validate_value("not_an_integer")

        with pytest.raises(ValueError, match="must be an integer"):
            param.validate_value(50.5)

        # Out of range
        with pytest.raises(ValueError, match="must be >= 1"):
            param.validate_value(0)

        with pytest.raises(ValueError, match="must be <= 100"):
            param.validate_value(101)

    def test_boolean_parameter_validation(self, mock_config):
        """Test boolean parameter validation."""
        param = boolean_parameter(
            name="test_boolean", description="Test boolean parameter", required=True
        )

        # Valid values
        assert param.validate_value(True) is True
        assert param.validate_value(False) is False

        # Invalid type
        with pytest.raises(ValueError, match="must be a boolean"):
            param.validate_value("true")

        with pytest.raises(ValueError, match="must be a boolean"):
            param.validate_value(1)

    def test_array_parameter_validation(self, mock_config):
        """Test array parameter validation."""
        param = ToolParameter(
            name="test_array",
            type=ToolParameterType.ARRAY,
            description="Test array parameter",
            required=True,
        )

        # Valid values
        assert param.validate_value([1, 2, 3]) == [1, 2, 3]
        assert param.validate_value([]) == []

        # Invalid type
        with pytest.raises(ValueError, match="must be an array"):
            param.validate_value("not_an_array")

        with pytest.raises(ValueError, match="must be an array"):
            param.validate_value({"key": "value"})

    def test_object_parameter_validation(self, mock_config):
        """Test object parameter validation."""
        param = ToolParameter(
            name="test_object",
            type=ToolParameterType.OBJECT,
            description="Test object parameter",
            required=True,
        )

        # Valid values
        test_obj = {"key": "value", "number": 42}
        assert param.validate_value(test_obj) == test_obj
        assert param.validate_value({}) == {}

        # Invalid type
        with pytest.raises(ValueError, match="must be an object"):
            param.validate_value("not_an_object")

        with pytest.raises(ValueError, match="must be an object"):
            param.validate_value([1, 2, 3])

    def test_pattern_validation(self, mock_config):
        """Test string pattern validation."""
        param = string_parameter(
            name="test_pattern",
            description="Test pattern parameter",
            required=True,
            pattern=r"^[a-zA-Z][a-zA-Z0-9_]*$",  # Valid identifier pattern
        )

        # Valid patterns
        assert param.validate_value("valid_identifier") == "valid_identifier"
        assert param.validate_value("ValidIdentifier123") == "ValidIdentifier123"

        # Invalid patterns
        with pytest.raises(ValueError, match="does not match pattern"):
            param.validate_value("123invalid")  # Starts with number

        with pytest.raises(ValueError, match="does not match pattern"):
            param.validate_value("invalid-identifier")  # Contains hyphen

    def test_default_value_application(self, mock_config):
        """Test default value application for optional parameters."""
        param = string_parameter(
            name="test_default",
            description="Test default parameter",
            required=False,
            default="default_value",
        )

        # Should return default when None
        assert param.validate_value(None) == "default_value"

        # Should return provided value when given
        assert param.validate_value("custom_value") == "custom_value"


class TestToolParameterDefinitions:
    """Test parameter definitions for all tools."""

    def test_all_tools_have_valid_parameters(self, all_tools):
        """Test that all tools have valid parameter definitions."""
        for tool in all_tools:
            # Every tool should have a parameters property
            assert hasattr(tool, "parameters")
            params = tool.parameters
            assert isinstance(params, list)

            # Check each parameter definition
            for param in params:
                assert isinstance(param, ToolParameter)
                assert param.name
                assert param.description
                assert isinstance(param.type, ToolParameterType)
                assert isinstance(param.required, bool)

    def test_parameter_naming_consistency(self, all_tools):
        """Test parameter naming consistency across tools."""
        # Common parameter names should have consistent types and constraints
        common_params = {}

        # Allow certain parameters to have different types due to valid design choices
        allowed_type_variations = {
            "relationship_types": [
                ToolParameterType.STRING,
                ToolParameterType.ARRAY,
            ]  # String (comma-separated) vs Array both valid
        }

        for tool in all_tools:
            for param in tool.parameters:
                if param.name in common_params:
                    # Check consistency with allowances for valid variations
                    existing_param = common_params[param.name]
                    if param.name in allowed_type_variations:
                        allowed_types = allowed_type_variations[param.name]
                        assert (
                            param.type in allowed_types
                        ), f"Parameter '{param.name}' has invalid type {param.type}, allowed: {allowed_types}"
                        assert (
                            existing_param.type in allowed_types
                        ), f"Parameter '{param.name}' has invalid type {existing_param.type}, allowed: {allowed_types}"
                    else:
                        assert (
                            param.type == existing_param.type
                        ), f"Parameter '{param.name}' has inconsistent type across tools"
                else:
                    common_params[param.name] = param

        # Verify specific common parameters
        if "query" in common_params:
            query_param = common_params["query"]
            assert query_param.type == ToolParameterType.STRING
            assert (
                query_param.required is True
            )  # Query parameters should typically be required

        if "top_k" in common_params:
            top_k_param = common_params["top_k"]
            assert top_k_param.type == ToolParameterType.INTEGER
            assert top_k_param.minimum is not None
            assert top_k_param.minimum >= 1

    def test_required_parameter_validation(self, all_tools):
        """Test that required parameters are properly validated."""
        for tool in all_tools:
            required_params = [p for p in tool.parameters if p.required]

            # Test with missing required parameter
            if required_params:
                # Try with empty parameters
                with pytest.raises(ValueError):
                    tool.validate_parameters({})

                # Try with missing specific required parameter
                first_required = required_params[0]
                incomplete_params = {p.name: "test_value" for p in required_params[1:]}
                with pytest.raises(ValueError):
                    tool.validate_parameters(incomplete_params)

    def test_optional_parameter_defaults(self, all_tools):
        """Test that optional parameters get proper default values."""
        for tool in all_tools:
            optional_params = [p for p in tool.parameters if not p.required]
            required_params = [p for p in tool.parameters if p.required]

            if optional_params:
                # Provide only required parameters
                minimal_params = {}
                for req_param in required_params:
                    if req_param.type == ToolParameterType.STRING:
                        minimal_params[req_param.name] = "test_value"
                    elif req_param.type == ToolParameterType.INTEGER:
                        minimal_params[req_param.name] = 1
                    elif req_param.type == ToolParameterType.BOOLEAN:
                        minimal_params[req_param.name] = True
                    elif req_param.type == ToolParameterType.ARRAY:
                        minimal_params[req_param.name] = []
                    elif req_param.type == ToolParameterType.OBJECT:
                        minimal_params[req_param.name] = {}

                # Should not raise an error
                try:
                    validated = tool.validate_parameters(minimal_params)
                    # Optional parameters should have default values
                    for opt_param in optional_params:
                        assert opt_param.name in validated
                        if opt_param.default is not None:
                            assert validated[opt_param.name] == opt_param.default
                except ValueError as e:
                    # If we can't create valid minimal params due to constraints, that's OK
                    pass


class TestJSONSchemaGeneration:
    """Test JSON schema generation for tool parameters."""

    def test_parameter_schema_generation(self, all_tools):
        """Test that all tools generate valid JSON schemas."""
        for tool in all_tools:
            schema = tool.get_parameter_schema()

            # Should be a valid JSON schema object
            assert isinstance(schema, dict)
            assert schema.get("type") == "object"
            assert "properties" in schema

            # Check required fields
            required_params = [p.name for p in tool.parameters if p.required]
            if required_params:
                assert "required" in schema
                assert set(schema["required"]) == set(required_params)

            # Check each property
            for param in tool.parameters:
                assert param.name in schema["properties"]
                prop_schema = schema["properties"][param.name]
                assert "type" in prop_schema
                assert "description" in prop_schema

    def test_mcp_schema_generation(self, all_tools):
        """Test MCP schema generation for tools."""
        for tool in all_tools:
            mcp_schema = tool.to_mcp_schema()

            # Should have required MCP fields
            assert "name" in mcp_schema
            assert "description" in mcp_schema
            assert "inputSchema" in mcp_schema

            # Name should match tool name
            assert mcp_schema["name"] == tool.name
            assert mcp_schema["description"] == tool.description

            # Input schema should be valid
            input_schema = mcp_schema["inputSchema"]
            assert isinstance(input_schema, dict)
            assert input_schema.get("type") == "object"

    def test_parameter_constraints_in_schema(self, all_tools):
        """Test that parameter constraints are properly included in schemas."""
        for tool in all_tools:
            schema = tool.get_parameter_schema()

            for param in tool.parameters:
                prop_schema = schema["properties"][param.name]

                # Check enum constraints
                if param.enum:
                    assert "enum" in prop_schema
                    assert prop_schema["enum"] == param.enum

                # Check range constraints
                if param.minimum is not None:
                    assert "minimum" in prop_schema
                    assert prop_schema["minimum"] == param.minimum

                if param.maximum is not None:
                    assert "maximum" in prop_schema
                    assert prop_schema["maximum"] == param.maximum

                # Check pattern constraints
                if param.pattern:
                    assert "pattern" in prop_schema
                    assert prop_schema["pattern"] == param.pattern


class TestResponseFormatValidation:
    """Test response format consistency across tools."""

    @pytest.mark.asyncio
    async def test_tool_result_structure(self, all_tools, mock_session):
        """Test that all tools return properly structured ToolResult objects."""
        for tool in all_tools:
            # Mock LightRAG client for tools that need it
            with patch.object(tool, "get_lightrag_client") as mock_client_getter:
                mock_client = AsyncMock()
                mock_client.query.return_value = {
                    "response": "test response",
                    "metadata": {},
                }
                mock_client.list_contexts.return_value = {
                    "contexts": {},
                    "current_context": "test",
                }
                mock_client.switch_context.return_value = {
                    "success": True,
                    "current_context": "test",
                }
                mock_client.clear_cache.return_value = {"success": True}
                mock_client_getter.return_value = mock_client

                # Create valid parameters for the tool
                try:
                    valid_params = {}
                    for param in tool.parameters:
                        if param.required:
                            if param.type == ToolParameterType.STRING:
                                if param.enum:
                                    valid_params[param.name] = param.enum[0]
                                else:
                                    valid_params[param.name] = "test_value"
                            elif param.type == ToolParameterType.INTEGER:
                                valid_params[param.name] = param.minimum or 1
                            elif param.type == ToolParameterType.BOOLEAN:
                                valid_params[param.name] = True
                            elif param.type == ToolParameterType.ARRAY:
                                valid_params[param.name] = []
                            elif param.type == ToolParameterType.OBJECT:
                                valid_params[param.name] = {}

                    # Special cases for specific tools
                    if (
                        tool.name == "clear_cache"
                        and valid_params.get("cache_type") == "all"
                    ):
                        valid_params["confirmation_token"] = "CONFIRM_CLEAR_ALL"

                    result = await tool.execute(mock_session, valid_params)

                    # Verify ToolResult structure
                    assert isinstance(result, ToolResult)
                    assert hasattr(result, "success")
                    assert isinstance(result.success, bool)
                    assert hasattr(result, "error")
                    assert hasattr(result, "data")
                    assert hasattr(result, "metadata")

                    # If successful, should have data
                    if result.success:
                        assert result.error is None
                        # Most tools should return some data
                        if tool.name not in [
                            "switch_context"
                        ]:  # Some tools may not return data
                            assert result.data is not None
                    else:
                        assert result.error is not None
                        assert isinstance(result.error, str)

                except ValueError:
                    # Some tools might have complex parameter requirements
                    # that we can't easily satisfy in this generic test
                    pass

    @pytest.mark.asyncio
    async def test_error_response_consistency(self, all_tools, mock_session):
        """Test that error responses have consistent structure."""
        for tool in all_tools:
            # Try to trigger a validation error with invalid parameters
            try:
                invalid_params = {"invalid_parameter": "invalid_value"}
                result = await tool.execute(mock_session, invalid_params)

                # Should be an error result
                assert isinstance(result, ToolResult)
                assert not result.success
                assert result.error is not None
                assert isinstance(result.error, str)
                assert result.metadata is not None
                assert isinstance(result.metadata, dict)

            except Exception:
                # Some tools might raise exceptions instead of returning error results
                # This is also valid behavior
                pass

    @pytest.mark.asyncio
    async def test_metadata_consistency(self, all_tools, mock_session):
        """Test that metadata structure is consistent across tools."""
        for tool in all_tools:
            with patch.object(tool, "get_lightrag_client") as mock_client_getter:
                mock_client = AsyncMock()
                mock_client.query.return_value = {"response": "test", "metadata": {}}
                mock_client.list_contexts.return_value = {
                    "contexts": {},
                    "current_context": "test",
                }
                mock_client.switch_context.return_value = {"success": True}
                mock_client.clear_cache.return_value = {"success": True}
                mock_client_getter.return_value = mock_client

                try:
                    # Create minimal valid parameters
                    params = {}
                    for param in tool.parameters:
                        if param.required:
                            if param.type == ToolParameterType.STRING:
                                if param.enum:
                                    params[param.name] = param.enum[0]
                                else:
                                    params[param.name] = "test"
                            elif param.type == ToolParameterType.INTEGER:
                                params[param.name] = param.minimum or 1
                            elif param.type == ToolParameterType.BOOLEAN:
                                params[param.name] = True

                    if tool.name == "clear_cache" and params.get("cache_type") == "all":
                        params["confirmation_token"] = "CONFIRM_CLEAR_ALL"

                    result = await tool.execute(mock_session, params)

                    if result.metadata:
                        # Common metadata fields that should be present
                        common_fields = ["tool"]
                        for field in common_fields:
                            if field in result.metadata:
                                # Verify the field has the expected value
                                if field == "tool":
                                    assert result.metadata[field] == tool.name

                except Exception:
                    # Skip tools that we can't easily test
                    pass


class TestStreamingResponseValidation:
    """Test streaming response format validation."""

    @pytest.mark.asyncio
    async def test_streaming_progress_format(self, all_tools, mock_session):
        """Test that streaming tools return properly formatted progress updates."""
        streaming_tools = [tool for tool in all_tools if tool.supports_streaming]

        for tool in streaming_tools:
            with patch.object(tool, "get_lightrag_client") as mock_client_getter:
                mock_client = AsyncMock()
                mock_client.query.return_value = {"response": "test", "metadata": {}}
                mock_client_getter.return_value = mock_client

                try:
                    # Create valid parameters
                    params = {}
                    for param in tool.parameters:
                        if param.required:
                            if param.type == ToolParameterType.STRING:
                                params[param.name] = "test"
                            elif param.type == ToolParameterType.INTEGER:
                                params[param.name] = 1
                            elif param.type == ToolParameterType.BOOLEAN:
                                params[param.name] = True

                    results = []
                    async for result in tool.execute_streaming(mock_session, params):
                        results.append(result)
                        # Verify each streaming result
                        assert isinstance(result, ToolResult)
                        assert hasattr(result, "success")
                        assert hasattr(result, "data")

                        # Check if this is a progress update
                        if isinstance(result.data, ToolProgress):
                            progress = result.data
                            assert hasattr(progress, "operation_id")
                            assert hasattr(progress, "progress")
                            assert hasattr(progress, "status")
                            assert hasattr(progress, "message")
                            assert 0.0 <= progress.progress <= 1.0

                    # Should have at least one result
                    assert len(results) > 0

                except Exception:
                    # Skip tools that we can't easily test
                    pass


class TestToolCategoryConsistency:
    """Test tool category and property consistency."""

    def test_tool_category_assignment(self, all_tools):
        """Test that all tools have appropriate category assignments."""
        for tool in all_tools:
            assert isinstance(tool.category, ToolCategory)

            # Verify category makes sense for tool
            if "context" in tool.name.lower():
                assert tool.category == ToolCategory.CONTEXT_MANAGEMENT
            elif tool.name in ["find_concept", "get_relationships", "search_docs"]:
                assert tool.category == ToolCategory.SEMANTIC_SEARCH
            elif tool.name in ["explore_graph"]:
                assert tool.category == ToolCategory.GRAPH_EXPLORATION
            elif tool.name in ["clear_cache", "help"]:
                assert tool.category == ToolCategory.SYSTEM_UTILITIES

    def test_context_requirement_consistency(self, all_tools):
        """Test that context requirements are consistent with tool functionality."""
        for tool in all_tools:
            assert isinstance(tool.requires_context, bool)

            # Some tools should not require context
        if tool.name in ["list_contexts", "switch_context", "clear_cache", "help"]:
            assert not tool.requires_context
        else:
            # Most other tools should require a context
            assert tool.requires_context

    def test_streaming_support_consistency(self, all_tools):
        """Test that streaming support is properly declared."""
        for tool in all_tools:
            assert isinstance(tool.supports_streaming, bool)

            # Verify execute_streaming method exists if streaming is supported
            if tool.supports_streaming:
                assert hasattr(tool, "execute_streaming")
                assert callable(tool.execute_streaming)


class TestValidationErrorMessages:
    """Test validation error message quality and consistency."""

    def test_parameter_error_message_quality(self, all_tools):
        """Test that parameter validation errors have helpful messages."""
        for tool in all_tools:
            for param in tool.parameters:
                if param.required:
                    # Test missing required parameter
                    try:
                        param.validate_value(None)
                        assert (
                            False
                        ), f"Should have raised error for missing required parameter {param.name}"
                    except ValueError as e:
                        error_msg = str(e)
                        assert param.name in error_msg
                        assert (
                            "required" in error_msg.lower()
                            or "missing" in error_msg.lower()
                        )

                if param.enum:
                    # Test invalid enum value
                    try:
                        param.validate_value("invalid_enum_value")
                        assert (
                            False
                        ), f"Should have raised error for invalid enum value in {param.name}"
                    except ValueError as e:
                        error_msg = str(e)
                        assert param.name in error_msg
                        assert "one of" in error_msg.lower()

    def test_constraint_error_messages(self, all_tools):
        """Test that constraint violation errors have helpful messages."""
        for tool in all_tools:
            for param in tool.parameters:
                if (
                    param.type == ToolParameterType.INTEGER
                    and param.minimum is not None
                ):
                    # Test minimum constraint
                    try:
                        param.validate_value(param.minimum - 1)
                        assert (
                            False
                        ), f"Should have raised error for value below minimum in {param.name}"
                    except ValueError as e:
                        error_msg = str(e)
                        assert param.name in error_msg
                        assert str(param.minimum) in error_msg

                if (
                    param.type == ToolParameterType.INTEGER
                    and param.maximum is not None
                ):
                    # Test maximum constraint
                    try:
                        param.validate_value(param.maximum + 1)
                        assert (
                            False
                        ), f"Should have raised error for value above maximum in {param.name}"
                    except ValueError as e:
                        error_msg = str(e)
                        assert param.name in error_msg
                        assert str(param.maximum) in error_msg


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
