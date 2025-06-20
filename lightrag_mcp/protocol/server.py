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
- Streaming response handling for long-running operations
- Progress tracking and cancellation support
- Comprehensive protocol validation and error responses
"""

import asyncio
import json
import logging
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Union

import structlog
from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, validator

from ..auth import verify_token
from ..config import MCPConfig
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

    # Extended capabilities for enhanced functionality
    PROGRESS_NOTIFICATIONS = "progress"
    CANCELLATION = "cancellation"
    ROOTS = "roots"
    COMPLETION = "completion"


class MCPProtocolVersion(str, Enum):
    """MCP protocol version"""

    V2024_11_05 = "2024-11-05"


class OperationStatus(str, Enum):
    """Status of long-running operations"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ValidationSeverity(str, Enum):
    """Validation error severity levels"""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ValidationResult:
    """Result of protocol validation"""

    is_valid: bool
    severity: ValidationSeverity
    message: str
    field: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    suggestions: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "is_valid": self.is_valid,
            "severity": self.severity.value,
            "message": self.message,
            "field": self.field,
            "details": self.details,
            "suggestions": self.suggestions,
        }


class MCPProtocolValidator:
    """Comprehensive MCP protocol validator"""

    # Valid JSON-RPC ID patterns
    VALID_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\.]{1,64}$")

    # Valid method name patterns
    VALID_METHOD_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_\/]*$")

    # Maximum message size (1MB)
    MAX_MESSAGE_SIZE = 1024 * 1024

    # Maximum parameter depth
    MAX_PARAM_DEPTH = 10

    def __init__(self):
        self.validation_history = []

    def validate_json_rpc_request(self, data: Dict[str, Any]) -> List[ValidationResult]:
        """Validate JSON-RPC request structure"""
        results = []

        # Check required fields
        if "jsonrpc" not in data:
            results.append(
                ValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.ERROR,
                    message="Missing required field 'jsonrpc'",
                    field="jsonrpc",
                    suggestions=["Add 'jsonrpc': '2.0' to your request"],
                )
            )
        elif data["jsonrpc"] != "2.0":
            results.append(
                ValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.ERROR,
                    message=f"Invalid JSON-RPC version: {data['jsonrpc']}",
                    field="jsonrpc",
                    suggestions=[
                        "Use 'jsonrpc': '2.0' as per JSON-RPC 2.0 specification"
                    ],
                )
            )

        if "method" not in data:
            results.append(
                ValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.ERROR,
                    message="Missing required field 'method'",
                    field="method",
                    suggestions=[
                        "Add 'method' field with the name of the method to call"
                    ],
                )
            )
        else:
            method_validation = self._validate_method_name(data["method"])
            results.extend(method_validation)

        # Validate ID if present
        if "id" in data:
            id_validation = self._validate_request_id(data["id"])
            results.extend(id_validation)

        # Validate params if present
        if "params" in data:
            param_validation = self._validate_params(data["params"])
            results.extend(param_validation)

        # Check for unexpected fields
        expected_fields = {"jsonrpc", "method", "params", "id"}
        unexpected_fields = set(data.keys()) - expected_fields
        if unexpected_fields:
            results.append(
                ValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.WARNING,
                    message=f"Unexpected fields in request: {', '.join(unexpected_fields)}",
                    details={"unexpected_fields": list(unexpected_fields)},
                    suggestions=[
                        "Remove unexpected fields or check JSON-RPC 2.0 specification"
                    ],
                )
            )

        return results

    def validate_json_rpc_response(
        self, data: Dict[str, Any]
    ) -> List[ValidationResult]:
        """Validate JSON-RPC response structure"""
        results = []

        # Check required fields
        if "jsonrpc" not in data:
            results.append(
                ValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.ERROR,
                    message="Missing required field 'jsonrpc'",
                    field="jsonrpc",
                )
            )
        elif data["jsonrpc"] != "2.0":
            results.append(
                ValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.ERROR,
                    message=f"Invalid JSON-RPC version: {data['jsonrpc']}",
                    field="jsonrpc",
                )
            )

        # Must have either result or error, but not both
        has_result = "result" in data
        has_error = "error" in data

        if not has_result and not has_error:
            results.append(
                ValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.ERROR,
                    message="Response must have either 'result' or 'error' field",
                    suggestions=[
                        "Add either 'result' for success or 'error' for failure"
                    ],
                )
            )
        elif has_result and has_error:
            results.append(
                ValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.ERROR,
                    message="Response cannot have both 'result' and 'error' fields",
                    suggestions=[
                        "Include only 'result' for success or only 'error' for failure"
                    ],
                )
            )

        # Validate error structure if present
        if has_error:
            error_validation = self._validate_error_object(data["error"])
            results.extend(error_validation)

        return results

    def validate_mcp_initialize_params(
        self, params: Dict[str, Any]
    ) -> List[ValidationResult]:
        """Validate MCP initialize method parameters"""
        results = []

        # Check required fields
        if "protocolVersion" not in params:
            results.append(
                ValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.ERROR,
                    message="Missing required field 'protocolVersion'",
                    field="protocolVersion",
                    suggestions=[
                        "Add 'protocolVersion' field with supported MCP version"
                    ],
                )
            )
        else:
            version = params["protocolVersion"]
            if version not in [v.value for v in MCPProtocolVersion]:
                results.append(
                    ValidationResult(
                        is_valid=False,
                        severity=ValidationSeverity.ERROR,
                        message=f"Unsupported protocol version: {version}",
                        field="protocolVersion",
                        details={
                            "supported_versions": [v.value for v in MCPProtocolVersion]
                        },
                        suggestions=[
                            f"Use supported version: {MCPProtocolVersion.V2024_11_05.value}"
                        ],
                    )
                )

        if "clientInfo" not in params:
            results.append(
                ValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.ERROR,
                    message="Missing required field 'clientInfo'",
                    field="clientInfo",
                    suggestions=[
                        "Add 'clientInfo' object with 'name' and 'version' fields"
                    ],
                )
            )
        else:
            client_info_validation = self._validate_client_info(params["clientInfo"])
            results.extend(client_info_validation)

        # Validate capabilities if present
        if "capabilities" in params:
            capabilities_validation = self._validate_capabilities(
                params["capabilities"]
            )
            results.extend(capabilities_validation)

        return results

    def validate_mcp_tool_call_params(
        self, params: Dict[str, Any]
    ) -> List[ValidationResult]:
        """Validate MCP tools/call method parameters"""
        results = []

        if "name" not in params:
            results.append(
                ValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.ERROR,
                    message="Missing required field 'name'",
                    field="name",
                    suggestions=["Add 'name' field with the tool name to call"],
                )
            )
        else:
            name = params["name"]
            if not isinstance(name, str) or not name.strip():
                results.append(
                    ValidationResult(
                        is_valid=False,
                        severity=ValidationSeverity.ERROR,
                        message="Tool name must be a non-empty string",
                        field="name",
                    )
                )

        # Validate arguments if present
        if "arguments" in params:
            args = params["arguments"]
            if not isinstance(args, dict):
                results.append(
                    ValidationResult(
                        is_valid=False,
                        severity=ValidationSeverity.ERROR,
                        message="Tool arguments must be an object",
                        field="arguments",
                        suggestions=[
                            "Provide arguments as a JSON object with key-value pairs"
                        ],
                    )
                )

        return results

    def validate_message_size(self, message: str) -> List[ValidationResult]:
        """Validate message size limits"""
        results = []

        message_size = len(message.encode("utf-8"))
        if message_size > self.MAX_MESSAGE_SIZE:
            results.append(
                ValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.ERROR,
                    message=f"Message size {message_size} bytes exceeds limit of {self.MAX_MESSAGE_SIZE} bytes",
                    details={
                        "message_size": message_size,
                        "limit": self.MAX_MESSAGE_SIZE,
                    },
                    suggestions=[
                        "Reduce message size by simplifying parameters",
                        "Split large requests into smaller chunks",
                        "Use streaming for large data transfers",
                    ],
                )
            )
        elif message_size > self.MAX_MESSAGE_SIZE * 0.8:
            results.append(
                ValidationResult(
                    is_valid=True,
                    severity=ValidationSeverity.WARNING,
                    message=f"Message size {message_size} bytes is approaching limit",
                    details={
                        "message_size": message_size,
                        "limit": self.MAX_MESSAGE_SIZE,
                    },
                )
            )

        return results

    def _validate_method_name(self, method: str) -> List[ValidationResult]:
        """Validate method name format"""
        results = []

        if not isinstance(method, str):
            results.append(
                ValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.ERROR,
                    message="Method name must be a string",
                    field="method",
                )
            )
            return results

        if not method:
            results.append(
                ValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.ERROR,
                    message="Method name cannot be empty",
                    field="method",
                )
            )
            return results

        if not self.VALID_METHOD_PATTERN.match(method):
            results.append(
                ValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.ERROR,
                    message=f"Invalid method name format: {method}",
                    field="method",
                    suggestions=[
                        "Method names should start with a letter",
                        "Use only letters, numbers, underscores, and forward slashes",
                        "Examples: 'initialize', 'tools/call', 'resources/list'",
                    ],
                )
            )

        return results

    def _validate_request_id(self, request_id: Any) -> List[ValidationResult]:
        """Validate request ID format"""
        results = []

        if request_id is None:
            return results  # ID is optional for notifications

        if not isinstance(request_id, (str, int)):
            results.append(
                ValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.ERROR,
                    message="Request ID must be a string, number, or null",
                    field="id",
                )
            )
            return results

        if isinstance(request_id, str):
            if len(request_id) > 64:
                results.append(
                    ValidationResult(
                        is_valid=False,
                        severity=ValidationSeverity.ERROR,
                        message="String request ID cannot exceed 64 characters",
                        field="id",
                    )
                )
            elif not self.VALID_ID_PATTERN.match(request_id):
                results.append(
                    ValidationResult(
                        is_valid=False,
                        severity=ValidationSeverity.WARNING,
                        message="Request ID contains unusual characters",
                        field="id",
                        suggestions=[
                            "Use alphanumeric characters, hyphens, underscores, and dots only"
                        ],
                    )
                )

        return results

    def _validate_params(self, params: Any) -> List[ValidationResult]:
        """Validate request parameters"""
        results = []

        if params is None:
            return results  # Params are optional

        if not isinstance(params, (dict, list)):
            results.append(
                ValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.ERROR,
                    message="Parameters must be an object or array",
                    field="params",
                )
            )
            return results

        # Check parameter depth
        depth = self._calculate_depth(params)
        if depth > self.MAX_PARAM_DEPTH:
            results.append(
                ValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.ERROR,
                    message=f"Parameter depth {depth} exceeds maximum of {self.MAX_PARAM_DEPTH}",
                    field="params",
                    details={"depth": depth, "max_depth": self.MAX_PARAM_DEPTH},
                    suggestions=["Flatten nested parameter structure"],
                )
            )

        return results

    def _validate_error_object(self, error: Any) -> List[ValidationResult]:
        """Validate JSON-RPC error object"""
        results = []

        if not isinstance(error, dict):
            results.append(
                ValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.ERROR,
                    message="Error must be an object",
                    field="error",
                )
            )
            return results

        # Check required fields
        if "code" not in error:
            results.append(
                ValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.ERROR,
                    message="Error object missing required 'code' field",
                    field="error.code",
                )
            )
        elif not isinstance(error["code"], int):
            results.append(
                ValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.ERROR,
                    message="Error code must be an integer",
                    field="error.code",
                )
            )

        if "message" not in error:
            results.append(
                ValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.ERROR,
                    message="Error object missing required 'message' field",
                    field="error.message",
                )
            )
        elif not isinstance(error["message"], str):
            results.append(
                ValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.ERROR,
                    message="Error message must be a string",
                    field="error.message",
                )
            )

        return results

    def _validate_client_info(self, client_info: Any) -> List[ValidationResult]:
        """Validate client info object"""
        results = []

        if not isinstance(client_info, dict):
            results.append(
                ValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.ERROR,
                    message="Client info must be an object",
                    field="clientInfo",
                )
            )
            return results

        # Check required fields
        if "name" not in client_info:
            results.append(
                ValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.ERROR,
                    message="Client info missing required 'name' field",
                    field="clientInfo.name",
                )
            )
        elif (
            not isinstance(client_info["name"], str) or not client_info["name"].strip()
        ):
            results.append(
                ValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.ERROR,
                    message="Client name must be a non-empty string",
                    field="clientInfo.name",
                )
            )

        if "version" not in client_info:
            results.append(
                ValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.ERROR,
                    message="Client info missing required 'version' field",
                    field="clientInfo.version",
                )
            )
        elif (
            not isinstance(client_info["version"], str)
            or not client_info["version"].strip()
        ):
            results.append(
                ValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.ERROR,
                    message="Client version must be a non-empty string",
                    field="clientInfo.version",
                )
            )

        return results

    def _validate_capabilities(self, capabilities: Any) -> List[ValidationResult]:
        """Validate capabilities object"""
        results = []

        if not isinstance(capabilities, dict):
            results.append(
                ValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.ERROR,
                    message="Capabilities must be an object",
                    field="capabilities",
                )
            )
            return results

        # Check for unknown capabilities
        known_capabilities = {cap.value for cap in MCPCapability}
        unknown_caps = set(capabilities.keys()) - known_capabilities

        if unknown_caps:
            results.append(
                ValidationResult(
                    is_valid=True,
                    severity=ValidationSeverity.WARNING,
                    message=f"Unknown capabilities: {', '.join(unknown_caps)}",
                    field="capabilities",
                    details={
                        "unknown_capabilities": list(unknown_caps),
                        "known_capabilities": list(known_capabilities),
                    },
                    suggestions=["Check capability names against MCP specification"],
                )
            )

        return results

    def _calculate_depth(self, obj: Any, current_depth: int = 0) -> int:
        """Calculate nested depth of an object"""
        if current_depth > self.MAX_PARAM_DEPTH:
            return current_depth

        if isinstance(obj, dict):
            if not obj:
                return current_depth
            return max(
                self._calculate_depth(v, current_depth + 1) for v in obj.values()
            )
        elif isinstance(obj, list):
            if not obj:
                return current_depth
            return max(self._calculate_depth(item, current_depth + 1) for item in obj)
        else:
            return current_depth

    def get_validation_summary(self) -> Dict[str, Any]:
        """Get validation statistics summary"""
        if not self.validation_history:
            return {"total_validations": 0, "error_count": 0, "warning_count": 0}

        error_count = sum(
            1
            for result in self.validation_history
            if result.severity == ValidationSeverity.ERROR
        )
        warning_count = sum(
            1
            for result in self.validation_history
            if result.severity == ValidationSeverity.WARNING
        )

        return {
            "total_validations": len(self.validation_history),
            "error_count": error_count,
            "warning_count": warning_count,
            "success_rate": (
                (len(self.validation_history) - error_count)
                / len(self.validation_history)
                if self.validation_history
                else 0
            ),
        }


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

    # Streaming operation error codes
    OPERATION_NOT_FOUND = -32111
    OPERATION_CANCELLED = -32112
    STREAMING_ERROR = -32113


class JSONRPCError:
    """Enhanced JSON-RPC error representation with detailed context"""

    def __init__(self, code: int, message: str, data: Optional[Dict[str, Any]] = None):
        self.code = code
        self.message = message
        self.data = data

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
        error_id: Optional[str] = None,
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

        return cls(code=code.value, message=message, data=data if data else None)

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

    @validator("method")
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

    @validator("result", "error")
    def validate_result_or_error(cls, v, values):
        # Exactly one of result or error must be present
        if "result" in values and "error" in values:
            if (values.get("result") is None) == (values.get("error") is None):
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


class ConnectionState(str, Enum):
    """Connection state enumeration"""

    CONNECTING = "connecting"
    CONNECTED = "connected"
    INITIALIZING = "initializing"
    INITIALIZED = "initialized"
    ACTIVE = "active"
    IDLE = "idle"
    DISCONNECTING = "disconnecting"
    DISCONNECTED = "disconnected"
    ERROR = "error"


@dataclass
class ConnectionSession:
    """Represents an active MCP connection session with comprehensive lifecycle management"""

    session_id: str
    client_info: Optional[MCPClientInfo] = None
    server_info: Optional[MCPServerInfo] = None
    capabilities: Dict[str, bool] = None
    context: Optional[str] = None
    authenticated: bool = False
    user_id: Optional[str] = None
    connected_at: datetime = None
    last_activity: datetime = None

    # Enhanced connection lifecycle fields
    state: ConnectionState = ConnectionState.CONNECTING
    websocket: Optional[WebSocket] = None
    connection_metadata: Dict[str, Any] = None
    resource_usage: Dict[str, Any] = None
    error_count: int = 0
    last_error: Optional[str] = None
    heartbeat_count: int = 0
    last_heartbeat: Optional[datetime] = None
    cleanup_scheduled: bool = False
    disconnect_reason: Optional[str] = None
    session_timeout: Optional[datetime] = None

    def __post_init__(self):
        if self.connected_at is None:
            self.connected_at = datetime.utcnow()
        if self.last_activity is None:
            self.last_activity = datetime.utcnow()
        if self.capabilities is None:
            self.capabilities = {}
        if self.connection_metadata is None:
            self.connection_metadata = {}
        if self.resource_usage is None:
            self.resource_usage = {
                "messages_sent": 0,
                "messages_received": 0,
                "bytes_sent": 0,
                "bytes_received": 0,
                "operations_started": 0,
                "operations_completed": 0,
                "errors_encountered": 0,
            }

    def update_activity(self):
        """Update last activity timestamp and manage session state"""
        self.last_activity = datetime.utcnow()

        # Auto-transition from IDLE to ACTIVE if there's activity
        if self.state == ConnectionState.IDLE:
            self.state = ConnectionState.ACTIVE

    def update_state(self, new_state: ConnectionState, reason: Optional[str] = None):
        """Update connection state with optional reason"""
        old_state = self.state
        self.state = new_state
        self.last_activity = datetime.utcnow()

        # Store disconnect reason if transitioning to disconnected states
        if new_state in [
            ConnectionState.DISCONNECTING,
            ConnectionState.DISCONNECTED,
            ConnectionState.ERROR,
        ]:
            self.disconnect_reason = reason

        return old_state

    def is_initialized(self) -> bool:
        """Check if session is properly initialized"""
        return (
            self.client_info is not None
            and self.server_info is not None
            and self.authenticated
            and self.state
            in [
                ConnectionState.INITIALIZED,
                ConnectionState.ACTIVE,
                ConnectionState.IDLE,
            ]
        )

    def is_active(self) -> bool:
        """Check if session is active and can handle requests"""
        return (
            self.state in [ConnectionState.ACTIVE, ConnectionState.IDLE]
            and self.is_initialized()
        )

    def can_cleanup(self) -> bool:
        """Check if session can be cleaned up"""
        return (
            self.state in [ConnectionState.DISCONNECTED, ConnectionState.ERROR]
            or self.cleanup_scheduled
        )

    def record_message(self, message_type: str, size: int):
        """Record message statistics"""
        if message_type == "sent":
            self.resource_usage["messages_sent"] += 1
            self.resource_usage["bytes_sent"] += size
        elif message_type == "received":
            self.resource_usage["messages_received"] += 1
            self.resource_usage["bytes_received"] += size

    def record_operation(self, operation_type: str):
        """Record operation statistics"""
        if operation_type == "started":
            self.resource_usage["operations_started"] += 1
        elif operation_type == "completed":
            self.resource_usage["operations_completed"] += 1

    def record_error(self, error_message: str):
        """Record error occurrence"""
        self.error_count += 1
        self.last_error = error_message
        self.resource_usage["errors_encountered"] += 1

    def record_heartbeat(self):
        """Record heartbeat activity"""
        self.heartbeat_count += 1
        self.last_heartbeat = datetime.utcnow()
        self.update_activity()

    def is_idle(self, idle_threshold_minutes: int = 30) -> bool:
        """Check if session has been idle for specified time"""
        if not self.last_activity:
            return False

        idle_time = datetime.utcnow() - self.last_activity
        return idle_time.total_seconds() > (idle_threshold_minutes * 60)

    def is_stale(self, stale_threshold_hours: int = 24) -> bool:
        """Check if session is stale and should be cleaned up"""
        if not self.connected_at:
            return True

        session_age = datetime.utcnow() - self.connected_at
        return session_age.total_seconds() > (stale_threshold_hours * 3600)

    def get_session_duration(self) -> timedelta:
        """Get total session duration"""
        if not self.connected_at:
            return timedelta(0)

        end_time = datetime.utcnow()
        if self.state == ConnectionState.DISCONNECTED:
            # Use last activity as end time for disconnected sessions
            end_time = self.last_activity or datetime.utcnow()

        return end_time - self.connected_at

    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary for serialization"""
        return {
            "session_id": self.session_id,
            "state": self.state.value,
            "authenticated": self.authenticated,
            "user_id": self.user_id,
            "context": self.context,
            "connected_at": (
                self.connected_at.isoformat() if self.connected_at else None
            ),
            "last_activity": (
                self.last_activity.isoformat() if self.last_activity else None
            ),
            "last_heartbeat": (
                self.last_heartbeat.isoformat() if self.last_heartbeat else None
            ),
            "session_duration": str(self.get_session_duration()),
            "client_info": {
                "name": self.client_info.name if self.client_info else None,
                "version": self.client_info.version if self.client_info else None,
                "protocol_version": (
                    self.client_info.protocol_version if self.client_info else None
                ),
            },
            "capabilities": self.capabilities,
            "resource_usage": self.resource_usage,
            "statistics": {
                "error_count": self.error_count,
                "heartbeat_count": self.heartbeat_count,
                "last_error": self.last_error,
            },
            "disconnect_reason": self.disconnect_reason,
            "connection_metadata": self.connection_metadata,
        }


@dataclass
class StreamingOperation:
    """Represents a streaming operation with progress tracking"""

    operation_id: str
    method: str
    session_id: str
    params: Optional[Dict[str, Any]] = None
    status: OperationStatus = OperationStatus.PENDING
    progress: float = 0.0
    message: str = "Operation started"
    result: Optional[Any] = None
    error: Optional[str] = None
    created_at: datetime = None
    updated_at: datetime = None
    task: Optional[asyncio.Task] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.updated_at is None:
            self.updated_at = datetime.utcnow()

    def update_progress(
        self, progress: float, message: str, status: Optional[OperationStatus] = None
    ):
        """Update operation progress"""
        self.progress = max(0.0, min(1.0, progress))  # Clamp between 0 and 1
        self.message = message
        if status:
            self.status = status
        self.updated_at = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "operation_id": self.operation_id,
            "method": self.method,
            "session_id": self.session_id,
            "params": self.params,
            "status": self.status.value,
            "progress": self.progress,
            "message": self.message,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


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
        context: Optional[Dict[str, Any]] = None,
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
                    **(context or {}),
                },
                suggestions=[
                    "Check that your client supports MCP protocol version 2024-11-05",
                    "Update your MCP client to the latest version",
                    "Verify the protocolVersion field in your initialize request",
                ],
                error_id=f"init_{session_id}_{self.error_count}",
            )
        elif "clientInfo" in str(error):
            return JSONRPCError.create_detailed_error(
                JSONRPCErrorCode.INITIALIZATION_ERROR,
                "Client information validation failed",
                details=str(error),
                context={
                    "session_id": session_id,
                    "error_type": "client_info_invalid",
                    **(context or {}),
                },
                suggestions=[
                    "Ensure clientInfo object is provided with name and version fields",
                    "Check that clientInfo is a valid JSON object",
                    "Verify all required clientInfo fields are present",
                ],
                error_id=f"init_{session_id}_{self.error_count}",
            )
        else:
            return JSONRPCError.create_detailed_error(
                JSONRPCErrorCode.INITIALIZATION_ERROR,
                "Session initialization failed",
                details=str(error),
                context={
                    "session_id": session_id,
                    "error_type": "initialization_failure",
                    **(context or {}),
                },
                suggestions=[
                    "Verify all required parameters are provided",
                    "Check your authentication credentials",
                    "Try reinitializing the connection",
                ],
                error_id=f"init_{session_id}_{self.error_count}",
            )

    def handle_capability_error(
        self,
        session_id: str,
        method: str,
        missing_capability: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> JSONRPCError:
        """Handle capability-related errors"""
        self.error_count += 1

        capability_suggestions = {
            "tools": [
                "Ensure your client requests 'tools' capability during initialization",
                "Check that tools capability was successfully negotiated",
                "Use the discovery endpoint to see available capabilities",
            ],
            "resources": [
                "Ensure your client requests 'resources' capability during initialization",
                "Check that resources capability was successfully negotiated",
                "Verify you have permission to access document resources",
            ],
            "prompts": [
                "Ensure your client requests 'prompts' capability during initialization",
                "Check that prompts capability was successfully negotiated",
                "Verify prompt templates are available in your context",
            ],
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
                **(context or {}),
            },
            suggestions=capability_suggestions.get(
                missing_capability,
                [
                    f"Ensure your client requests '{missing_capability}' capability during initialization",
                    "Check the server's capability negotiation response",
                    "Verify your client supports the required capability",
                ],
            ),
            error_id=f"cap_{session_id}_{self.error_count}",
        )

    def handle_validation_error(
        self,
        session_id: str,
        method: str,
        validation_error: Exception,
        context: Optional[Dict[str, Any]] = None,
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
                **(context or {}),
            },
            suggestions=[
                "Check that all required parameters are provided",
                "Verify parameter types match the expected schema",
                "Review the method documentation for parameter requirements",
                "Use the discovery endpoint to see method specifications",
            ],
            error_id=f"val_{session_id}_{self.error_count}",
        )

    def handle_lightrag_api_error(
        self,
        session_id: str,
        method: str,
        api_error: Exception,
        context: Optional[Dict[str, Any]] = None,
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
                    **(context or {}),
                },
                suggestions=[
                    "Check that the LightRAG API server is running",
                    "Verify network connectivity to the LightRAG service",
                    "Check LightRAG API endpoint configuration",
                    "Try again after a brief delay",
                ],
                error_id=f"api_{session_id}_{self.error_count}",
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
                    **(context or {}),
                },
                suggestions=[
                    "Try a simpler query to reduce processing time",
                    "Check if the LightRAG service is overloaded",
                    "Consider breaking complex operations into smaller parts",
                    "Retry the operation after a brief delay",
                ],
                error_id=f"timeout_{session_id}_{self.error_count}",
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
                    **(context or {}),
                },
                suggestions=[
                    "Check the LightRAG API server logs for more details",
                    "Verify that the requested context exists",
                    "Ensure proper authentication with LightRAG API",
                    "Try the operation again with valid parameters",
                ],
                error_id=f"api_{session_id}_{self.error_count}",
            )

    def handle_internal_error(
        self,
        session_id: str,
        method: str,
        internal_error: Exception,
        context: Optional[Dict[str, Any]] = None,
    ) -> JSONRPCError:
        """Handle unexpected internal server errors"""
        self.error_count += 1

        # Log internal errors for debugging
        self.logger.error(
            "Internal server error occurred",
            session_id=session_id,
            method=method,
            error=str(internal_error),
            exc_info=True,
        )

        return JSONRPCError.create_detailed_error(
            JSONRPCErrorCode.INTERNAL_ERROR,
            "An unexpected internal server error occurred",
            details="The server encountered an unexpected error while processing your request",
            context={
                "session_id": session_id,
                "method": method,
                "error_type": "internal_server_error",
                **(context or {}),
            },
            suggestions=[
                "Try the operation again after a brief delay",
                "Check if the issue persists with a simpler request",
                "Contact system administrator if the problem continues",
                "Check server logs for detailed error information",
            ],
            error_id=f"internal_{session_id}_{self.error_count}",
        )

    def handle_parse_error(
        self, session_id: str, parse_error: Exception, raw_message: Optional[str] = None
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
                "raw_message_length": len(raw_message) if raw_message else 0,
            },
            suggestions=[
                "Verify that your request is valid JSON",
                "Check for missing quotes, brackets, or commas",
                "Ensure special characters are properly escaped",
                "Use a JSON validator to check your request format",
            ],
            error_id=f"parse_{session_id}_{self.error_count}",
        )

    def log_error_metrics(self):
        """Log error metrics for monitoring"""
        self.logger.info(
            "Error handler metrics",
            total_errors=self.error_count,
            recent_errors=len(
                [
                    e
                    for e in self.error_history
                    if (datetime.utcnow() - e.get("timestamp", datetime.min)).seconds
                    < 300
                ]
            ),
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

        # Protocol validation
        self.validator = MCPProtocolValidator()

        # Active sessions storage
        self.sessions: Dict[str, ConnectionSession] = {}

        # Method handlers registry
        self.handlers: Dict[str, Callable] = {}

        # Streaming handlers registry for long-running operations
        self.streaming_handlers: Dict[str, Callable] = {}

        # Active streaming operations
        self.streaming_operations: Dict[str, StreamingOperation] = {}

        # Server capabilities
        self.server_capabilities = {
            MCPCapability.TOOLS: {"listChanged": True, "supports_progress": True},
            MCPCapability.RESOURCES: {"subscribe": True, "listChanged": True},
            MCPCapability.PROMPTS: {"listChanged": True},
            MCPCapability.LOGGING: {"level": "info"},
            MCPCapability.PROGRESS_NOTIFICATIONS: {"supports_progress": True},
            MCPCapability.CANCELLATION: {"supports_cancellation": True},
        }

        # Register core protocol handlers
        self._register_core_handlers()

        # Register validation handlers
        self._register_validation_handlers()

    def _register_core_handlers(self):
        """Register core MCP protocol method handlers"""
        self.handlers.update(
            {
                "initialize": self._handle_initialize,
                "initialized": self._handle_initialized,
                "ping": self._handle_ping,
                "notifications/cancelled": self._handle_notification_cancelled,
                "notifications/progress": self._handle_notification_progress,
                "logging/setLevel": self._handle_logging_set_level,
                # Streaming operation handlers
                "operations/status": self._handle_operation_status,
                "operations/cancel": self._handle_operation_cancel,
                "operations/list": self._handle_list_operations,
            }
        )

    def register_handler(self, method: str, handler: Callable):
        """Register a custom method handler"""
        self.handlers[method] = handler
        self.logger.debug("Registered handler", method=method)

    def register_streaming_handler(self, method: str, handler: Callable):
        """Register a streaming method handler for long-running operations"""
        self.streaming_handlers[method] = handler
        self.logger.debug("Registered streaming handler", method=method)

    def _register_validation_handlers(self):
        """Register validation-related method handlers"""
        self.handlers.update(
            {
                "validation/validate_request": self._handle_validate_request,
                "validation/validate_response": self._handle_validate_response,
                "validation/get_summary": self._handle_get_validation_summary,
            }
        )

    async def handle_websocket(self, websocket: WebSocket, path: str):
        """
        Handle WebSocket connection for MCP protocol with comprehensive lifecycle management

        Args:
            websocket: FastAPI WebSocket connection
            path: Connection path (may contain authentication info)
        """
        session_id = str(uuid.uuid4())

        # Create session with enhanced lifecycle management
        session = await self.create_session(
            session_id=session_id,
            websocket=websocket,
            metadata={
                "path": path,
                "connection_type": "websocket",
                "client_ip": websocket.client.host if websocket.client else "unknown",
            },
        )

        self.logger.info(
            "New MCP connection established",
            session_id=session_id,
            client_ip=websocket.client.host if websocket.client else "unknown",
        )

        try:
            await websocket.accept()
            session.update_state(
                ConnectionState.CONNECTED, "WebSocket connection accepted"
            )

            async for message in websocket.iter_text():
                try:
                    session.update_activity()
                    session.record_message("received", len(message))

                    response = await self._process_message(session, message)

                    if response:
                        await websocket.send_text(response)
                        session.record_message("sent", len(response))

                except Exception as e:
                    session.record_error(f"Message processing error: {str(e)}")
                    self.logger.error(
                        "Error processing message",
                        session_id=session_id,
                        error=str(e),
                        exc_info=True,
                    )

                    # Send enhanced error response
                    error_obj = self.error_handler.handle_internal_error(
                        session_id, "websocket_processing", e
                    )
                    error_response = JSONRPCResponse(
                        id=None, error=error_obj.to_dict()
                    ).json()
                    await websocket.send_text(error_response)
                    session.record_message("sent", len(error_response))

        except WebSocketDisconnect:
            self.logger.info("MCP client disconnected", session_id=session_id)
            await self.disconnect_session(
                session_id, "WebSocket disconnect", graceful=False
            )
        except Exception as e:
            session.record_error(f"WebSocket error: {str(e)}")
            self.logger.error(
                "WebSocket error", session_id=session_id, error=str(e), exc_info=True
            )
            await self.disconnect_session(
                session_id, f"WebSocket error: {str(e)}", graceful=False
            )
        finally:
            # Ensure proper cleanup
            await self.cleanup_session(session_id)
            self.logger.debug("Session cleaned up", session_id=session_id)

    async def _process_message(
        self, session: ConnectionSession, message: str
    ) -> Optional[str]:
        """
        Process incoming JSON-RPC message with comprehensive validation

        Args:
            session: Connection session
            message: Raw JSON-RPC message

        Returns:
            JSON-RPC response string if response is needed
        """
        try:
            # Validate message size first
            size_validation = self.validator.validate_message_size(message)
            for result in size_validation:
                if not result.is_valid:
                    error_obj = self.error_handler.handle_validation_error(
                        session.session_id,
                        "message_processing",
                        ValueError(result.message),
                        {"validation_result": result.to_dict()},
                    )
                    return JSONRPCResponse(id=None, error=error_obj.to_dict()).json()
                elif result.severity == ValidationSeverity.WARNING:
                    self.logger.warning(
                        "Message size warning",
                        session_id=session.session_id,
                        validation_result=result.to_dict(),
                    )

            # Parse JSON-RPC request
            try:
                data = json.loads(message)
            except json.JSONDecodeError as e:
                error_obj = self.error_handler.handle_parse_error(
                    session.session_id,
                    e,
                    message[:100] + "..." if len(message) > 100 else message,
                )
                return JSONRPCResponse(id=None, error=error_obj.to_dict()).json()

            # Validate JSON-RPC request structure
            request_validation = self.validator.validate_json_rpc_request(data)
            validation_errors = [r for r in request_validation if not r.is_valid]

            if validation_errors:
                # Log all validation errors
                for error in validation_errors:
                    self.logger.error(
                        "JSON-RPC request validation failed",
                        session_id=session.session_id,
                        validation_error=error.to_dict(),
                    )

                # Return error for the first critical validation failure
                first_error = validation_errors[0]
                error_obj = self.error_handler.handle_validation_error(
                    session.session_id,
                    data.get("method", "unknown"),
                    ValueError(first_error.message),
                    {
                        "validation_errors": [e.to_dict() for e in validation_errors],
                        "field": first_error.field,
                        "suggestions": first_error.suggestions,
                    },
                )
                return JSONRPCResponse(
                    id=data.get("id"), error=error_obj.to_dict()
                ).json()

            # Log validation warnings
            validation_warnings = [
                r
                for r in request_validation
                if r.severity == ValidationSeverity.WARNING
            ]
            for warning in validation_warnings:
                self.logger.warning(
                    "JSON-RPC request validation warning",
                    session_id=session.session_id,
                    validation_warning=warning.to_dict(),
                )

            # Store validation results for metrics
            self.validator.validation_history.extend(request_validation)

            # Create validated request object
            request = JSONRPCRequest(**data)

            self.logger.debug(
                "Processing MCP request",
                session_id=session.session_id,
                method=request.method,
                has_id=request.id is not None,
            )

            # Check if session is initialized for non-initialization methods
            if (
                request.method not in ["initialize", "initialized", "ping"]
                and not session.is_initialized()
            ):
                error_obj = self.error_handler.handle_initialization_error(
                    session.session_id,
                    ValueError("Session not initialized. Call 'initialize' first."),
                    {
                        "method": request.method,
                        "has_client_info": session.client_info is not None,
                    },
                )
                return JSONRPCResponse(id=request.id, error=error_obj.to_dict()).json()

            # Check if this is a streaming request
            is_streaming_request = request.method in self.streaming_handlers or (
                request.params and request.params.get("streaming", False)
            )

            # Route to appropriate handler
            if request.method in self.handlers or is_streaming_request:
                try:
                    # Validate capability requirements for specific method types
                    if not self._validate_method_capability(session, request.method):
                        missing_capability = self._get_required_capability(
                            request.method
                        )
                        error_obj = self.error_handler.handle_capability_error(
                            session.session_id,
                            request.method,
                            missing_capability,
                            {
                                "negotiated_capabilities": (
                                    list(session.capabilities.keys())
                                    if session.capabilities
                                    else []
                                )
                            },
                        )
                        return JSONRPCResponse(
                            id=request.id, error=error_obj.to_dict()
                        ).json()

                    # Handle streaming requests differently
                    if is_streaming_request:
                        result = await self.handle_streaming_request(
                            session, request.method, request.params
                        )
                    else:
                        result = await self.handlers[request.method](
                            session, request.params
                        )

                    # Only send response for requests with ID (not notifications)
                    if request.id is not None:
                        return self._create_success_response(request.id, result)

                except ValueError as e:
                    # Handle validation errors with detailed context
                    if request.id is not None:
                        error_obj = self.error_handler.handle_validation_error(
                            session.session_id,
                            request.method,
                            e,
                            {"params": request.params},
                        )
                        return JSONRPCResponse(
                            id=request.id, error=error_obj.to_dict()
                        ).json()

                except Exception as e:
                    # Handle all other errors as internal errors
                    if request.id is not None:
                        error_obj = self.error_handler.handle_internal_error(
                            session.session_id,
                            request.method,
                            e,
                            {"params": request.params},
                        )
                        return JSONRPCResponse(
                            id=request.id, error=error_obj.to_dict()
                        ).json()
            else:
                if request.id is not None:
                    return self._create_error_response(
                        request.id,
                        JSONRPCErrorCode.METHOD_NOT_FOUND,
                        f"Method '{request.method}' not found",
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
                    "error_type": "request_validation",
                },
                suggestions=[
                    "Ensure your request follows JSON-RPC 2.0 specification",
                    "Check that required fields (jsonrpc, method) are present",
                    "Verify that the 'method' field is a non-empty string",
                    "For requests expecting a response, include an 'id' field",
                ],
            )
            return JSONRPCResponse(id=None, error=error_obj.to_dict()).json()

        return None

    def _create_success_response(self, request_id: Union[str, int], result: Any) -> str:
        """Create JSON-RPC success response"""
        response = JSONRPCResponse(id=request_id, result=result)
        return response.json()

    def _create_error_response(
        self,
        request_id: Optional[Union[str, int]],
        error_code: JSONRPCErrorCode,
        error_message: str,
        error_data: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create JSON-RPC error response"""
        error = JSONRPCError(
            code=error_code.value, message=error_message, data=error_data
        )
        response = JSONRPCResponse(id=request_id, error=error.to_dict())
        return response.json()

    # Core Protocol Handlers

    async def _handle_initialize(
        self, session: ConnectionSession, params: Any
    ) -> Dict[str, Any]:
        """
        Handle MCP initialize request with comprehensive validation and capability negotiation

        This is the first method called to establish the MCP session.
        Performs protocol version validation, capability matching, and session setup.
        """
        if not params or not isinstance(params, dict):
            raise ValueError("Initialize requires client info parameters")

        # Validate initialize parameters using comprehensive validator
        init_validation = self.validator.validate_mcp_initialize_params(params)
        validation_errors = [r for r in init_validation if not r.is_valid]

        if validation_errors:
            # Log validation errors
            for error in validation_errors:
                self.logger.error(
                    "Initialize parameter validation failed",
                    session_id=session.session_id,
                    validation_error=error.to_dict(),
                )

            # Raise validation error with detailed information
            first_error = validation_errors[0]
            error_msg = f"Initialize validation failed: {first_error.message}"
            if first_error.field:
                error_msg += f" (field: {first_error.field})"
            if first_error.suggestions:
                error_msg += f". Suggestions: {', '.join(first_error.suggestions)}"
            raise ValueError(error_msg)

        # Log validation warnings
        validation_warnings = [
            r for r in init_validation if r.severity == ValidationSeverity.WARNING
        ]
        for warning in validation_warnings:
            self.logger.warning(
                "Initialize parameter validation warning",
                session_id=session.session_id,
                validation_warning=warning.to_dict(),
            )

        # Store validation results for metrics
        self.validator.validation_history.extend(init_validation)

        # Validate required parameters (redundant but explicit)
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
            protocol_version=params.get(
                "protocolVersion", MCPProtocolVersion.V2024_11_05
            ),
            capabilities=params.get("capabilities", {}),
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
            client_info.capabilities or {}, session
        )

        # Create server info with negotiated capabilities
        server_info = MCPServerInfo(capabilities=negotiated_capabilities)

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
            client_capabilities=list((client_info.capabilities or {}).keys()),
        )

        return {
            "protocolVersion": server_info.protocol_version,
            "serverInfo": {"name": server_info.name, "version": server_info.version},
            "capabilities": negotiated_capabilities,
            "instructions": "Session initialized successfully. Use 'initialized' notification to complete handshake.",
        }

    async def _handle_initialized(
        self, session: ConnectionSession, params: Any
    ) -> None:
        """
        Handle MCP initialized notification - Complete the handshake

        Sent by client after receiving initialize response to confirm
        that capability negotiation is accepted and session is ready.
        """
        if not session.is_initialized():
            self.logger.warning(
                "Received 'initialized' notification but session not properly initialized",
                session_id=session.session_id,
            )
            return

        # Mark session as fully operational
        session.update_activity()

        # Log successful handshake completion
        self.logger.info(
            "MCP handshake completed successfully",
            session_id=session.session_id,
            client_name=session.client_info.name if session.client_info else "unknown",
            protocol_version=(
                session.client_info.protocol_version
                if session.client_info
                else "unknown"
            ),
            active_capabilities=(
                list(session.capabilities.keys()) if session.capabilities else []
            ),
            session_ready=True,
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

    async def _handle_ping(
        self, session: ConnectionSession, params: Any
    ) -> Dict[str, Any]:
        """Handle ping request for connection keepalive"""
        return {"status": "pong", "timestamp": datetime.utcnow().isoformat()}

    async def _handle_notification_cancelled(
        self, session: ConnectionSession, params: Any
    ) -> None:
        """Handle cancelled notification"""
        request_id = params.get("requestId") if params else None
        self.logger.info(
            "Request cancelled by client",
            session_id=session.session_id,
            cancelled_request_id=request_id,
        )
        # Implementation would cancel the specified request
        # For now, we just log it

    async def _handle_notification_progress(
        self, session: ConnectionSession, params: Any
    ) -> None:
        """Handle progress notification from client"""
        # This would typically be sent by the server to client, not vice versa
        # But we handle it for completeness
        self.logger.debug(
            "Progress notification from client",
            session_id=session.session_id,
            progress=params,
        )

    async def _handle_logging_set_level(
        self, session: ConnectionSession, params: Any
    ) -> Dict[str, Any]:
        """Handle logging level change request"""
        if not params or "level" not in params:
            raise ValueError("level parameter required")

        level = params["level"]
        valid_levels = [
            "debug",
            "info",
            "notice",
            "warning",
            "error",
            "critical",
            "alert",
            "emergency",
        ]

        if level not in valid_levels:
            raise ValueError(f"Invalid log level. Must be one of: {valid_levels}")

        # Update logging level for this session
        # (In a real implementation, you might want to update the logger configuration)
        self.logger.info(
            "Log level changed", session_id=session.session_id, new_level=level
        )

        return {"success": True}

    # Validation Handler Methods

    async def _handle_validate_request(
        self, session: ConnectionSession, params: Any
    ) -> Dict[str, Any]:
        """Handle request validation"""
        if not params or not isinstance(params, dict):
            raise ValueError("Validation parameters required")

        request_data = params.get("request")
        if not request_data:
            raise ValueError("Request data required for validation")

        # Validate the request structure
        validation_results = self.validator.validate_json_rpc_request(request_data)

        # Add method-specific validation if available
        method = request_data.get("method")
        if method == "initialize" and "params" in request_data:
            init_validation = self.validator.validate_mcp_initialize_params(
                request_data["params"]
            )
            validation_results.extend(init_validation)
        elif method == "tools/call" and "params" in request_data:
            tool_validation = self.validator.validate_mcp_tool_call_params(
                request_data["params"]
            )
            validation_results.extend(tool_validation)

        # Store validation results
        self.validator.validation_history.extend(validation_results)

        return {
            "validation_results": [r.to_dict() for r in validation_results],
            "is_valid": all(r.is_valid for r in validation_results),
            "error_count": len([r for r in validation_results if not r.is_valid]),
            "warning_count": len(
                [
                    r
                    for r in validation_results
                    if r.severity == ValidationSeverity.WARNING
                ]
            ),
        }

    async def _handle_validate_response(
        self, session: ConnectionSession, params: Any
    ) -> Dict[str, Any]:
        """Handle response validation"""
        if not params or not isinstance(params, dict):
            raise ValueError("Validation parameters required")

        response_data = params.get("response")
        if not response_data:
            raise ValueError("Response data required for validation")

        # Validate the response structure
        validation_results = self.validator.validate_json_rpc_response(response_data)

        # Store validation results
        self.validator.validation_history.extend(validation_results)

        return {
            "validation_results": [r.to_dict() for r in validation_results],
            "is_valid": all(r.is_valid for r in validation_results),
            "error_count": len([r for r in validation_results if not r.is_valid]),
            "warning_count": len(
                [
                    r
                    for r in validation_results
                    if r.severity == ValidationSeverity.WARNING
                ]
            ),
        }

    async def _handle_get_validation_summary(
        self, session: ConnectionSession, params: Any
    ) -> Dict[str, Any]:
        """Get validation statistics summary"""
        summary = self.validator.get_validation_summary()

        # Add recent validation history if requested
        include_history = params.get("include_history", False) if params else False
        if include_history:
            recent_count = params.get("recent_count", 10) if params else 10
            recent_history = (
                self.validator.validation_history[-recent_count:]
                if self.validator.validation_history
                else []
            )
            summary["recent_validations"] = [r.to_dict() for r in recent_history]

        return summary

    def validate_tool_call_params(
        self, method: str, params: Dict[str, Any]
    ) -> List[ValidationResult]:
        """Validate tool call parameters with method-specific validation"""
        results = []

        # General tool call validation
        if method == "tools/call":
            tool_validation = self.validator.validate_mcp_tool_call_params(params)
            results.extend(tool_validation)

        # Add any custom tool-specific validation here
        # This could be extended based on the specific tools being called

        return results

    # Streaming Operation Methods

    async def start_streaming_operation(
        self,
        session: ConnectionSession,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        websocket: Optional[WebSocket] = None,
    ) -> str:
        """
        Start a long-running streaming operation

        Args:
            session: Connection session
            method: Method name for the operation
            params: Operation parameters
            websocket: WebSocket connection for real-time updates

        Returns:
            Operation ID for tracking
        """
        operation_id = str(uuid.uuid4())

        # Create streaming operation
        operation = StreamingOperation(
            operation_id=operation_id,
            session_id=session.session_id,
            method=method,
            params=params,
            status=OperationStatus.PENDING,
        )

        self.streaming_operations[operation_id] = operation

        # Check if we have a streaming handler for this method
        if method in self.streaming_handlers:
            # Start the streaming operation as a background task
            operation.task = asyncio.create_task(
                self._execute_streaming_operation(operation, session, websocket)
            )
            operation.update_progress(0.0, "Operation started", OperationStatus.RUNNING)
        else:
            operation.update_progress(
                0.0,
                f"No streaming handler for method: {method}",
                OperationStatus.FAILED,
            )
            operation.error = f"Method '{method}' does not support streaming"

        self.logger.info(
            "Started streaming operation",
            operation_id=operation_id,
            session_id=session.session_id,
            method=method,
            status=operation.status.value,
        )

        return operation_id

    async def _execute_streaming_operation(
        self,
        operation: StreamingOperation,
        session: ConnectionSession,
        websocket: Optional[WebSocket] = None,
    ):
        """Execute a streaming operation with progress tracking"""
        try:
            handler = self.streaming_handlers[operation.method]

            # Execute the streaming handler
            async for progress_update in handler(
                session, operation.params or {}, operation.operation_id
            ):
                if operation.status == OperationStatus.CANCELLED:
                    break

                # Update operation progress
                if isinstance(progress_update, dict):
                    progress = progress_update.get("progress", operation.progress)
                    message = progress_update.get("message", operation.message)
                    status = progress_update.get("status", operation.status)
                    result = progress_update.get("result")

                    if isinstance(status, str):
                        status = OperationStatus(status)

                    operation.update_progress(progress, message, status)

                    if result is not None:
                        operation.result = result

                # Send progress notification via WebSocket if available
                if websocket:
                    await self._send_progress_notification(websocket, operation)

                # Check if operation is complete
                if operation.status in [
                    OperationStatus.COMPLETED,
                    OperationStatus.FAILED,
                ]:
                    break

            # Mark as completed if not already marked
            if operation.status == OperationStatus.RUNNING:
                operation.update_progress(
                    1.0, "Operation completed", OperationStatus.COMPLETED
                )

        except asyncio.CancelledError:
            operation.update_progress(
                operation.progress, "Operation cancelled", OperationStatus.CANCELLED
            )
            self.logger.info(f"Streaming operation cancelled: {operation.operation_id}")
        except Exception as e:
            operation.error = str(e)
            operation.update_progress(
                operation.progress,
                f"Operation failed: {str(e)}",
                OperationStatus.FAILED,
            )
            self.logger.error(
                f"Streaming operation failed",
                operation_id=operation.operation_id,
                error=str(e),
                exc_info=True,
            )
        finally:
            # Send final progress notification
            if websocket:
                await self._send_progress_notification(websocket, operation)

    async def _send_progress_notification(
        self, websocket: WebSocket, operation: StreamingOperation
    ):
        """Send progress notification via WebSocket"""
        try:
            notification = {
                "jsonrpc": "2.0",
                "method": "notifications/progress",
                "params": {
                    "progressToken": operation.operation_id,
                    "value": {
                        "kind": "progress",
                        "title": f"Operation: {operation.method}",
                        "message": operation.message,
                        "percentage": int(operation.progress * 100),
                        "status": operation.status.value,
                        "cancellable": True,
                    },
                },
            }

            await websocket.send_text(json.dumps(notification))

        except Exception as e:
            self.logger.error(f"Failed to send progress notification: {e}")

    def get_operation_status(self, operation_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a streaming operation"""
        operation = self.streaming_operations.get(operation_id)
        if operation:
            return operation.to_dict()
        return None

    async def cancel_operation(self, operation_id: str) -> bool:
        """Cancel a streaming operation"""
        operation = self.streaming_operations.get(operation_id)
        if not operation:
            return False

        if operation.task and not operation.task.done():
            operation.task.cancel()
            operation.update_progress(
                operation.progress, "Cancellation requested", OperationStatus.CANCELLED
            )

            self.logger.info(f"Cancelled streaming operation: {operation_id}")
            return True

        return False

    def cleanup_completed_operations(self, max_age_hours: int = 24):
        """Clean up completed operations older than specified age"""
        cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)

        operations_to_remove = []
        for operation_id, operation in self.streaming_operations.items():
            if (
                operation.status
                in [
                    OperationStatus.COMPLETED,
                    OperationStatus.FAILED,
                    OperationStatus.CANCELLED,
                ]
                and operation.updated_at < cutoff_time
            ):
                operations_to_remove.append(operation_id)

        for operation_id in operations_to_remove:
            del self.streaming_operations[operation_id]
            self.logger.debug(f"Cleaned up completed operation: {operation_id}")

    async def handle_streaming_request(
        self,
        session: ConnectionSession,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        websocket: Optional[WebSocket] = None,
    ) -> Dict[str, Any]:
        """
        Handle a request that should be processed as a streaming operation

        Returns operation ID and initial status
        """
        operation_id = await self.start_streaming_operation(
            session, method, params, websocket
        )
        operation = self.streaming_operations[operation_id]

        return {
            "operation_id": operation_id,
            "status": operation.status.value,
            "message": "Streaming operation started",
            "progress": operation.progress,
            "supports_cancellation": True,
        }

    # Enhanced Core Protocol Handlers

    async def _handle_operation_status(
        self, session: ConnectionSession, params: Any
    ) -> Dict[str, Any]:
        """Handle operation status request"""
        if not params or "operation_id" not in params:
            raise ValueError("operation_id parameter required")

        operation_id = params["operation_id"]
        status = self.get_operation_status(operation_id)

        if not status:
            raise ValueError(f"Operation '{operation_id}' not found")

        return status

    async def _handle_operation_cancel(
        self, session: ConnectionSession, params: Any
    ) -> Dict[str, Any]:
        """Handle operation cancellation request"""
        if not params or "operation_id" not in params:
            raise ValueError("operation_id parameter required")

        operation_id = params["operation_id"]
        cancelled = await self.cancel_operation(operation_id)

        return {
            "operation_id": operation_id,
            "cancelled": cancelled,
            "message": (
                "Operation cancelled"
                if cancelled
                else "Operation not found or already completed"
            ),
        }

    async def _handle_list_operations(
        self, session: ConnectionSession, params: Any
    ) -> Dict[str, Any]:
        """Handle list operations request"""
        # Filter operations for this session
        session_operations = [
            op.to_dict()
            for op in self.streaming_operations.values()
            if op.session_id == session.session_id
        ]

        return {
            "operations": session_operations,
            "total_count": len(session_operations),
            "active_count": len(
                [op for op in session_operations if op["status"] == "running"]
            ),
            "timestamp": datetime.utcnow().isoformat(),
        }

    # Capability Negotiation Methods

    def _negotiate_capabilities(
        self, client_capabilities: Dict[str, Any], session: ConnectionSession
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
                    server_tools.get("supports_progress", False)
                    and client_tools.get(
                        "supports_progress", True
                    )  # Default to True for clients
                ),
                "available_tools": [
                    "list_contexts",
                    "switch_context",
                    "get_context_info",
                    "query",
                    "find_concept",
                    "get_relationships",
                    "search_docs",
                    "search_documents",
                    "get_summary",
                    "explore_graph",
                    "clear_cache",
                    "help",
                ],
            }

        # Resources capability negotiation
        if MCPCapability.RESOURCES in self.server_capabilities:
            client_resources = client_capabilities.get("resources", {})
            server_resources = self.server_capabilities[MCPCapability.RESOURCES]

            negotiated[MCPCapability.RESOURCES] = {
                "subscribe": (
                    server_resources.get("subscribe", False)
                    and client_resources.get("subscribe", True)
                ),
                "listChanged": server_resources.get("listChanged", False),
                "available_resources": [
                    "document_content",
                    "processed_chunks",
                    "knowledge_graph",
                ],
            }

        # Prompts capability negotiation
        if MCPCapability.PROMPTS in self.server_capabilities:
            client_prompts = client_capabilities.get("prompts", {})
            server_prompts = self.server_capabilities[MCPCapability.PROMPTS]

            negotiated[MCPCapability.PROMPTS] = {
                "listChanged": server_prompts.get("listChanged", False),
                "available_prompts": [
                    "documentation_search",
                    "architecture_discovery",
                    "best_practices",
                    "code_review",
                    "user_story_context_builder",
                ],
            }

        # Logging capability negotiation
        if MCPCapability.LOGGING in self.server_capabilities:
            client_logging = client_capabilities.get("logging", {})
            server_logging = self.server_capabilities[MCPCapability.LOGGING]

            # Client can request different log level
            requested_level = client_logging.get("level", "info")
            valid_levels = [
                "debug",
                "info",
                "notice",
                "warning",
                "error",
                "critical",
                "alert",
                "emergency",
            ]

            negotiated[MCPCapability.LOGGING] = {
                "level": requested_level if requested_level in valid_levels else "info",
                "supports_level_change": True,
            }

        # Experimental sampling (if requested by client)
        if (
            MCPCapability.EXPERIMENTAL_SAMPLING in client_capabilities
            and MCPCapability.EXPERIMENTAL_SAMPLING in self.server_capabilities
        ):
            negotiated[MCPCapability.EXPERIMENTAL_SAMPLING] = {
                "supports_sampling": False  # Not implemented yet
            }

        self.logger.debug(
            "Capability negotiation completed",
            session_id=session.session_id,
            client_requested=list(client_capabilities.keys()),
            server_available=list(self.server_capabilities.keys()),
            negotiated=list(negotiated.keys()),
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
            "progress_updates": capabilities.get(MCPCapability.TOOLS, {}).get(
                "supports_progress", False
            ),
            "resource_subscriptions": capabilities.get(MCPCapability.RESOURCES, {}).get(
                "subscribe", False
            ),
            "prompt_changes": capabilities.get(MCPCapability.PROMPTS, {}).get(
                "listChanged", False
            ),
        }

    def _validate_capability_request(
        self, session: ConnectionSession, required_capability: str
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
        change_type: str = "updated",
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
                "timestamp": datetime.utcnow().isoformat(),
            },
        }

        # In a real implementation, you would send this to the specific session
        # For now, we log it
        self.logger.info(
            "Capability change notification",
            session_id=session.session_id,
            capability_type=capability_type,
            change_type=change_type,
        )

    def _validate_method_capability(
        self, session: ConnectionSession, method: str
    ) -> bool:
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
            "initialize",
            "initialized",
            "ping",
            "notifications/cancelled",
            "notifications/progress",
            "logging/setLevel",
        ]

        if method in core_methods:
            return True

        # Tools methods require tools capability
        tools_methods = [
            "tools/list",
            "tools/call",
            # LightRAG-specific tool methods that will be implemented
            "list_contexts",
            "switch_context",
            "get_context_info",
            "query",
            "find_concept",
            "get_relationships",
            "search_docs",
            "search_documents",
            "get_summary",
            "explore_graph",
            "clear_cache",
            "help",
        ]

        if method in tools_methods:
            return self._validate_capability_request(session, "tools")

        # Resources methods require resources capability
        resources_methods = [
            "resources/list",
            "resources/read",
            "resources/subscribe",
            "resources/unsubscribe",
            # LightRAG-specific resource methods that will be implemented
            "get_full_document",
            "get_processed_chunks",
        ]

        if method in resources_methods:
            return self._validate_capability_request(session, "resources")

        # Prompts methods require prompts capability
        prompts_methods = [
            "prompts/list",
            "prompts/get",
            # LightRAG-specific prompt methods that will be implemented
            "get_prompt_template",
            "render_prompt",
        ]

        if method in prompts_methods:
            return self._validate_capability_request(session, "prompts")

        # Unknown methods are allowed by default (for extensibility)
        self.logger.debug(
            "Unknown method - allowing by default",
            session_id=session.session_id,
            method=method,
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
            "tools/list",
            "tools/call",
            "list_contexts",
            "switch_context",
            "get_context_info",
            "query",
            "find_concept",
            "get_relationships",
            "search_docs",
            "search_documents",
            "get_summary",
            "explore_graph",
            "clear_cache",
            "help",
        ]

        resources_methods = [
            "resources/list",
            "resources/read",
            "resources/subscribe",
            "resources/unsubscribe",
            "get_full_document",
            "get_processed_chunks",
        ]

        prompts_methods = [
            "prompts/list",
            "prompts/get",
            "get_prompt_template",
            "render_prompt",
        ]

        if method in tools_methods:
            return "tools"
        elif method in resources_methods:
            return "resources"
        elif method in prompts_methods:
            return "prompts"
        else:
            return "unknown"

    # Connection Lifecycle Management Methods

    async def create_session(
        self,
        session_id: str,
        websocket: Optional[WebSocket] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ConnectionSession:
        """
        Create a new connection session with proper initialization

        Args:
            session_id: Unique session identifier
            websocket: WebSocket connection if applicable
            metadata: Additional connection metadata

        Returns:
            Newly created ConnectionSession
        """
        session = ConnectionSession(
            session_id=session_id,
            websocket=websocket,
            connection_metadata=metadata or {},
        )

        # Update state to connected
        session.update_state(ConnectionState.CONNECTED, "Session created")

        # Store session
        self.sessions[session_id] = session

        self.logger.info(
            "Created new session",
            session_id=session_id,
            state=session.state.value,
            has_websocket=websocket is not None,
        )

        return session

    async def initialize_session(
        self,
        session: ConnectionSession,
        client_info: MCPClientInfo,
        capabilities: Dict[str, Any],
    ) -> bool:
        """
        Initialize a session with client information and capabilities

        Args:
            session: Session to initialize
            client_info: Client information
            capabilities: Negotiated capabilities

        Returns:
            True if initialization successful
        """
        try:
            # Update session state
            session.update_state(
                ConnectionState.INITIALIZING, "Starting initialization"
            )

            # Set client info and capabilities
            session.client_info = client_info
            session.capabilities = self._create_capability_flags(capabilities)

            # Create server info
            session.server_info = MCPServerInfo(capabilities=self.server_capabilities)

            # Mark as authenticated (in real implementation, this would involve actual auth)
            session.authenticated = True

            # Update state to initialized
            session.update_state(
                ConnectionState.INITIALIZED, "Initialization completed"
            )

            self.logger.info(
                "Session initialized successfully",
                session_id=session.session_id,
                client_name=client_info.name,
                client_version=client_info.version,
                capabilities=list(session.capabilities.keys()),
            )

            return True

        except Exception as e:
            session.update_state(
                ConnectionState.ERROR, f"Initialization failed: {str(e)}"
            )
            session.record_error(f"Initialization error: {str(e)}")

            self.logger.error(
                "Session initialization failed",
                session_id=session.session_id,
                error=str(e),
                exc_info=True,
            )

            return False

    async def activate_session(self, session: ConnectionSession) -> bool:
        """
        Activate an initialized session for normal operations

        Args:
            session: Session to activate

        Returns:
            True if activation successful
        """
        if not session.is_initialized():
            self.logger.warning(
                "Cannot activate uninitialized session",
                session_id=session.session_id,
                current_state=session.state.value,
            )
            return False

        session.update_state(ConnectionState.ACTIVE, "Session activated")

        self.logger.info(
            "Session activated",
            session_id=session.session_id,
            client_name=session.client_info.name if session.client_info else "unknown",
        )

        return True

    async def disconnect_session(
        self, session_id: str, reason: str = "Normal disconnect", graceful: bool = True
    ) -> bool:
        """
        Disconnect a session with proper cleanup

        Args:
            session_id: Session to disconnect
            reason: Reason for disconnection
            graceful: Whether to perform graceful shutdown

        Returns:
            True if disconnect successful
        """
        session = self.sessions.get(session_id)
        if not session:
            self.logger.warning(
                f"Attempted to disconnect non-existent session: {session_id}"
            )
            return False

        try:
            # Update state to disconnecting
            session.update_state(ConnectionState.DISCONNECTING, reason)

            if graceful:
                # Cancel any active streaming operations for this session
                session_operations = [
                    op
                    for op in self.streaming_operations.values()
                    if op.session_id == session_id
                ]

                for operation in session_operations:
                    if operation.status == OperationStatus.RUNNING:
                        await self.cancel_operation(operation.operation_id)

                # Close WebSocket connection if present
                if session.websocket:
                    try:
                        await session.websocket.close(code=1000, reason=reason)
                    except Exception as e:
                        self.logger.warning(f"Error closing WebSocket: {e}")

            # Update final state
            session.update_state(ConnectionState.DISCONNECTED, reason)

            self.logger.info(
                "Session disconnected",
                session_id=session_id,
                reason=reason,
                graceful=graceful,
                session_duration=str(session.get_session_duration()),
            )

            return True

        except Exception as e:
            session.update_state(ConnectionState.ERROR, f"Disconnect error: {str(e)}")
            session.record_error(f"Disconnect error: {str(e)}")

            self.logger.error(
                "Error during session disconnect",
                session_id=session_id,
                error=str(e),
                exc_info=True,
            )

            return False

    async def cleanup_session(self, session_id: str) -> bool:
        """
        Clean up and remove a session from memory

        Args:
            session_id: Session to cleanup

        Returns:
            True if cleanup successful
        """
        session = self.sessions.get(session_id)
        if not session:
            return False

        if not session.can_cleanup():
            self.logger.warning(
                "Attempted to cleanup active session",
                session_id=session_id,
                current_state=session.state.value,
            )
            return False

        try:
            # Remove from sessions
            del self.sessions[session_id]

            # Clean up any remaining streaming operations
            operations_to_remove = [
                op_id
                for op_id, op in self.streaming_operations.items()
                if op.session_id == session_id
            ]

            for op_id in operations_to_remove:
                del self.streaming_operations[op_id]

            self.logger.info(
                "Session cleaned up",
                session_id=session_id,
                operations_cleaned=len(operations_to_remove),
            )

            return True

        except Exception as e:
            self.logger.error(
                "Error during session cleanup",
                session_id=session_id,
                error=str(e),
                exc_info=True,
            )

            return False

    async def cleanup_stale_sessions(
        self, idle_threshold_minutes: int = 30, stale_threshold_hours: int = 24
    ) -> int:
        """
        Clean up idle and stale sessions

        Args:
            idle_threshold_minutes: Minutes of inactivity before marking as idle
            stale_threshold_hours: Hours before considering session stale

        Returns:
            Number of sessions cleaned up
        """
        cleaned_count = 0
        sessions_to_cleanup = []

        for session_id, session in self.sessions.items():
            # Mark idle sessions
            if session.is_active() and session.is_idle(idle_threshold_minutes):
                session.update_state(ConnectionState.IDLE, "Session idle")

            # Mark stale sessions for cleanup
            if session.is_stale(stale_threshold_hours):
                sessions_to_cleanup.append(session_id)

            # Mark disconnected sessions for cleanup
            elif session.state == ConnectionState.DISCONNECTED:
                sessions_to_cleanup.append(session_id)

        # Perform cleanup
        for session_id in sessions_to_cleanup:
            if await self.cleanup_session(session_id):
                cleaned_count += 1

        if cleaned_count > 0:
            self.logger.info(f"Cleaned up {cleaned_count} stale sessions")

        return cleaned_count

    def get_session_statistics(self) -> Dict[str, Any]:
        """Get comprehensive session statistics"""
        total_sessions = len(self.sessions)

        state_counts = {}
        for state in ConnectionState:
            state_counts[state.value] = 0

        total_messages = 0
        total_operations = 0
        total_errors = 0

        for session in self.sessions.values():
            state_counts[session.state.value] += 1
            total_messages += session.resource_usage.get(
                "messages_sent", 0
            ) + session.resource_usage.get("messages_received", 0)
            total_operations += session.resource_usage.get("operations_started", 0)
            total_errors += session.resource_usage.get("errors_encountered", 0)

        return {
            "total_sessions": total_sessions,
            "state_distribution": state_counts,
            "active_sessions": state_counts.get("active", 0)
            + state_counts.get("idle", 0),
            "total_messages": total_messages,
            "total_operations": total_operations,
            "total_errors": total_errors,
            "active_streaming_operations": len(self.streaming_operations),
            "timestamp": datetime.utcnow().isoformat(),
        }

    # Enhanced Utility Methods

    def get_session(self, session_id: str) -> Optional[ConnectionSession]:
        """Get session by ID"""
        return self.sessions.get(session_id)

    def get_active_sessions(self) -> List[ConnectionSession]:
        """Get list of all active sessions"""
        return [session for session in self.sessions.values() if session.is_active()]

    def get_all_sessions(self) -> List[ConnectionSession]:
        """Get list of all sessions regardless of state"""
        return list(self.sessions.values())

    def get_session_count(self) -> int:
        """Get count of all sessions"""
        return len(self.sessions)

    def get_active_session_count(self) -> int:
        """Get count of active sessions only"""
        return len(self.get_active_sessions())

    async def broadcast_notification(
        self, method: str, params: Any, active_only: bool = True
    ):
        """
        Broadcast notification to connected clients

        Args:
            method: Notification method
            params: Notification parameters
            active_only: Only send to active sessions if True
        """
        notification = {"jsonrpc": "2.0", "method": method, "params": params}
        message = json.dumps(notification)

        target_sessions = (
            self.get_active_sessions() if active_only else self.get_all_sessions()
        )
        sent_count = 0

        for session in target_sessions:
            if session.websocket:
                try:
                    await session.websocket.send_text(message)
                    session.record_message("sent", len(message))
                    sent_count += 1
                except Exception as e:
                    session.record_error(f"Broadcast error: {str(e)}")
                    self.logger.warning(
                        f"Failed to send notification to session {session.session_id}: {e}"
                    )

        self.logger.info(
            "Broadcast notification sent",
            method=method,
            target_sessions=len(target_sessions),
            sent_count=sent_count,
        )

    async def send_session_notification(
        self, session_id: str, method: str, params: Any
    ) -> bool:
        """
        Send notification to a specific session

        Args:
            session_id: Target session ID
            method: Notification method
            params: Notification parameters

        Returns:
            True if notification sent successfully
        """
        session = self.get_session(session_id)
        if not session or not session.websocket:
            return False

        notification = {"jsonrpc": "2.0", "method": method, "params": params}
        message = json.dumps(notification)

        try:
            await session.websocket.send_text(message)
            session.record_message("sent", len(message))
            return True
        except Exception as e:
            session.record_error(f"Notification error: {str(e)}")
            self.logger.warning(
                f"Failed to send notification to session {session_id}: {e}"
            )
            return False

    async def shutdown(self):
        """Gracefully shutdown the protocol server with proper cleanup"""
        self.logger.info("Shutting down MCP protocol server")

        # Disconnect all sessions gracefully
        disconnect_tasks = []
        for session_id in list(self.sessions.keys()):
            task = asyncio.create_task(
                self.disconnect_session(session_id, "Server shutdown", graceful=True)
            )
            disconnect_tasks.append(task)

        if disconnect_tasks:
            await asyncio.gather(*disconnect_tasks, return_exceptions=True)

        # Cancel all streaming operations
        cancel_tasks = []
        for operation_id in list(self.streaming_operations.keys()):
            task = asyncio.create_task(self.cancel_operation(operation_id))
            cancel_tasks.append(task)

        if cancel_tasks:
            await asyncio.gather(*cancel_tasks, return_exceptions=True)

        # Clear all data structures
        self.sessions.clear()
        self.streaming_operations.clear()

        self.logger.info("MCP protocol server shutdown complete")
