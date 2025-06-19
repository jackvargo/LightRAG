"""
LightRAG MCP Tools Framework

This module provides the base framework for implementing MCP tools that interact
with LightRAG's knowledge graph system. It includes tool registration, parameter
validation, progress tracking, and comprehensive error handling.

Features:
- Base tool classes and interfaces
- Tool registration and discovery
- Parameter validation and schema definition
- Progress tracking and streaming support
- Integration with LightRAG API
- Comprehensive error handling
"""

import asyncio
import inspect
import json
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union, Callable, AsyncGenerator, Type
from dataclasses import dataclass, field
from pydantic import BaseModel, Field, validator

from ..config import MCPConfig
from ..services.lightrag_client import LightRAGClient, get_lightrag_client
from ..logging_utils import get_logger
from .server import ConnectionSession, JSONRPCError, JSONRPCErrorCode

logger = get_logger(__name__)


class ToolParameterType(str, Enum):
    """Supported parameter types for MCP tools"""
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"


class ToolCategory(str, Enum):
    """Categories of available tools"""
    CONTEXT_MANAGEMENT = "context_management"
    QUERY_OPERATIONS = "query_operations"
    SEMANTIC_SEARCH = "semantic_search"
    GRAPH_EXPLORATION = "graph_exploration"
    DOCUMENT_ACCESS = "document_access"
    SYSTEM_UTILITIES = "system_utilities"


@dataclass
class ToolParameter:
    """Tool parameter definition with validation rules"""
    name: str
    type: ToolParameterType
    description: str
    required: bool = True
    default: Optional[Any] = None
    enum: Optional[List[Any]] = None
    minimum: Optional[Union[int, float]] = None
    maximum: Optional[Union[int, float]] = None
    pattern: Optional[str] = None
    items: Optional["ToolParameter"] = None  # For array types
    properties: Optional[Dict[str, "ToolParameter"]] = None  # For object types

    def to_schema(self) -> Dict[str, Any]:
        """Convert parameter to JSON schema format"""
        schema = {
            "type": self.type.value,
            "description": self.description
        }
        
        if self.enum:
            schema["enum"] = self.enum
        if self.minimum is not None:
            schema["minimum"] = self.minimum
        if self.maximum is not None:
            schema["maximum"] = self.maximum
        if self.pattern:
            schema["pattern"] = self.pattern
        if not self.required and self.default is not None:
            schema["default"] = self.default
            
        if self.type == ToolParameterType.ARRAY and self.items:
            schema["items"] = self.items.to_schema()
        elif self.type == ToolParameterType.OBJECT and self.properties:
            schema["properties"] = {
                name: param.to_schema() 
                for name, param in self.properties.items()
            }
            schema["required"] = [
                name for name, param in self.properties.items() 
                if param.required
            ]
            
        return schema

    def validate_value(self, value: Any) -> Any:
        """Validate parameter value against schema"""
        if self.required and value is None:
            raise ValueError(f"Required parameter '{self.name}' is missing")
            
        if value is None:
            return self.default
            
        # Type validation
        if self.type == ToolParameterType.STRING and not isinstance(value, str):
            raise ValueError(f"Parameter '{self.name}' must be a string")
        elif self.type == ToolParameterType.INTEGER and not isinstance(value, int):
            raise ValueError(f"Parameter '{self.name}' must be an integer")
        elif self.type == ToolParameterType.NUMBER and not isinstance(value, (int, float)):
            raise ValueError(f"Parameter '{self.name}' must be a number")
        elif self.type == ToolParameterType.BOOLEAN and not isinstance(value, bool):
            raise ValueError(f"Parameter '{self.name}' must be a boolean")
        elif self.type == ToolParameterType.ARRAY and not isinstance(value, list):
            raise ValueError(f"Parameter '{self.name}' must be an array")
        elif self.type == ToolParameterType.OBJECT and not isinstance(value, dict):
            raise ValueError(f"Parameter '{self.name}' must be an object")
            
        # Value validation
        if self.enum and value not in self.enum:
            raise ValueError(f"Parameter '{self.name}' must be one of: {self.enum}")
        if self.minimum is not None and value < self.minimum:
            raise ValueError(f"Parameter '{self.name}' must be >= {self.minimum}")
        if self.maximum is not None and value > self.maximum:
            raise ValueError(f"Parameter '{self.name}' must be <= {self.maximum}")
        if self.pattern and isinstance(value, str):
            import re
            if not re.match(self.pattern, value):
                raise ValueError(f"Parameter '{self.name}' does not match pattern: {self.pattern}")
                
        return value


@dataclass
class ToolProgress:
    """Progress information for long-running tool operations"""
    operation_id: str
    progress: float  # 0.0 to 1.0
    status: str
    message: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    details: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert progress to dictionary format"""
        return {
            "operation_id": self.operation_id,
            "progress": self.progress,
            "status": self.status,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "details": self.details or {}
        }


@dataclass
class ToolResult:
    """Result from tool execution"""
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    progress: Optional[ToolProgress] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary format"""
        result = {
            "success": self.success,
            "data": self.data,
            "metadata": self.metadata or {}
        }
        
        if self.error:
            result["error"] = self.error
        if self.progress:
            result["progress"] = self.progress.to_dict()
            
        return result


class MCPTool(ABC):
    """
    Abstract base class for MCP tools
    
    All MCP tools must inherit from this class and implement the required methods.
    This provides a standardized interface for tool registration, validation, and execution.
    """

    def __init__(self, config: MCPConfig):
        self.config = config
        self.logger = logger.bind(component=f"mcp_tool_{self.name}")
        self._lightrag_client: Optional[LightRAGClient] = None

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name (must be unique)"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Tool description for discovery"""
        pass

    @property
    @abstractmethod
    def category(self) -> ToolCategory:
        """Tool category for organization"""
        pass

    @property
    @abstractmethod
    def parameters(self) -> List[ToolParameter]:
        """Tool parameters definition"""
        pass

    @property
    def supports_progress(self) -> bool:
        """Whether tool supports progress reporting"""
        return False

    @property
    def supports_streaming(self) -> bool:
        """Whether tool supports streaming results"""
        return False

    @property
    def requires_context(self) -> bool:
        """Whether tool requires a LightRAG context to be selected"""
        return True

    async def get_lightrag_client(self) -> LightRAGClient:
        """Get or create LightRAG client instance"""
        if self._lightrag_client is None:
            self._lightrag_client = get_lightrag_client(self.config)
        return self._lightrag_client

    def get_parameter_schema(self) -> Dict[str, Any]:
        """Get JSON schema for tool parameters"""
        if not self.parameters:
            return {"type": "object", "properties": {}}
            
        properties = {}
        required = []
        
        for param in self.parameters:
            properties[param.name] = param.to_schema()
            if param.required:
                required.append(param.name)
        
        schema = {
            "type": "object",
            "properties": properties
        }
        
        if required:
            schema["required"] = required
            
        return schema

    def validate_parameters(self, params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Validate and normalize tool parameters"""
        if not params:
            params = {}
            
        validated = {}
        
        for param in self.parameters:
            value = params.get(param.name)
            validated[param.name] = param.validate_value(value)
            
        return validated

    def validate_session(self, session: ConnectionSession) -> None:
        """Validate session requirements for tool execution"""
        if not session.is_initialized():
            raise ValueError("Session not properly initialized")
            
        if self.requires_context and not session.context:
            raise ValueError(f"Tool '{self.name}' requires a context to be selected")

    @abstractmethod
    async def execute(
        self, 
        session: ConnectionSession, 
        parameters: Dict[str, Any]
    ) -> ToolResult:
        """
        Execute the tool with validated parameters
        
        Args:
            session: Current MCP session
            parameters: Validated tool parameters
            
        Returns:
            ToolResult with execution results
        """
        pass

    async def execute_streaming(
        self, 
        session: ConnectionSession, 
        parameters: Dict[str, Any]
    ) -> AsyncGenerator[ToolResult, None]:
        """
        Execute tool with streaming results (optional)
        
        Args:
            session: Current MCP session
            parameters: Validated tool parameters
            
        Yields:
            ToolResult instances with partial results
        """
        # Default implementation - just yield final result
        result = await self.execute(session, parameters)
        yield result

    def to_mcp_schema(self) -> Dict[str, Any]:
        """Convert tool to MCP tool schema format"""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.get_parameter_schema(),
            "metadata": {
                "category": self.category.value,
                "supports_progress": self.supports_progress,
                "supports_streaming": self.supports_streaming,
                "requires_context": self.requires_context
            }
        }


class ToolRegistry:
    """
    Registry for managing MCP tools
    
    Handles tool registration, discovery, and execution routing.
    """

    def __init__(self, config: MCPConfig):
        self.config = config
        self.logger = logger.bind(component="tool_registry")
        self._tools: Dict[str, MCPTool] = {}
        self._tools_by_category: Dict[ToolCategory, List[MCPTool]] = {}

    def register_tool(self, tool: MCPTool) -> None:
        """Register a new tool"""
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")
            
        self._tools[tool.name] = tool
        
        # Add to category index
        if tool.category not in self._tools_by_category:
            self._tools_by_category[tool.category] = []
        self._tools_by_category[tool.category].append(tool)
        
        self.logger.info(f"Registered tool: {tool.name} (category: {tool.category.value})")

    def unregister_tool(self, tool_name: str) -> None:
        """Unregister a tool"""
        if tool_name not in self._tools:
            raise ValueError(f"Tool '{tool_name}' is not registered")
            
        tool = self._tools[tool_name]
        del self._tools[tool_name]
        
        # Remove from category index
        if tool.category in self._tools_by_category:
            self._tools_by_category[tool.category] = [
                t for t in self._tools_by_category[tool.category] 
                if t.name != tool_name
            ]
            
        self.logger.info(f"Unregistered tool: {tool_name}")

    def get_tool(self, tool_name: str) -> Optional[MCPTool]:
        """Get tool by name"""
        return self._tools.get(tool_name)

    def list_tools(self, category: Optional[ToolCategory] = None) -> List[MCPTool]:
        """List all tools or tools by category"""
        if category:
            return self._tools_by_category.get(category, [])
        return list(self._tools.values())

    def get_tools_schema(self) -> List[Dict[str, Any]]:
        """Get MCP schema for all registered tools"""
        return [tool.to_mcp_schema() for tool in self._tools.values()]

    async def execute_tool(
        self, 
        tool_name: str, 
        session: ConnectionSession, 
        parameters: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        """Execute a tool by name"""
        tool = self.get_tool(tool_name)
        if not tool:
            return ToolResult(
                success=False,
                error=f"Tool '{tool_name}' not found"
            )
            
        try:
            # Validate session requirements
            tool.validate_session(session)
            
            # Validate and normalize parameters
            validated_params = tool.validate_parameters(parameters)
            
            # Execute tool
            result = await tool.execute(session, validated_params)
            
            self.logger.info(
                f"Tool executed successfully",
                tool_name=tool_name,
                session_id=session.session_id,
                success=result.success
            )
            
            return result
            
        except Exception as e:
            self.logger.error(
                f"Tool execution failed",
                tool_name=tool_name,
                session_id=session.session_id,
                error=str(e),
                exc_info=True
            )
            
            return ToolResult(
                success=False,
                error=str(e),
                metadata={"tool_name": tool_name, "error_type": type(e).__name__}
            )

    async def execute_tool_streaming(
        self, 
        tool_name: str, 
        session: ConnectionSession, 
        parameters: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[ToolResult, None]:
        """Execute a tool with streaming results"""
        tool = self.get_tool(tool_name)
        if not tool:
            yield ToolResult(
                success=False,
                error=f"Tool '{tool_name}' not found"
            )
            return
            
        try:
            # Validate session requirements
            tool.validate_session(session)
            
            # Validate and normalize parameters
            validated_params = tool.validate_parameters(parameters)
            
            # Execute tool with streaming
            async for result in tool.execute_streaming(session, validated_params):
                yield result
                
        except Exception as e:
            self.logger.error(
                f"Streaming tool execution failed",
                tool_name=tool_name,
                session_id=session.session_id,
                error=str(e),
                exc_info=True
            )
            
            yield ToolResult(
                success=False,
                error=str(e),
                metadata={"tool_name": tool_name, "error_type": type(e).__name__}
            )


class ToolManager:
    """
    High-level tool management interface
    
    Provides the main interface for MCP protocol server to interact with tools.
    """

    def __init__(self, config: MCPConfig):
        self.config = config
        self.logger = logger.bind(component="tool_manager")
        self.registry = ToolRegistry(config)
        self._active_operations: Dict[str, asyncio.Task] = {}

    async def initialize(self) -> None:
        """Initialize tool manager and register built-in tools"""
        self.logger.info("Initializing tool manager")
        
        # Tool registration will be handled in Phase 5
        # For now, we just log that the framework is ready
        self.logger.info(
            "Tool framework initialized",
            tools_count=len(self.registry.list_tools())
        )

    async def shutdown(self) -> None:
        """Shutdown tool manager and cancel active operations"""
        self.logger.info("Shutting down tool manager")
        
        # Cancel all active operations
        for operation_id, task in self._active_operations.items():
            if not task.done():
                task.cancel()
                self.logger.debug(f"Cancelled operation: {operation_id}")
                
        self._active_operations.clear()
        self.logger.info("Tool manager shutdown complete")

    def register_tool(self, tool: MCPTool) -> None:
        """Register a tool with the manager"""
        self.registry.register_tool(tool)

    def get_tools_list(self) -> List[Dict[str, Any]]:
        """Get list of available tools for MCP tools/list"""
        return self.registry.get_tools_schema()

    async def call_tool(
        self, 
        tool_name: str, 
        session: ConnectionSession, 
        arguments: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Call a tool for MCP tools/call
        
        Returns standardized MCP tool call response
        """
        try:
            result = await self.registry.execute_tool(tool_name, session, arguments)
            
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result.to_dict(), indent=2)
                    }
                ],
                "isError": not result.success
            }
            
        except Exception as e:
            self.logger.error(
                f"Tool call failed",
                tool_name=tool_name,
                session_id=session.session_id,
                error=str(e),
                exc_info=True
            )
            
            return {
                "content": [
                    {
                        "type": "text", 
                        "text": f"Tool execution failed: {str(e)}"
                    }
                ],
                "isError": True
            }

    async def call_tool_streaming(
        self, 
        tool_name: str, 
        session: ConnectionSession, 
        arguments: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Call a tool with streaming results"""
        try:
            async for result in self.registry.execute_tool_streaming(tool_name, session, arguments):
                yield {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result.to_dict(), indent=2)
                        }
                    ],
                    "isError": not result.success
                }
                
        except Exception as e:
            self.logger.error(
                f"Streaming tool call failed",
                tool_name=tool_name,
                session_id=session.session_id,
                error=str(e),
                exc_info=True
            )
            
            yield {
                "content": [
                    {
                        "type": "text",
                        "text": f"Streaming tool execution failed: {str(e)}"
                    }
                ],
                "isError": True
            }

    def cancel_operation(self, operation_id: str) -> bool:
        """Cancel an active operation"""
        if operation_id in self._active_operations:
            task = self._active_operations[operation_id]
            if not task.done():
                task.cancel()
                del self._active_operations[operation_id]
                self.logger.info(f"Cancelled operation: {operation_id}")
                return True
        return False

    def get_operation_status(self, operation_id: str) -> Optional[str]:
        """Get status of an active operation"""
        if operation_id in self._active_operations:
            task = self._active_operations[operation_id]
            if task.done():
                del self._active_operations[operation_id]
                return "completed"
            return "running"
        return None


# Helper functions for creating common parameter types

def string_parameter(
    name: str, 
    description: str, 
    required: bool = True, 
    default: Optional[str] = None,
    enum: Optional[List[str]] = None,
    pattern: Optional[str] = None
) -> ToolParameter:
    """Create a string parameter"""
    return ToolParameter(
        name=name,
        type=ToolParameterType.STRING,
        description=description,
        required=required,
        default=default,
        enum=enum,
        pattern=pattern
    )


def integer_parameter(
    name: str,
    description: str,
    required: bool = True,
    default: Optional[int] = None,
    minimum: Optional[int] = None,
    maximum: Optional[int] = None
) -> ToolParameter:
    """Create an integer parameter"""
    return ToolParameter(
        name=name,
        type=ToolParameterType.INTEGER,
        description=description,
        required=required,
        default=default,
        minimum=minimum,
        maximum=maximum
    )


def boolean_parameter(
    name: str,
    description: str,
    required: bool = True,
    default: Optional[bool] = None
) -> ToolParameter:
    """Create a boolean parameter"""
    return ToolParameter(
        name=name,
        type=ToolParameterType.BOOLEAN,
        description=description,
        required=required,
        default=default
    )


def array_parameter(
    name: str,
    description: str,
    items: ToolParameter,
    required: bool = True,
    default: Optional[List[Any]] = None
) -> ToolParameter:
    """Create an array parameter"""
    return ToolParameter(
        name=name,
        type=ToolParameterType.ARRAY,
        description=description,
        required=required,
        default=default,
        items=items
    ) 