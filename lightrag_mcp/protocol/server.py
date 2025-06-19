"""
LightRAG MCP JSON-RPC Protocol Server Implementation

This module implements the core MCP (Model Context Protocol) JSON-RPC server
that handles communication between MCP clients and the LightRAG knowledge graph system.

Features:
- Full JSON-RPC 2.0 protocol implementation
- MCP capability negotiation and initialization
- Request/response handling with streaming support
- Comprehensive error handling and validation
- Session management and connection lifecycle
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Union, Callable
from enum import Enum
from dataclasses import dataclass, asdict

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, validator
import structlog

from ..config import MCPConfig
from ..auth import verify_token
from ..logging_utils import get_logger

# Configure structured logging
logger = get_logger(__name__)


class JSONRPCVersion(str, Enum):
    """JSON-RPC version specification"""
    V2_0 = "2.0"


class MCPCapability(str, Enum):
    """MCP server capabilities"""
    TOOLS = "tools"
    RESOURCES = "resources"
    PROMPTS = "prompts"
    LOGGING = "logging"
    EXPERIMENTAL_SAMPLING = "experimental/sampling"


class MCPProtocolVersion(str, Enum):
    """MCP protocol version"""
    V2024_11_05 = "2024-11-05"


class JSONRPCErrorCode(int, Enum):
    """Standard JSON-RPC error codes with detailed categorization"""
    # Standard JSON-RPC 2.0 errors
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    
    # MCP-specific error codes (following MCP specification)
    INITIALIZATION_ERROR = -32000
    CAPABILITY_NOT_SUPPORTED = -32001
    AUTHENTICATION_ERROR = -32002
    AUTHORIZATION_ERROR = -32003
    CONTEXT_ERROR = -32004
    RATE_LIMIT_ERROR = -32005
    
    # LightRAG-specific error codes
    LIGHTRAG_API_ERROR = -32100
    LIGHTRAG_CONNECTION_ERROR = -32101
    CONTEXT_SWITCH_ERROR = -32102
    DOCUMENT_NOT_FOUND = -32103
    QUERY_EXECUTION_ERROR = -32104
    KNOWLEDGE_GRAPH_ERROR = -32105
    CACHE_ERROR = -32106
    VALIDATION_ERROR = -32107
    RESOURCE_EXHAUSTED = -32108
    TIMEOUT_ERROR = -32109
    CONFIGURATION_ERROR = -32110


@dataclass
class JSONRPCError:
    """Enhanced JSON-RPC error representation with detailed context"""
    code: int
    message: str
    data: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {"code": self.code, "message": self.message}
        if self.data:
            result["data"] = self.data
        return result

    @classmethod
    def create_detailed_error(
        cls,
        code: JSONRPCErrorCode,
        message: str,
        details: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        suggestions: Optional[List[str]] = None,
        error_id: Optional[str] = None
    ) -> "JSONRPCError":
        """
        Create a detailed error with comprehensive debugging information
        
        Args:
            code: Error code from JSONRPCErrorCode enum
            message: Human-readable error message
            details: Detailed technical information
            context: Additional context about the error
            suggestions: List of suggested solutions
            error_id: Unique error identifier for tracking
            
        Returns:
            JSONRPCError instance with detailed information
        """
        data = {}
        
        if details:
            data["details"] = details
            
        if context:
            data["context"] = context
            
        if suggestions:
            data["suggestions"] = suggestions
            
        if error_id:
            data["error_id"] = error_id
            
        # Add error category based on code
        data["category"] = cls._get_error_category(code)
        
        # Add timestamp for debugging
        data["timestamp"] = datetime.utcnow().isoformat()
        
        return cls(
            code=code.value,
            message=message,
            data=data if data else None
        )

    @staticmethod
    def _get_error_category(code: JSONRPCErrorCode) -> str:
        """Get error category for better error handling"""
        if code.value >= -32700 and code.value <= -32600:
            return "protocol"
        elif code.value >= -32099 and code.value <= -32000:
            return "mcp"
        elif code.value >= -32199 and code.value <= -32100:
            return "lightrag"
        else:
            return "unknown"


class JSONRPCRequest(BaseModel):
    """JSON-RPC request model"""
    jsonrpc: JSONRPCVersion = JSONRPCVersion.V2_0
    method: str
    params: Optional[Union[Dict[str, Any], List[Any]]] = None
    id: Optional[Union[str, int]] = None

    @validator('method')
    def validate_method(cls, v):
        if not v or not isinstance(v, str):
            raise ValueError("Method must be a non-empty string")
        return v


class JSONRPCResponse(BaseModel):
    """JSON-RPC response model"""
    jsonrpc: JSONRPCVersion = JSONRPCVersion.V2_0
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None
    id: Optional[Union[str, int]] = None

    @validator('result', 'error')
    def validate_result_or_error(cls, v, values):
        # Exactly one of result or error must be present
        if 'result' in values and 'error' in values:
            if (values.get('result') is None) == (values.get('error') is None):
                raise ValueError("Exactly one of 'result' or 'error' must be present")
        return v


class MCPServerInfo(BaseModel):
    """MCP server information"""
    name: str = "lightrag-mcp-server"
    version: str = "0.1.0"
    protocol_version: MCPProtocolVersion = MCPProtocolVersion.V2024_11_05
    capabilities: Dict[str, Any] = Field(default_factory=dict)


class MCPClientInfo(BaseModel):
    """MCP client information received during initialization"""
    name: str
    version: str
    protocol_version: str
    capabilities: Optional[Dict[str, Any]] = None


@dataclass
class ConnectionSession:
    """Represents an active MCP connection session"""
    session_id: str
    client_info: Optional[MCPClientInfo] = None
    server_info: Optional[MCPServerInfo] = None
    capabilities: Dict[str, bool] = None
    context: Optional[str] = None
    authenticated: bool = False
    user_id: Optional[str] = None
    connected_at: datetime = None
    last_activity: datetime = None

    def __post_init__(self):
        if self.connected_at is None:
            self.connected_at = datetime.utcnow()
        if self.last_activity is None:
            self.last_activity = datetime.utcnow()
        if self.capabilities is None:
            self.capabilities = {}

    def update_activity(self):
        """Update last activity timestamp"""
        self.last_activity = datetime.utcnow()

    def is_initialized(self) -> bool:
        """Check if session is properly initialized"""
        return (
            self.client_info is not None
            and self.server_info is not None
            and self.authenticated
        )


class MCPErrorHandler:
    """
    Comprehensive error handling manager for MCP protocol operations
    
    Provides detailed error messages, context information, and recovery suggestions
    for all types of MCP protocol and LightRAG-specific errors.
    """
    
    def __init__(self, logger):
        self.logger = logger
        self.error_count = 0
        self.error_history = []

    def handle_initialization_error(
        self, 
        session_id: str, 
        error: Exception, 
        context: Optional[Dict[str, Any]] = None
    ) -> JSONRPCError:
        """Handle initialization-related errors with detailed context"""
        self.error_count += 1
        
        if "protocolVersion" in str(error):
            return JSONRPCError.create_detailed_error(
                JSONRPCErrorCode.INITIALIZATION_ERROR,
                "Protocol version validation failed",
                details=str(error),
                context={
                    "session_id": session_id,
                    "error_type": "protocol_version_mismatch",
                    **(context or {})
                },
                suggestions=[
                    "Check that your client supports MCP protocol version 2024-11-05",
                    "Update your MCP client to the latest version",
                    "Verify the protocolVersion field in your initialize request"
                ],
                error_id=f"init_{session_id}_{self.error_count}"
            )
        elif "clientInfo" in str(error):
            return JSONRPCError.create_detailed_error(
                JSONRPCErrorCode.INITIALIZATION_ERROR,
                "Client information validation failed",
                details=str(error),
                context={
                    "session_id": session_id,
                    "error_type": "client_info_invalid",
                    **(context or {})
                },
                suggestions=[
                    "Ensure clientInfo object is provided with name and version fields",
                    "Check that clientInfo is a valid JSON object",
                    "Verify all required clientInfo fields are present"
                ],
                error_id=f"init_{session_id}_{self.error_count}"
            )
        else:
            return JSONRPCError.create_detailed_error(
                JSONRPCErrorCode.INITIALIZATION_ERROR,
                "Session initialization failed",
                details=str(error),
                context={
                    "session_id": session_id,
                    "error_type": "initialization_failure",
                    **(context or {})
                },
                suggestions=[
                    "Verify all required parameters are provided",
                    "Check your authentication credentials",
                    "Try reinitializing the connection"
                ],
                error_id=f"init_{session_id}_{self.error_count}"
            )

    def handle_capability_error(
        self, 
        session_id: str, 
        method: str, 
        missing_capability: str,
        context: Optional[Dict[str, Any]] = None
    ) -> JSONRPCError:
        """Handle capability-related errors"""
        self.error_count += 1
        
        capability_suggestions = {
            "tools": [
                "Ensure your client requests 'tools' capability during initialization",
                "Check that tools capability was successfully negotiated",
                "Use the discovery endpoint to see available capabilities"
            ],
            "resources": [
                "Ensure your client requests 'resources' capability during initialization", 
                "Check that resources capability was successfully negotiated",
                "Verify you have permission to access document resources"
            ],
            "prompts": [
                "Ensure your client requests 'prompts' capability during initialization",
                "Check that prompts capability was successfully negotiated",
                "Verify prompt templates are available in your context"
            ]
        }
        
        return JSONRPCError.create_detailed_error(
            JSONRPCErrorCode.CAPABILITY_NOT_SUPPORTED,
            f"Method '{method}' requires '{missing_capability}' capability",
            details=f"The method '{method}' cannot be executed because the '{missing_capability}' capability was not negotiated for this session",
            context={
                "session_id": session_id,
                "method": method,
                "missing_capability": missing_capability,
                "error_type": "capability_not_negotiated",
                **(context or {})
            },
            suggestions=capability_suggestions.get(missing_capability, [
                f"Ensure your client requests '{missing_capability}' capability during initialization",
                "Check the server's capability negotiation response",
                "Verify your client supports the required capability"
            ]),
            error_id=f"cap_{session_id}_{self.error_count}"
        )

    def handle_validation_error(
        self, 
        session_id: str, 
        method: str, 
        validation_error: Exception,
        context: Optional[Dict[str, Any]] = None
    ) -> JSONRPCError:
        """Handle parameter validation errors"""
        self.error_count += 1
        
        return JSONRPCError.create_detailed_error(
            JSONRPCErrorCode.VALIDATION_ERROR,
            f"Parameter validation failed for method '{method}'",
            details=str(validation_error),
            context={
                "session_id": session_id,
                "method": method,
                "error_type": "parameter_validation",
                **(context or {})
            },
            suggestions=[
                "Check that all required parameters are provided",
                "Verify parameter types match the expected schema",
                "Review the method documentation for parameter requirements",
                "Use the discovery endpoint to see method specifications"
            ],
            error_id=f"val_{session_id}_{self.error_count}"
        )

    def handle_lightrag_api_error(
        self, 
        session_id: str, 
        method: str, 
        api_error: Exception,
        context: Optional[Dict[str, Any]] = None
    ) -> JSONRPCError:
        """Handle LightRAG API communication errors"""
        self.error_count += 1
        
        if "connection" in str(api_error).lower():
            return JSONRPCError.create_detailed_error(
                JSONRPCErrorCode.LIGHTRAG_CONNECTION_ERROR,
                "Failed to connect to LightRAG API",
                details=str(api_error),
                context={
                    "session_id": session_id,
                    "method": method,
                    "error_type": "lightrag_connection_failure",
                    **(context or {})
                },
                suggestions=[
                    "Check that the LightRAG API server is running",
                    "Verify network connectivity to the LightRAG service",
                    "Check LightRAG API endpoint configuration",
                    "Try again after a brief delay"
                ],
                error_id=f"api_{session_id}_{self.error_count}"
            )
        elif "timeout" in str(api_error).lower():
            return JSONRPCError.create_detailed_error(
                JSONRPCErrorCode.TIMEOUT_ERROR,
                "LightRAG API request timed out",
                details=str(api_error),
                context={
                    "session_id": session_id,
                    "method": method,
                    "error_type": "lightrag_timeout",
                    **(context or {})
                },
                suggestions=[
                    "Try a simpler query to reduce processing time",
                    "Check if the LightRAG service is overloaded",
                    "Consider breaking complex operations into smaller parts",
                    "Retry the operation after a brief delay"
                ],
                error_id=f"timeout_{session_id}_{self.error_count}"
            )
        else:
            return JSONRPCError.create_detailed_error(
                JSONRPCErrorCode.LIGHTRAG_API_ERROR,
                f"LightRAG API error in method '{method}'",
                details=str(api_error),
                context={
                    "session_id": session_id,
                    "method": method,
                    "error_type": "lightrag_api_error",
                    **(context or {})
                },
                suggestions=[
                    "Check the LightRAG API server logs for more details",
                    "Verify that the requested context exists",
                    "Ensure proper authentication with LightRAG API",
                    "Try the operation again with valid parameters"
                ],
                error_id=f"api_{session_id}_{self.error_count}"
            )

    def handle_internal_error(
        self, 
        session_id: str, 
        method: str, 
        internal_error: Exception,
        context: Optional[Dict[str, Any]] = None
    ) -> JSONRPCError:
        """Handle unexpected internal server errors"""
        self.error_count += 1
        
        # Log internal errors for debugging
        self.logger.error(
            "Internal server error occurred",
            session_id=session_id,
            method=method,
            error=str(internal_error),
            exc_info=True
        )
        
        return JSONRPCError.create_detailed_error(
            JSONRPCErrorCode.INTERNAL_ERROR,
            "An unexpected internal server error occurred",
            details="The server encountered an unexpected error while processing your request",
            context={
                "session_id": session_id,
                "method": method,
                "error_type": "internal_server_error",
                **(context or {})
            },
            suggestions=[
                "Try the operation again after a brief delay",
                "Check if the issue persists with a simpler request",
                "Contact system administrator if the problem continues",
                "Check server logs for detailed error information"
            ],
            error_id=f"internal_{session_id}_{self.error_count}"
        )

    def handle_parse_error(
        self, 
        session_id: str, 
        parse_error: Exception,
        raw_message: Optional[str] = None
    ) -> JSONRPCError:
        """Handle JSON parsing errors"""
        self.error_count += 1
        
        return JSONRPCError.create_detailed_error(
            JSONRPCErrorCode.PARSE_ERROR,
            "Failed to parse JSON-RPC request",
            details=str(parse_error),
            context={
                "session_id": session_id,
                "error_type": "json_parse_error",
                "raw_message_length": len(raw_message) if raw_message else 0
            },
            suggestions=[
                "Verify that your request is valid JSON",
                "Check for missing quotes, brackets, or commas",
                "Ensure special characters are properly escaped",
                "Use a JSON validator to check your request format"
            ],
            error_id=f"parse_{session_id}_{self.error_count}"
        )

    def log_error_metrics(self):
        """Log error metrics for monitoring"""
        self.logger.info(
            "Error handler metrics",
            total_errors=self.error_count,
            recent_errors=len([e for e in self.error_history if 
                             (datetime.utcnow() - e.get('timestamp', datetime.min)).seconds < 300])
        )


class MCPProtocolServer:
    """
    Core MCP JSON-RPC protocol server implementation
    
    Handles the complete MCP protocol lifecycle including:
    - Connection establishment and session management
    - JSON-RPC message parsing and validation
    - Capability negotiation and initialization
    - Request routing and response handling
    - Error handling and logging
    """

    def __init__(self, config: MCPConfig):
        self.config = config
        self.logger = logger.bind(component="mcp_protocol_server")
        
        # Enhanced error handling
        self.error_handler = MCPErrorHandler(self.logger)
        
        # Active sessions storage
        self.sessions: Dict[str, ConnectionSession] = {}
        
        # Method handlers registry
        self.handlers: Dict[str, Callable] = {}
        
        # Server capabilities
        self.server_capabilities = {
            MCPCapability.TOOLS: {
                "listChanged": True,
                "supports_progress": True
            },
            MCPCapability.RESOURCES: {
                "subscribe": True,
                "listChanged": True
            },
            MCPCapability.PROMPTS: {
                "listChanged": True
            },
            MCPCapability.LOGGING: {
                "level": "info"
            }
        }
        
        # Register core protocol handlers
        self._register_core_handlers()

    def _register_core_handlers(self):
        """Register core MCP protocol method handlers"""
        self.handlers.update({
            "initialize": self._handle_initialize,
            "initialized": self._handle_initialized,
            "ping": self._handle_ping,
            "notifications/cancelled": self._handle_notification_cancelled,
            "notifications/progress": self._handle_notification_progress,
            "logging/setLevel": self._handle_logging_set_level,
        })

    def register_handler(self, method: str, handler: Callable):
        """Register a custom method handler"""
        self.handlers[method] = handler
        self.logger.debug("Registered handler", method=method)

    async def handle_websocket(self, websocket: WebSocket, path: str):
        """
        Handle WebSocket connection for MCP protocol
        
        Args:
            websocket: FastAPI WebSocket connection
            path: Connection path (may contain authentication info)
        """
        session_id = str(uuid.uuid4())
        session = ConnectionSession(session_id=session_id)
        self.sessions[session_id] = session
        
        self.logger.info(
            "New MCP connection established",
            session_id=session_id,
            client_ip=websocket.client.host if websocket.client else "unknown"
        )

        try:
            await websocket.accept()
            
            async for message in websocket.iter_text():
                try:
                    session.update_activity()
                    response = await self._process_message(session, message)
                    
                    if response:
                        await websocket.send_text(response)
                        
                except Exception as e:
                    self.logger.error(
                        "Error processing message",
                        session_id=session_id,
                        error=str(e),
                        exc_info=True
                    )
                    
                    # Send enhanced error response
                    error_obj = self.error_handler.handle_internal_error(
                        session_id, "websocket_processing", e
                    )
                    error_response = JSONRPCResponse(
                        id=None, error=error_obj.to_dict()
                    ).json()
                    await websocket.send_text(error_response)

        except WebSocketDisconnect:
            self.logger.info("MCP client disconnected", session_id=session_id)
        except Exception as e:
            self.logger.error(
                "WebSocket error",
                session_id=session_id,
                error=str(e),
                exc_info=True
            )
        finally:
            # Cleanup session
            if session_id in self.sessions:
                del self.sessions[session_id]
            self.logger.debug("Session cleaned up", session_id=session_id)

    async def _process_message(self, session: ConnectionSession, message: str) -> Optional[str]:
        """
        Process incoming JSON-RPC message
        
        Args:
            session: Connection session
            message: Raw JSON-RPC message
            
        Returns:
            JSON-RPC response string if response is needed
        """
        try:
            # Parse JSON-RPC request
            data = json.loads(message)
            request = JSONRPCRequest(**data)
            
            self.logger.debug(
                "Processing MCP request",
                session_id=session.session_id,
                method=request.method,
                has_id=request.id is not None
            )
            
            # Check if session is initialized for non-initialization methods
            if (
                request.method not in ["initialize", "initialized", "ping"]
                and not session.is_initialized()
            ):
                error_obj = self.error_handler.handle_initialization_error(
                    session.session_id, 
                    ValueError("Session not initialized. Call 'initialize' first."),
                    {"method": request.method, "has_client_info": session.client_info is not None}
                )
                return JSONRPCResponse(id=request.id, error=error_obj.to_dict()).json()
            
            # Route to appropriate handler
            if request.method in self.handlers:
                try:
                    # Validate capability requirements for specific method types
                    if not self._validate_method_capability(session, request.method):
                        missing_capability = self._get_required_capability(request.method)
                        error_obj = self.error_handler.handle_capability_error(
                            session.session_id, request.method, missing_capability,
                            {"negotiated_capabilities": list(session.capabilities.keys()) if session.capabilities else []}
                        )
                        return JSONRPCResponse(id=request.id, error=error_obj.to_dict()).json()
                    
                    result = await self.handlers[request.method](session, request.params)
                    
                    # Only send response for requests with ID (not notifications)
                    if request.id is not None:
                        return self._create_success_response(request.id, result)
                        
                except ValueError as e:
                    # Handle validation errors with detailed context
                    if request.id is not None:
                        error_obj = self.error_handler.handle_validation_error(
                            session.session_id, request.method, e,
                            {"params": request.params}
                        )
                        return JSONRPCResponse(id=request.id, error=error_obj.to_dict()).json()
                        
                except Exception as e:
                    # Handle all other errors as internal errors
                    if request.id is not None:
                        error_obj = self.error_handler.handle_internal_error(
                            session.session_id, request.method, e,
                            {"params": request.params}
                        )
                        return JSONRPCResponse(id=request.id, error=error_obj.to_dict()).json()
            else:
                if request.id is not None:
                    return self._create_error_response(
                        request.id,
                        JSONRPCErrorCode.METHOD_NOT_FOUND,
                        f"Method '{request.method}' not found"
                    )
                    
        except json.JSONDecodeError as e:
            error_obj = self.error_handler.handle_parse_error(
                session.session_id, e, message
            )
            return JSONRPCResponse(id=None, error=error_obj.to_dict()).json()
            
        except ValueError as e:
            # Handle JSON-RPC request validation errors
            error_obj = JSONRPCError.create_detailed_error(
                JSONRPCErrorCode.INVALID_REQUEST,
                "Invalid JSON-RPC request format",
                details=str(e),
                context={
                    "session_id": session.session_id,
                    "error_type": "request_validation"
                },
                suggestions=[
                    "Ensure your request follows JSON-RPC 2.0 specification",
                    "Check that required fields (jsonrpc, method) are present",
                    "Verify that the 'method' field is a non-empty string",
                    "For requests expecting a response, include an 'id' field"
                ]
            )
            return JSONRPCResponse(id=None, error=error_obj.to_dict()).json()
            
        return None

    def _create_success_response(self, request_id: Union[str, int], result: Any) -> str:
        """Create JSON-RPC success response"""
        response = JSONRPCResponse(
            id=request_id,
            result=result
        )
        return response.json()

    def _create_error_response(
        self,
        request_id: Optional[Union[str, int]],
        error_code: JSONRPCErrorCode,
        error_message: str,
        error_data: Optional[Dict[str, Any]] = None
    ) -> str:
        """Create JSON-RPC error response"""
        error = JSONRPCError(
            code=error_code.value,
            message=error_message,
            data=error_data
        )
        response = JSONRPCResponse(
            id=request_id,
            error=error.to_dict()
        )
        return response.json()

    # Core Protocol Handlers

    async def _handle_initialize(self, session: ConnectionSession, params: Any) -> Dict[str, Any]:
        """
        Handle MCP initialize request with comprehensive capability negotiation
        
        This is the first method called to establish the MCP session.
        Performs protocol version validation, capability matching, and session setup.
        """
        if not params or not isinstance(params, dict):
            raise ValueError("Initialize requires client info parameters")
            
        # Validate required parameters
        if "protocolVersion" not in params:
            raise ValueError("protocolVersion is required for initialization")
            
        if "clientInfo" not in params:
            raise ValueError("clientInfo is required for initialization")
            
        client_info_data = params["clientInfo"]
        if not isinstance(client_info_data, dict):
            raise ValueError("clientInfo must be an object")
            
        # Parse and validate client information
        client_info = MCPClientInfo(
            name=client_info_data.get("name", "unknown-client"),
            version=client_info_data.get("version", "unknown"),
            protocol_version=params.get("protocolVersion", MCPProtocolVersion.V2024_11_05),
            capabilities=params.get("capabilities", {})
        )
        
        # Validate protocol version compatibility
        supported_versions = [MCPProtocolVersion.V2024_11_05]
        if client_info.protocol_version not in [v.value for v in supported_versions]:
            raise ValueError(
                f"Unsupported protocol version: {client_info.protocol_version}. "
                f"Supported versions: {[v.value for v in supported_versions]}"
            )
        
        # Perform capability negotiation
        negotiated_capabilities = self._negotiate_capabilities(
            client_info.capabilities or {},
            session
        )
        
        # Create server info with negotiated capabilities
        server_info = MCPServerInfo(
            capabilities=negotiated_capabilities
        )
        
        # Update session with capability agreement
        session.client_info = client_info
        session.server_info = server_info
        session.capabilities = self._create_capability_flags(negotiated_capabilities)
        
        # Note: Authentication handled separately via auth middleware
        session.authenticated = True  # Will be set by auth middleware
        
        self.logger.info(
            "MCP session initialized with capability negotiation",
            session_id=session.session_id,
            client_name=client_info.name,
            client_version=client_info.version,
            protocol_version=client_info.protocol_version,
            negotiated_capabilities=list(negotiated_capabilities.keys()),
            client_capabilities=list((client_info.capabilities or {}).keys())
        )
        
        return {
            "protocolVersion": server_info.protocol_version,
            "serverInfo": {
                "name": server_info.name,
                "version": server_info.version
            },
            "capabilities": negotiated_capabilities,
            "instructions": "Session initialized successfully. Use 'initialized' notification to complete handshake."
        }

    async def _handle_initialized(self, session: ConnectionSession, params: Any) -> None:
        """
        Handle MCP initialized notification - Complete the handshake
        
        Sent by client after receiving initialize response to confirm
        that capability negotiation is accepted and session is ready.
        """
        if not session.is_initialized():
            self.logger.warning(
                "Received 'initialized' notification but session not properly initialized",
                session_id=session.session_id
            )
            return
        
        # Mark session as fully operational
        session.update_activity()
        
        # Log successful handshake completion
        self.logger.info(
            "MCP handshake completed successfully",
            session_id=session.session_id,
            client_name=session.client_info.name if session.client_info else "unknown",
            protocol_version=session.client_info.protocol_version if session.client_info else "unknown",
            active_capabilities=list(session.capabilities.keys()) if session.capabilities else [],
            session_ready=True
        )
        
        # Send any pending notifications about available capabilities
        if session.capabilities.get("tools", False):
            await self._send_capability_change_notification(
                session, "tools", "available"
            )
        
        if session.capabilities.get("resources", False):
            await self._send_capability_change_notification(
                session, "resources", "available"
            )
        
        if session.capabilities.get("prompts", False):
            await self._send_capability_change_notification(
                session, "prompts", "available"
            )
        
        # This is a notification, no response needed

    async def _handle_ping(self, session: ConnectionSession, params: Any) -> Dict[str, Any]:
        """Handle ping request for connection keepalive"""
        return {"status": "pong", "timestamp": datetime.utcnow().isoformat()}

    async def _handle_notification_cancelled(self, session: ConnectionSession, params: Any) -> None:
        """Handle cancelled notification"""
        request_id = params.get("requestId") if params else None
        self.logger.info(
            "Request cancelled by client",
            session_id=session.session_id,
            cancelled_request_id=request_id
        )
        # Implementation would cancel the specified request
        # For now, we just log it

    async def _handle_notification_progress(self, session: ConnectionSession, params: Any) -> None:
        """Handle progress notification from client"""
        # This would typically be sent by the server to client, not vice versa
        # But we handle it for completeness
        self.logger.debug(
            "Progress notification from client",
            session_id=session.session_id,
            progress=params
        )

    async def _handle_logging_set_level(self, session: ConnectionSession, params: Any) -> Dict[str, Any]:
        """Handle logging level change request"""
        if not params or "level" not in params:
            raise ValueError("level parameter required")
            
        level = params["level"]
        valid_levels = ["debug", "info", "notice", "warning", "error", "critical", "alert", "emergency"]
        
        if level not in valid_levels:
            raise ValueError(f"Invalid log level. Must be one of: {valid_levels}")
            
        # Update logging level for this session
        # (In a real implementation, you might want to update the logger configuration)
        self.logger.info(
            "Log level changed",
            session_id=session.session_id,
            new_level=level
        )
        
        return {"success": True}

    # Capability Negotiation Methods

    def _negotiate_capabilities(
        self, 
        client_capabilities: Dict[str, Any], 
        session: ConnectionSession
    ) -> Dict[str, Any]:
        """
        Negotiate capabilities between client and server
        
        Args:
            client_capabilities: Capabilities requested by client
            session: Current session for context-specific negotiation
            
        Returns:
            Dictionary of negotiated capabilities
        """
        negotiated = {}
        
        # Tools capability negotiation
        if MCPCapability.TOOLS in self.server_capabilities:
            client_tools = client_capabilities.get("tools", {})
            server_tools = self.server_capabilities[MCPCapability.TOOLS]
            
            negotiated[MCPCapability.TOOLS] = {
                "listChanged": server_tools.get("listChanged", False),
                "supports_progress": (
                    server_tools.get("supports_progress", False) and
                    client_tools.get("supports_progress", True)  # Default to True for clients
                ),
                "available_tools": [
                    "list_contexts", "switch_context", "get_context_info",
                    "query", "find_concept", "get_relationships", "search_docs", 
                    "search_documents", "get_summary", "explore_graph", "clear_cache", "help"
                ]
            }
        
        # Resources capability negotiation
        if MCPCapability.RESOURCES in self.server_capabilities:
            client_resources = client_capabilities.get("resources", {})
            server_resources = self.server_capabilities[MCPCapability.RESOURCES]
            
            negotiated[MCPCapability.RESOURCES] = {
                "subscribe": (
                    server_resources.get("subscribe", False) and
                    client_resources.get("subscribe", True)
                ),
                "listChanged": server_resources.get("listChanged", False),
                "available_resources": [
                    "document_content", "processed_chunks", "knowledge_graph"
                ]
            }
        
        # Prompts capability negotiation
        if MCPCapability.PROMPTS in self.server_capabilities:
            client_prompts = client_capabilities.get("prompts", {})
            server_prompts = self.server_capabilities[MCPCapability.PROMPTS]
            
            negotiated[MCPCapability.PROMPTS] = {
                "listChanged": server_prompts.get("listChanged", False),
                "available_prompts": [
                    "documentation_search", "architecture_discovery", 
                    "best_practices", "code_review", "user_story_context_builder"
                ]
            }
        
        # Logging capability negotiation
        if MCPCapability.LOGGING in self.server_capabilities:
            client_logging = client_capabilities.get("logging", {})
            server_logging = self.server_capabilities[MCPCapability.LOGGING]
            
            # Client can request different log level
            requested_level = client_logging.get("level", "info")
            valid_levels = ["debug", "info", "notice", "warning", "error", "critical", "alert", "emergency"]
            
            negotiated[MCPCapability.LOGGING] = {
                "level": requested_level if requested_level in valid_levels else "info",
                "supports_level_change": True
            }
        
        # Experimental sampling (if requested by client)
        if (
            MCPCapability.EXPERIMENTAL_SAMPLING in client_capabilities and
            MCPCapability.EXPERIMENTAL_SAMPLING in self.server_capabilities
        ):
            negotiated[MCPCapability.EXPERIMENTAL_SAMPLING] = {
                "supports_sampling": False  # Not implemented yet
            }
        
        self.logger.debug(
            "Capability negotiation completed",
            session_id=session.session_id,
            client_requested=list(client_capabilities.keys()),
            server_available=list(self.server_capabilities.keys()),
            negotiated=list(negotiated.keys())
        )
        
        return negotiated

    def _create_capability_flags(self, capabilities: Dict[str, Any]) -> Dict[str, bool]:
        """
        Create simple capability flags from negotiated capabilities
        
        Args:
            capabilities: Negotiated capabilities dictionary
            
        Returns:
            Simple boolean flags for quick capability checking
        """
        return {
            "tools": MCPCapability.TOOLS in capabilities,
            "resources": MCPCapability.RESOURCES in capabilities,
            "prompts": MCPCapability.PROMPTS in capabilities,
            "logging": MCPCapability.LOGGING in capabilities,
            "sampling": MCPCapability.EXPERIMENTAL_SAMPLING in capabilities,
            "progress_updates": capabilities.get(MCPCapability.TOOLS, {}).get("supports_progress", False),
            "resource_subscriptions": capabilities.get(MCPCapability.RESOURCES, {}).get("subscribe", False),
            "prompt_changes": capabilities.get(MCPCapability.PROMPTS, {}).get("listChanged", False),
        }

    def _validate_capability_request(
        self, 
        session: ConnectionSession, 
        required_capability: str
    ) -> bool:
        """
        Validate if session has required capability
        
        Args:
            session: Connection session
            required_capability: Required capability name
            
        Returns:
            True if capability is available, False otherwise
        """
        if not session.is_initialized():
            return False
            
        capability_flags = session.capabilities or {}
        return capability_flags.get(required_capability, False)

    async def _send_capability_change_notification(
        self, 
        session: ConnectionSession, 
        capability_type: str,
        change_type: str = "updated"
    ):
        """
        Send capability change notification to client
        
        Args:
            session: Target session
            capability_type: Type of capability that changed
            change_type: Type of change (updated, added, removed)
        """
        notification = {
            "jsonrpc": "2.0",
            "method": f"notifications/{capability_type}/listChanged",
            "params": {
                "change_type": change_type,
                "timestamp": datetime.utcnow().isoformat()
            }
        }
        
        # In a real implementation, you would send this to the specific session
        # For now, we log it
        self.logger.info(
            "Capability change notification",
            session_id=session.session_id,
            capability_type=capability_type,
            change_type=change_type
        )

    def _validate_method_capability(self, session: ConnectionSession, method: str) -> bool:
        """
        Validate if a method can be executed based on negotiated capabilities
        
        Args:
            session: Connection session with negotiated capabilities
            method: Method name to validate
            
        Returns:
            True if method is allowed, False otherwise
        """
        # Core protocol methods are always allowed
        core_methods = [
            "initialize", "initialized", "ping", 
            "notifications/cancelled", "notifications/progress", "logging/setLevel"
        ]
        
        if method in core_methods:
            return True
        
        # Tools methods require tools capability
        tools_methods = [
            "tools/list", "tools/call",
            # LightRAG-specific tool methods that will be implemented
            "list_contexts", "switch_context", "get_context_info",
            "query", "find_concept", "get_relationships", "search_docs",
            "search_documents", "get_summary", "explore_graph", "clear_cache", "help"
        ]
        
        if method in tools_methods:
            return self._validate_capability_request(session, "tools")
        
        # Resources methods require resources capability
        resources_methods = [
            "resources/list", "resources/read", "resources/subscribe", "resources/unsubscribe",
            # LightRAG-specific resource methods that will be implemented
            "get_full_document", "get_processed_chunks"
        ]
        
        if method in resources_methods:
            return self._validate_capability_request(session, "resources")
        
        # Prompts methods require prompts capability
        prompts_methods = [
            "prompts/list", "prompts/get",
            # LightRAG-specific prompt methods that will be implemented
            "get_prompt_template", "render_prompt"
        ]
        
        if method in prompts_methods:
            return self._validate_capability_request(session, "prompts")
        
        # Unknown methods are allowed by default (for extensibility)
        self.logger.debug(
            "Unknown method - allowing by default",
            session_id=session.session_id,
            method=method
        )
        return True

    def _get_required_capability(self, method: str) -> str:
        """
        Get the required capability for a specific method
        
        Args:
            method: Method name
            
        Returns:
            Required capability name
        """
        tools_methods = [
            "tools/list", "tools/call",
            "list_contexts", "switch_context", "get_context_info",
            "query", "find_concept", "get_relationships", "search_docs",
            "search_documents", "get_summary", "explore_graph", "clear_cache", "help"
        ]
        
        resources_methods = [
            "resources/list", "resources/read", "resources/subscribe", "resources/unsubscribe",
            "get_full_document", "get_processed_chunks"
        ]
        
        prompts_methods = [
            "prompts/list", "prompts/get",
            "get_prompt_template", "render_prompt"
        ]
        
        if method in tools_methods:
            return "tools"
        elif method in resources_methods:
            return "resources"
        elif method in prompts_methods:
            return "prompts"
        else:
            return "unknown"

    # Utility Methods

    def get_session(self, session_id: str) -> Optional[ConnectionSession]:
        """Get session by ID"""
        return self.sessions.get(session_id)

    def get_active_sessions(self) -> List[ConnectionSession]:
        """Get list of all active sessions"""
        return list(self.sessions.values())

    def get_session_count(self) -> int:
        """Get count of active sessions"""
        return len(self.sessions)

    async def broadcast_notification(self, method: str, params: Any):
        """Broadcast notification to all connected clients"""
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        }
        
        message = json.dumps(notification)
        
        # In a real implementation, you'd need WebSocket references
        # This is a placeholder for the broadcasting mechanism
        self.logger.info(
            "Broadcasting notification",
            method=method,
            active_sessions=len(self.sessions)
        )

    async def shutdown(self):
        """Gracefully shutdown the protocol server"""
        self.logger.info("Shutting down MCP protocol server")
        
        # Close all active sessions
        for session in self.sessions.values():
            self.logger.debug("Closing session", session_id=session.session_id)
            
        self.sessions.clear()
        self.logger.info("MCP protocol server shutdown complete") 