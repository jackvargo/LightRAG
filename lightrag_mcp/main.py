"""
LightRAG MCP Server - Main FastAPI Application

This module provides the main FastAPI application for the LightRAG MCP server,
including basic health checks, CORS configuration, WebSocket and SSE support,
and application lifecycle management.
"""

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional
from urllib.parse import parse_qs

import redis.asyncio as redis
import uvicorn
from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from redis.exceptions import ConnectionError as RedisConnectionError

from .auth import (
    FastAPIAuthenticationMiddleware,
    get_optional_user,
    require_authenticated_user,
)
from .config import Settings, get_settings
from .logging_utils import (
    LoggingMiddleware,
    get_logger,
    performance_monitor,
    security_logger,
    setup_logging,
)
from .services.lightrag_client import LightRAGClient, LightRAGError, get_lightrag_client

# Get settings
settings = get_settings()

# Setup comprehensive logging
setup_logging()
logger = get_logger(__name__)

# Application metadata
APP_NAME = settings.app_name
APP_VERSION = settings.app_version
APP_DESCRIPTION = "Model Context Protocol server for LightRAG knowledge graphs"

# Global service instances
redis_client: redis.Redis = None
lightrag_client: LightRAGClient = None


# WebSocket connection manager
class WebSocketManager:
    """Manages WebSocket connections for real-time communication."""

    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self.connection_metadata: Dict[WebSocket, Dict[str, Any]] = {}

    async def connect(
        self, websocket: WebSocket, client_id: str, metadata: Dict[str, Any] = None
    ):
        """Accept a WebSocket connection and register it."""
        await websocket.accept()

        if client_id not in self.active_connections:
            self.active_connections[client_id] = []

        self.active_connections[client_id].append(websocket)
        self.connection_metadata[websocket] = {
            "client_id": client_id,
            "connected_at": datetime.now(timezone.utc),
            "metadata": metadata or {},
        }

        logger.info(f"WebSocket connection established for client: {client_id}")

    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection."""
        if websocket in self.connection_metadata:
            client_id = self.connection_metadata[websocket]["client_id"]

            if client_id in self.active_connections:
                self.active_connections[client_id].remove(websocket)

                if not self.active_connections[client_id]:
                    del self.active_connections[client_id]

            del self.connection_metadata[websocket]
            logger.info(f"WebSocket connection closed for client: {client_id}")

    async def send_to_client(self, client_id: str, message: Dict[str, Any]):
        """Send a message to all connections for a specific client."""
        if client_id in self.active_connections:
            dead_connections = []

            for websocket in self.active_connections[client_id]:
                try:
                    await websocket.send_text(json.dumps(message))
                except Exception as e:
                    logger.warning(f"Failed to send message to client {client_id}: {e}")
                    dead_connections.append(websocket)

            # Clean up dead connections
            for websocket in dead_connections:
                self.disconnect(websocket)

    async def broadcast(self, message: Dict[str, Any], exclude_client: str = None):
        """Broadcast a message to all connected clients."""
        for client_id in list(self.active_connections.keys()):
            if exclude_client and client_id == exclude_client:
                continue
            await self.send_to_client(client_id, message)

    def get_connection_stats(self) -> Dict[str, Any]:
        """Get statistics about active connections."""
        total_connections = sum(
            len(connections) for connections in self.active_connections.values()
        )
        return {
            "total_connections": total_connections,
            "unique_clients": len(self.active_connections),
            "clients": list(self.active_connections.keys()),
        }


# Global WebSocket manager
websocket_manager = WebSocketManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager for startup and shutdown events.
    """
    global redis_client, lightrag_client

    # Startup
    logger.info(f"Starting {APP_NAME} v{APP_VERSION}")

    try:
        # Initialize Redis client
        redis_client = redis.from_url(
            settings.redis.url,
            password=settings.redis.password,
            db=settings.redis.db,
            max_connections=settings.redis.max_connections,
            decode_responses=True,
        )
        logger.info("Redis client initialized")

        # Initialize LightRAG client
        lightrag_client = get_lightrag_client(settings)
        logger.info("LightRAG client initialized")

        # Test connections
        await _test_redis_connection()
        await _test_lightrag_connection()

        logger.info(f"{APP_NAME} startup completed successfully")

    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")
        # Continue startup even if some services fail

    yield

    # Shutdown
    logger.info(f"Shutting down {APP_NAME}")

    try:
        # Cleanup Redis client
        if redis_client:
            await redis_client.close()
            logger.info("Redis client closed")

        # Cleanup LightRAG client
        if lightrag_client:
            await lightrag_client.close()
            logger.info("LightRAG client closed")

    except Exception as e:
        logger.error(f"Error during shutdown: {e}")

    logger.info(f"{APP_NAME} shutdown completed")


async def _test_redis_connection():
    """Test Redis connection."""
    try:
        if redis_client:
            await redis_client.ping()
            logger.info("Redis connection test successful")
    except Exception as e:
        logger.warning(f"Redis connection test failed: {e}")


async def _test_lightrag_connection():
    """Test LightRAG API connection."""
    try:
        if lightrag_client:
            await lightrag_client.health_check()
            logger.info("LightRAG API connection test successful")
    except Exception as e:
        logger.warning(f"LightRAG API connection test failed: {e}")


# Create FastAPI application
app = FastAPI(
    title=APP_NAME, version=APP_VERSION, description=APP_DESCRIPTION, lifespan=lifespan
)

# Add logging middleware first
app.add_middleware(LoggingMiddleware)
logger.info("Logging middleware enabled with request tracing")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add authentication middleware (only if not in NONE mode)
if settings.auth.mode.value != "none":
    app.add_middleware(FastAPIAuthenticationMiddleware, settings=settings)
    logger.info(f"Authentication middleware enabled (mode: {settings.auth.mode.value})")


@app.get("/", response_model=Dict[str, Any])
async def root():
    """
    Root endpoint providing basic server information.
    """
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "description": APP_DESCRIPTION,
        "status": "running",
    }


async def _check_redis_health() -> Dict[str, Any]:
    """Check Redis health status."""
    try:
        if not redis_client:
            return {"status": "unavailable", "error": "Redis client not initialized"}

        start_time = datetime.now()
        await redis_client.ping()
        response_time = (datetime.now() - start_time).total_seconds() * 1000

        # Test basic operations
        test_key = "health_check_test"
        await redis_client.set(test_key, "test_value", ex=10)
        test_value = await redis_client.get(test_key)
        await redis_client.delete(test_key)

        if test_value != "test_value":
            return {"status": "degraded", "error": "Redis operations failing"}

        return {
            "status": "healthy",
            "response_time_ms": round(response_time, 2),
            "operations": "functional",
        }

    except RedisConnectionError:
        return {"status": "unhealthy", "error": "Redis connection failed"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


async def _check_lightrag_health() -> Dict[str, Any]:
    """Check LightRAG API health status."""
    try:
        if not lightrag_client:
            return {"status": "unavailable", "error": "LightRAG client not initialized"}

        start_time = datetime.now()
        health_data = await lightrag_client.health_check()
        response_time = (datetime.now() - start_time).total_seconds() * 1000

        return {
            "status": "healthy",
            "response_time_ms": round(response_time, 2),
            "api_status": health_data.get("status", "unknown"),
            "api_version": health_data.get("version", "unknown"),
        }

    except LightRAGError as e:
        return {"status": "unhealthy", "error": f"LightRAG API error: {e}"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


async def _check_auth_service_health() -> Dict[str, Any]:
    """Check authentication service health."""
    try:
        # Test JWT token creation (basic functionality)
        from .auth import create_access_token

        test_token = create_access_token({"sub": "health_check"})

        if not test_token:
            return {"status": "unhealthy", "error": "Cannot create JWT tokens"}

        # Test password hashing
        from .auth import get_password_hash, verify_password

        test_password = "test_password_123"
        hashed = get_password_hash(test_password)
        verified = verify_password(test_password, hashed)

        if not verified:
            return {
                "status": "unhealthy",
                "error": "Password hashing/verification failed",
            }

        return {
            "status": "healthy",
            "jwt_generation": "functional",
            "password_hashing": "functional",
        }

    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


@app.get("/health", response_model=Dict[str, Any])
async def health_check():
    """
    Comprehensive health check endpoint for monitoring and load balancers.
    """
    start_time = datetime.now(timezone.utc)

    try:
        # Check all dependencies
        redis_health = await _check_redis_health()
        lightrag_health = await _check_lightrag_health()
        auth_health = await _check_auth_service_health()

        # Determine overall status
        all_dependencies = [redis_health, lightrag_health, auth_health]

        if all(dep["status"] == "healthy" for dep in all_dependencies):
            overall_status = "healthy"
            status_code = 200
        elif any(dep["status"] == "unhealthy" for dep in all_dependencies):
            overall_status = "unhealthy"
            status_code = 503
        else:
            overall_status = "degraded"
            status_code = 200

        check_duration = (datetime.now(timezone.utc) - start_time).total_seconds()

        response_data = {
            "status": overall_status,
            "version": APP_VERSION,
            "timestamp": start_time.isoformat(),
            "check_duration_seconds": round(check_duration, 3),
            "environment": settings.environment.value,
            "dependencies": {
                "redis": redis_health,
                "lightrag_api": lightrag_health,
                "auth_service": auth_health,
            },
            "system_info": {
                "uptime": "calculated_at_runtime",  # TODO: Implement uptime tracking
                "memory_usage": "not_implemented",  # TODO: Add memory monitoring
                "cpu_usage": "not_implemented",  # TODO: Add CPU monitoring
            },
        }

        if overall_status == "unhealthy":
            raise HTTPException(status_code=status_code, detail=response_data)

        return response_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        error_response = {
            "status": "error",
            "version": APP_VERSION,
            "timestamp": start_time.isoformat(),
            "error": str(e),
            "message": "Health check system failure",
        }
        raise HTTPException(status_code=503, detail=error_response)


@app.post("/auth/login", response_model=Dict[str, Any])
async def login_endpoint(username: str, password: str, request: Request):
    """
    OAuth 2.1 login endpoint for obtaining access tokens.
    """
    try:
        from .auth import login_for_access_token

        token = await login_for_access_token(username, password, request)
        return token.dict()
    except Exception as e:
        logger.error(f"Login failed for user {username}: {e}")
        raise HTTPException(status_code=401, detail="Invalid credentials")


@app.post("/auth/refresh", response_model=Dict[str, Any])
async def refresh_token_endpoint(refresh_token: str):
    """
    OAuth 2.1 token refresh endpoint.
    """
    try:
        from .auth import refresh_access_token

        new_token = await refresh_access_token(refresh_token)
        return new_token.dict()
    except Exception as e:
        logger.error(f"Token refresh failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid refresh token")


@app.get("/auth/me", response_model=Dict[str, Any])
async def get_current_user_info(user: Dict = Depends(require_authenticated_user)):
    """
    Get current authenticated user information.
    """
    return {
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "scopes": user.scopes,
        "disabled": user.disabled,
    }


@app.get("/auth/discovery", response_model=Dict[str, Any])
async def auth_discovery():
    """
    OAuth 2.1 discovery endpoint for authentication configuration.
    """
    return {
        "issuer": f"http://{settings.server.host}:{settings.server.port}",
        "authorization_endpoint": "/auth/authorize",  # TODO: Implement if needed
        "token_endpoint": "/auth/login",
        "refresh_endpoint": "/auth/refresh",
        "userinfo_endpoint": "/auth/me",
        "jwks_uri": "/auth/jwks",  # TODO: Implement if needed
        "scopes_supported": ["read", "write", "admin"],
        "response_types_supported": ["token"],
        "grant_types_supported": ["password", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["client_secret_post"],
        "auth_modes_supported": ["oauth", "api_key", "none"],
        "current_auth_mode": settings.auth.mode.value,
    }


@app.get("/discovery", response_model=Dict[str, Any])
async def mcp_discovery():
    """
    MCP discovery endpoint for client capability negotiation.
    """
    return {
        "protocol_version": settings.mcp.protocol_version,
        "server_info": {
            "name": APP_NAME,
            "version": APP_VERSION,
            "description": APP_DESCRIPTION,
            "environment": settings.environment.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "capabilities": {
            "tools": settings.mcp.enable_tools,
            "resources": settings.mcp.enable_resources,
            "prompts": settings.mcp.enable_prompts,
            "logging": True,
            "completion": False,  # Not implemented yet
            "sampling": False,  # Not implemented yet
        },
        "supported_transports": ["http", "websocket", "sse"],
        "transport_details": {
            "websocket": {
                "endpoints": ["/mcp", "/mcp/{operation}"],
                "supported_operations": ["query", "documents", "graph"],
                "features": ["real_time_messaging", "subscriptions", "heartbeat"],
            },
            "sse": {
                "endpoints": ["/mcp/stream", "/mcp/stream/{operation}"],
                "features": ["streaming_responses", "progress_updates", "heartbeat"],
            },
        },
        "authentication": {
            "supported_methods": ["oauth2", "bearer_token"],
            "oauth_discovery": "/auth/discovery",  # TODO: Implement OAuth discovery
            "token_endpoint": "/auth/token",  # TODO: Implement token endpoint
        },
        "rate_limiting": {
            "enabled": True,
            "requests_per_minute": settings.mcp.rate_limit_per_minute,
            "burst_limit": settings.mcp.rate_limit_per_minute * 2,
        },
        "features": {
            "context_switching": True,
            "document_management": True,
            "knowledge_graph_queries": True,
            "relationship_exploration": True,
            "semantic_search": True,
            "real_time_updates": True,
            "tool_discovery": True,
            "tool_metadata": True,
            "tool_categories": True,
            "streaming_operations": True,
            "progress_tracking": True,
            "operation_cancellation": True,
            "session_management": True,
            "connection_lifecycle": True,
            "session_statistics": True,
            "automatic_cleanup": True,
        },
        "limits": {
            "max_request_size": settings.mcp.max_request_size,
            "request_timeout": settings.mcp.request_timeout,
            "max_concurrent_requests": 10,  # TODO: Make configurable
        },
        "health_check": {"endpoint": "/health", "interval_seconds": 30},
        "tool_endpoints": {
            "list": "/tools/list",
            "call": "/tools/call",
            "metadata": "/tools/metadata",
            "categories": "/tools/categories",
            "schema": "/tools/{tool_name}/schema",
        },
        "streaming_endpoints": {
            "start": "/operations/start",
            "status": "/operations/{operation_id}/status",
            "cancel": "/operations/{operation_id}/cancel",
            "stream": "/operations/{operation_id}/stream",
            "list": "/operations",
        },
        "session_endpoints": {
            "list": "/sessions",
            "details": "/sessions/{session_id}",
            "disconnect": "/sessions/{session_id}/disconnect",
            "cleanup": "/sessions/cleanup",
            "statistics": "/sessions/statistics",
            "heartbeat": "/sessions/{session_id}/heartbeat",
        },
        "validation_endpoints": {
            "validate_request": "/validation/request",
            "validate_response": "/validation/response",
            "validation_summary": "/validation/summary",
            "protocol_info": "/validation/protocol",
        },
    }


@app.get("/protected", response_model=Dict[str, Any])
async def protected_endpoint(user: Dict = Depends(require_authenticated_user)):
    """
    Example protected endpoint that requires authentication.
    """
    return {
        "message": "This is a protected endpoint",
        "authenticated_user": user.username,
        "user_scopes": user.scopes,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/admin-only", response_model=Dict[str, Any])
async def admin_only_endpoint():
    """
    Example admin-only endpoint (will be protected by middleware).
    """
    return {
        "message": "This endpoint requires admin privileges",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "admin_features": [
            "User management",
            "System configuration",
            "Advanced monitoring",
        ],
    }


@app.get("/optional-auth", response_model=Dict[str, Any])
async def optional_auth_endpoint(user: Optional[Dict] = Depends(get_optional_user)):
    """
    Example endpoint with optional authentication.
    """
    if user:
        return {
            "message": "Hello authenticated user!",
            "user": user.username,
            "scopes": user.scopes,
        }
    else:
        return {
            "message": "Hello anonymous user!",
            "note": "You can access more features by authenticating",
        }


# WebSocket and SSE endpoints for real-time communication
@app.websocket("/mcp")
async def mcp_websocket_endpoint(websocket: WebSocket):
    """
    Main MCP WebSocket endpoint for real-time protocol communication.
    """
    client_id = f"ws_{datetime.now().timestamp()}"

    try:
        # Extract client information from query parameters
        query_params = parse_qs(
            str(websocket.url).split("?")[1] if "?" in str(websocket.url) else ""
        )
        client_info = {
            "user_agent": websocket.headers.get("user-agent", "unknown"),
            "client_name": query_params.get("client", ["unknown"])[0],
            "protocol_version": query_params.get("version", ["1.0"])[0],
        }

        await websocket_manager.connect(websocket, client_id, client_info)

        # Send welcome message
        welcome_message = {
            "type": "welcome",
            "client_id": client_id,
            "server_info": {
                "name": APP_NAME,
                "version": APP_VERSION,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            "capabilities": {
                "tools": settings.mcp.enable_tools,
                "resources": settings.mcp.enable_resources,
                "prompts": settings.mcp.enable_prompts,
                "real_time": True,
            },
        }
        await websocket.send_text(json.dumps(welcome_message))

        # Message handling loop
        while True:
            try:
                data = await websocket.receive_text()
                message = json.loads(data)

                # Handle different message types
                response = await handle_websocket_message(message, client_id)
                if response:
                    await websocket.send_text(json.dumps(response))

            except json.JSONDecodeError:
                error_response = {
                    "type": "error",
                    "error": "invalid_json",
                    "message": "Invalid JSON in message",
                }
                await websocket.send_text(json.dumps(error_response))

    except WebSocketDisconnect:
        logger.info(f"WebSocket client {client_id} disconnected")
    except Exception as e:
        logger.error(f"WebSocket error for client {client_id}: {e}")
    finally:
        websocket_manager.disconnect(websocket)


@app.websocket("/mcp/{path:path}")
async def mcp_websocket_path_endpoint(websocket: WebSocket, path: str):
    """
    Path-based WebSocket routing for different MCP operations.
    """
    client_id = f"ws_{path}_{datetime.now().timestamp()}"

    try:
        await websocket_manager.connect(websocket, client_id, {"path": path})

        # Send path-specific welcome message
        welcome_message = {
            "type": "welcome",
            "client_id": client_id,
            "path": path,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await websocket.send_text(json.dumps(welcome_message))

        # Handle path-specific logic
        if path == "query":
            await handle_query_websocket(websocket, client_id)
        elif path == "documents":
            await handle_documents_websocket(websocket, client_id)
        elif path == "graph":
            await handle_graph_websocket(websocket, client_id)
        else:
            # Default message handling
            while True:
                data = await websocket.receive_text()
                message = json.loads(data)
                response = await handle_websocket_message(message, client_id)
                if response:
                    await websocket.send_text(json.dumps(response))

    except WebSocketDisconnect:
        logger.info(f"WebSocket client {client_id} disconnected from path: {path}")
    except Exception as e:
        logger.error(f"WebSocket error for client {client_id} on path {path}: {e}")
    finally:
        websocket_manager.disconnect(websocket)


async def handle_websocket_message(
    message: Dict[str, Any], client_id: str
) -> Optional[Dict[str, Any]]:
    """Handle incoming WebSocket messages."""
    try:
        message_type = message.get("type")

        if message_type == "ping":
            return {"type": "pong", "timestamp": datetime.now(timezone.utc).isoformat()}
        elif message_type == "subscribe":
            topic = message.get("topic")
            logger.info(f"Client {client_id} subscribed to topic: {topic}")
            return {
                "type": "subscription_confirmed",
                "topic": topic,
                "client_id": client_id,
            }
        elif message_type == "unsubscribe":
            topic = message.get("topic")
            logger.info(f"Client {client_id} unsubscribed from topic: {topic}")
            return {
                "type": "subscription_cancelled",
                "topic": topic,
                "client_id": client_id,
            }
        else:
            return {
                "type": "error",
                "error": "unknown_message_type",
                "message": f"Unknown message type: {message_type}",
            }

    except Exception as e:
        logger.error(f"Error handling WebSocket message: {e}")
        return {"type": "error", "error": "message_handling_error", "message": str(e)}


async def handle_query_websocket(websocket: WebSocket, client_id: str):
    """Handle WebSocket connections for query operations."""
    while True:
        try:
            data = await websocket.receive_text()
            message = json.loads(data)

            if message.get("type") == "query":
                query_text = message.get("query", "")

                # Send query started notification
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "query_started",
                            "query": query_text,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                    )
                )

                # Stream query results (simulated)
                await asyncio.sleep(0.5)  # Simulate processing time
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "query_result",
                            "query": query_text,
                            "result": f"Mock result for: {query_text}",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                    )
                )

        except WebSocketDisconnect:
            break
        except Exception as e:
            await websocket.send_text(json.dumps({"type": "error", "error": str(e)}))


async def handle_documents_websocket(websocket: WebSocket, client_id: str):
    """Handle WebSocket connections for document operations."""
    while True:
        try:
            data = await websocket.receive_text()
            message = json.loads(data)

            # Handle document-related operations
            if message.get("type") == "document_status":
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "document_status_response",
                            "status": "healthy",
                            "document_count": 42,  # Mock data
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                    )
                )

        except WebSocketDisconnect:
            break
        except Exception as e:
            await websocket.send_text(json.dumps({"type": "error", "error": str(e)}))


async def handle_graph_websocket(websocket: WebSocket, client_id: str):
    """Handle WebSocket connections for graph operations."""
    while True:
        try:
            data = await websocket.receive_text()
            message = json.loads(data)

            # Handle graph-related operations
            if message.get("type") == "graph_status":
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "graph_status_response",
                            "nodes": 123,  # Mock data
                            "edges": 456,  # Mock data
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                    )
                )

        except WebSocketDisconnect:
            break
        except Exception as e:
            await websocket.send_text(json.dumps({"type": "error", "error": str(e)}))


# Server-Sent Events (SSE) endpoints
@app.get("/mcp/stream")
async def mcp_sse_endpoint(request: Request):
    """
    General SSE endpoint for streaming server events.
    """

    async def event_generator():
        try:
            # Send initial connection event
            data = {
                "type": "connected",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "server": APP_NAME,
            }
            yield f"data: {json.dumps(data)}\n\n"

            # Send periodic heartbeat
            while True:
                if await request.is_disconnected():
                    break

                # Send heartbeat every 30 seconds
                heartbeat_data = {
                    "type": "heartbeat",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "connections": websocket_manager.get_connection_stats(),
                }
                yield f"data: {json.dumps(heartbeat_data)}\n\n"

                await asyncio.sleep(30)

        except Exception as e:
            logger.error(f"SSE error: {e}")
            error_data = {
                "type": "error",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            yield f"data: {json.dumps(error_data)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control",
        },
    )


@app.get("/mcp/stream/{operation}")
async def mcp_sse_operation_endpoint(operation: str, request: Request):
    """
    Operation-specific SSE endpoint for streaming operation results.
    """

    async def operation_event_generator():
        try:
            # Send operation started event
            start_data = {
                "type": "operation_started",
                "operation": operation,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            yield f"data: {json.dumps(start_data)}\n\n"

            # Simulate operation progress
            for i in range(1, 6):
                if await request.is_disconnected():
                    break

                progress_data = {
                    "type": "operation_progress",
                    "operation": operation,
                    "progress": i * 20,
                    "message": "Step " + str(i) + " of 5 completed",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                yield f"data: {json.dumps(progress_data)}\n\n"

                await asyncio.sleep(1)

            # Send completion event
            if not await request.is_disconnected():
                completion_data = {
                    "type": "operation_completed",
                    "operation": operation,
                    "result": "Operation " + operation + " completed successfully",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                yield f"data: {json.dumps(completion_data)}\n\n"

        except Exception as e:
            logger.error(f"SSE operation error: {e}")
            error_data = {
                "type": "error",
                "operation": operation,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            yield f"data: {json.dumps(error_data)}\n\n"

    return StreamingResponse(
        operation_event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control",
        },
    )


@app.get("/mcp/connections", response_model=Dict[str, Any])
async def get_websocket_connections(user: Optional[Dict] = Depends(get_optional_user)):
    """
    Get current WebSocket connection statistics.
    """
    stats = websocket_manager.get_connection_stats()
    return {
        "websocket_stats": stats,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "server_info": {"name": APP_NAME, "version": APP_VERSION},
    }


# MCP Tool Discovery and Metadata Endpoints
@app.get("/tools/list", response_model=Dict[str, Any])
async def list_tools(
    category: Optional[str] = None, user: Optional[Dict] = Depends(get_optional_user)
):
    """
    MCP tools/list endpoint - List available tools with metadata.

    This endpoint provides comprehensive tool discovery functionality,
    allowing clients to discover available tools and their capabilities.
    """
    try:
        from .protocol.tools import ToolCategory, ToolManager

        # Initialize tool manager (this will be properly initialized in Phase 5)
        tool_manager = ToolManager(settings)
        await tool_manager.initialize()

        # Get all tools or filter by category
        tools_list = tool_manager.get_tools_list()

        # Filter by category if requested
        if category:
            try:
                filter_category = ToolCategory(category)
                tools_list = [
                    tool
                    for tool in tools_list
                    if tool.get("metadata", {}).get("category") == filter_category.value
                ]
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid category '{category}'. Valid categories: {[c.value for c in ToolCategory]}",
                )

        return {
            "tools": tools_list,
            "total_count": len(tools_list),
            "categories": [c.value for c in ToolCategory],
            "server_info": {
                "name": APP_NAME,
                "version": APP_VERSION,
                "capabilities": {
                    "supports_progress": True,
                    "supports_streaming": True,
                    "supports_cancellation": True,
                },
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error(f"Error listing tools: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list tools: {str(e)}")


@app.post("/tools/call", response_model=Dict[str, Any])
async def call_tool(
    request: Dict[str, Any], user: Optional[Dict] = Depends(get_optional_user)
):
    """
    MCP tools/call endpoint - Execute a tool with parameters.

    This endpoint handles tool execution with comprehensive error handling
    and progress tracking for long-running operations.
    """
    try:
        from .protocol.server import ConnectionSession
        from .protocol.tools import ToolManager

        # Validate request structure
        if "name" not in request:
            raise HTTPException(status_code=400, detail="Tool name is required")

        tool_name = request["name"]
        arguments = request.get("arguments", {})

        # Create a mock session for HTTP calls (in real implementation, this would be from WebSocket)
        session = ConnectionSession(
            session_id=f"http_{datetime.now().timestamp()}",
            authenticated=True,
            context=request.get("context"),  # Allow context override
        )

        # Initialize tool manager
        tool_manager = ToolManager(settings)
        await tool_manager.initialize()

        # Execute the tool
        result = await tool_manager.call_tool(tool_name, session, arguments)

        return {
            "tool_name": tool_name,
            "execution_result": result,
            "session_id": session.session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error(f"Error calling tool: {e}")
        raise HTTPException(status_code=500, detail=f"Tool execution failed: {str(e)}")


@app.get("/tools/metadata", response_model=Dict[str, Any])
async def get_tools_metadata(user: Optional[Dict] = Depends(get_optional_user)):
    """
    Get comprehensive metadata about the tool system.

    Provides detailed information about tool categories, capabilities,
    and system-wide tool statistics.
    """
    try:
        from .protocol.tools import ToolCategory, ToolManager

        # Initialize tool manager
        tool_manager = ToolManager(settings)
        await tool_manager.initialize()

        # Get tools by category
        tools_by_category = {}
        for category in ToolCategory:
            category_tools = [
                tool
                for tool in tool_manager.get_tools_list()
                if tool.get("metadata", {}).get("category") == category.value
            ]
            tools_by_category[category.value] = {
                "count": len(category_tools),
                "tools": [tool["name"] for tool in category_tools],
                "description": _get_category_description(category),
            }

        return {
            "categories": tools_by_category,
            "total_tools": len(tool_manager.get_tools_list()),
            "capabilities": {
                "progress_tracking": True,
                "streaming_results": True,
                "parameter_validation": True,
                "error_recovery": True,
                "session_management": True,
            },
            "supported_parameter_types": [
                "string",
                "integer",
                "number",
                "boolean",
                "array",
                "object",
            ],
            "server_info": {
                "name": APP_NAME,
                "version": APP_VERSION,
                "protocol_version": settings.mcp.protocol_version,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error(f"Error getting tools metadata: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get metadata: {str(e)}")


@app.get("/tools/{tool_name}/schema", response_model=Dict[str, Any])
async def get_tool_schema(
    tool_name: str, user: Optional[Dict] = Depends(get_optional_user)
):
    """
    Get detailed schema for a specific tool.

    Provides comprehensive parameter schema, examples, and usage information
    for a specific tool.
    """
    try:
        from .protocol.tools import ToolManager

        # Initialize tool manager
        tool_manager = ToolManager(settings)
        await tool_manager.initialize()

        # Get tool from registry
        tool = tool_manager.registry.get_tool(tool_name)
        if not tool:
            raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")

        # Get comprehensive tool schema
        schema = tool.to_mcp_schema()

        # Add additional metadata
        enhanced_schema = {
            **schema,
            "detailed_metadata": {
                "category": tool.category.value,
                "category_description": _get_category_description(tool.category),
                "supports_progress": tool.supports_progress,
                "supports_streaming": tool.supports_streaming,
                "requires_context": tool.requires_context,
                "parameter_count": len(tool.parameters),
                "required_parameters": [p.name for p in tool.parameters if p.required],
                "optional_parameters": [
                    p.name for p in tool.parameters if not p.required
                ],
            },
            "usage_examples": _get_tool_examples(tool_name),
            "error_codes": _get_tool_error_codes(tool_name),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        return enhanced_schema

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting tool schema: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get tool schema: {str(e)}"
        )


@app.get("/tools/categories", response_model=Dict[str, Any])
async def get_tool_categories(user: Optional[Dict] = Depends(get_optional_user)):
    """
    Get information about tool categories.

    Provides detailed information about each tool category,
    including descriptions and available tools.
    """
    try:
        from .protocol.tools import ToolCategory, ToolManager

        # Initialize tool manager
        tool_manager = ToolManager(settings)
        await tool_manager.initialize()

        categories_info = {}
        for category in ToolCategory:
            category_tools = [
                tool
                for tool in tool_manager.get_tools_list()
                if tool.get("metadata", {}).get("category") == category.value
            ]

            categories_info[category.value] = {
                "name": category.value,
                "display_name": category.value.replace("_", " ").title(),
                "description": _get_category_description(category),
                "tool_count": len(category_tools),
                "tools": [
                    {
                        "name": tool["name"],
                        "description": tool["description"],
                        "requires_context": tool.get("metadata", {}).get(
                            "requires_context", True
                        ),
                    }
                    for tool in category_tools
                ],
                "capabilities": {
                    "progress_tracking": any(
                        tool.get("metadata", {}).get("supports_progress", False)
                        for tool in category_tools
                    ),
                    "streaming": any(
                        tool.get("metadata", {}).get("supports_streaming", False)
                        for tool in category_tools
                    ),
                },
            }

        return {
            "categories": categories_info,
            "total_categories": len(ToolCategory),
            "total_tools": len(tool_manager.get_tools_list()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error(f"Error getting tool categories: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get categories: {str(e)}"
        )


def _get_category_description(category) -> str:
    """Get human-readable description for tool category."""
    descriptions = {
        "context_management": "Tools for managing LightRAG contexts and switching between knowledge bases",
        "query_operations": "Tools for querying the knowledge graph with various modes and parameters",
        "semantic_search": "Tools for semantic search and concept discovery within the knowledge base",
        "graph_exploration": "Tools for exploring entity relationships and graph structure",
        "document_access": "Tools for accessing raw documents and processed content chunks",
        "system_utilities": "Utility tools for cache management, help, and system operations",
    }
    return descriptions.get(category.value, f"Tools in the {category.value} category")


def _get_tool_examples(tool_name: str) -> List[Dict[str, Any]]:
    """Get usage examples for a specific tool."""
    examples = {
        "list_contexts": [
            {
                "description": "List all available contexts",
                "parameters": {},
                "expected_result": "Array of context names and metadata",
            }
        ],
        "query": [
            {
                "description": "Perform a global query",
                "parameters": {
                    "query": "What are the main concepts in this knowledge base?",
                    "mode": "global",
                },
                "expected_result": "Comprehensive answer with entity relationships",
            },
            {
                "description": "Perform a local query with specific parameters",
                "parameters": {
                    "query": "machine learning algorithms",
                    "mode": "local",
                    "top_k": 5,
                },
                "expected_result": "Top 5 most relevant local results",
            },
        ],
    }
    return examples.get(
        tool_name,
        [
            {
                "description": f"Basic usage of {tool_name}",
                "parameters": {},
                "expected_result": "Tool-specific result format",
            }
        ],
    )


def _get_tool_error_codes(tool_name: str) -> List[Dict[str, Any]]:
    """Get possible error codes for a specific tool."""
    common_errors = [
        {
            "code": "VALIDATION_ERROR",
            "description": "Parameter validation failed",
            "resolution": "Check parameter types and required fields",
        },
        {
            "code": "CONTEXT_ERROR",
            "description": "No context selected or context not found",
            "resolution": "Use switch_context tool to select a valid context",
        },
        {
            "code": "LIGHTRAG_API_ERROR",
            "description": "LightRAG API communication failed",
            "resolution": "Check LightRAG service status and connectivity",
        },
    ]

    tool_specific_errors = {
        "switch_context": [
            {
                "code": "CONTEXT_NOT_FOUND",
                "description": "Specified context does not exist",
                "resolution": "Use list_contexts to see available contexts",
            }
        ],
        "query": [
            {
                "code": "QUERY_EXECUTION_ERROR",
                "description": "Query execution failed in LightRAG",
                "resolution": "Simplify query or check knowledge base status",
            }
        ],
    }

    return common_errors + tool_specific_errors.get(tool_name, [])


# Streaming Operation Endpoints for Long-Running Operations
@app.post("/operations/start", response_model=Dict[str, Any])
async def start_streaming_operation(
    request: Dict[str, Any], user: Optional[Dict] = Depends(get_optional_user)
):
    """
    Start a long-running streaming operation.

    This endpoint initiates operations that may take significant time to complete,
    providing immediate response with operation ID for tracking progress.
    """
    try:
        from .protocol.server import ConnectionSession, MCPProtocolServer

        # Validate request structure
        if "method" not in request:
            raise HTTPException(status_code=400, detail="Method is required")

        method = request["method"]
        params = request.get("params", {})

        # Create a session for the operation
        session = ConnectionSession(
            session_id=f"stream_{datetime.now().timestamp()}",
            authenticated=True,
            context=request.get("context"),
        )

        # Initialize protocol server (in real implementation, this would be a singleton)
        config = settings  # Use existing settings as config
        protocol_server = MCPProtocolServer(config)

        # Start the streaming operation
        operation_id = await protocol_server.start_streaming_operation(
            session, method, params
        )

        operation_status = protocol_server.get_operation_status(operation_id)

        return {
            "operation_id": operation_id,
            "status": operation_status,
            "endpoints": {
                "status": f"/operations/{operation_id}/status",
                "cancel": f"/operations/{operation_id}/cancel",
                "stream": f"/operations/{operation_id}/stream",
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error(f"Error starting streaming operation: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to start operation: {str(e)}"
        )


@app.get("/operations/{operation_id}/status", response_model=Dict[str, Any])
async def get_operation_status(
    operation_id: str, user: Optional[Dict] = Depends(get_optional_user)
):
    """
    Get the current status of a streaming operation.

    Provides detailed information about operation progress, current status,
    and any results or errors that have occurred.
    """
    try:
        from .protocol.server import MCPProtocolServer

        # In real implementation, this would use a shared protocol server instance
        config = settings
        protocol_server = MCPProtocolServer(config)

        status = protocol_server.get_operation_status(operation_id)

        if not status:
            raise HTTPException(
                status_code=404, detail=f"Operation '{operation_id}' not found"
            )

        return {
            "operation": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting operation status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}")


@app.post("/operations/{operation_id}/cancel", response_model=Dict[str, Any])
async def cancel_operation(
    operation_id: str, user: Optional[Dict] = Depends(get_optional_user)
):
    """
    Cancel a running streaming operation.

    Attempts to gracefully cancel a long-running operation,
    allowing for cleanup and resource deallocation.
    """
    try:
        from .protocol.server import MCPProtocolServer

        config = settings
        protocol_server = MCPProtocolServer(config)

        cancelled = await protocol_server.cancel_operation(operation_id)

        if not cancelled:
            raise HTTPException(
                status_code=400,
                detail=f"Operation '{operation_id}' not found or already completed",
            )

        return {
            "operation_id": operation_id,
            "cancelled": True,
            "message": "Operation cancellation requested",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling operation: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to cancel operation: {str(e)}"
        )


@app.get("/operations/{operation_id}/stream")
async def stream_operation_progress(
    operation_id: str,
    request: Request,
    user: Optional[Dict] = Depends(get_optional_user),
):
    """
    Stream real-time progress updates for a long-running operation.

    Uses Server-Sent Events to provide continuous updates about
    operation progress, status changes, and results.
    """

    async def progress_event_generator():
        try:
            from .protocol.server import MCPProtocolServer

            config = settings
            protocol_server = MCPProtocolServer(config)

            # Send initial status
            status = protocol_server.get_operation_status(operation_id)
            if not status:
                error_data = {
                    "type": "error",
                    "error": f"Operation {operation_id} not found",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                yield f"data: {json.dumps(error_data)}\n\n"
                return

            status_data = {
                "type": "status",
                "operation": status,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            yield f"data: {json.dumps(status_data)}\n\n"

            # Stream progress updates
            last_update = status.get("updated_at")

            while True:
                if await request.is_disconnected():
                    break

                # Check for updates
                current_status = protocol_server.get_operation_status(operation_id)
                if not current_status:
                    break

                # Send update if status changed
                if current_status.get("updated_at") != last_update:
                    progress_data = {
                        "type": "progress",
                        "operation": current_status,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    yield f"data: {json.dumps(progress_data)}\n\n"
                    last_update = current_status.get("updated_at")

                # Check if operation is complete
                if current_status.get("status") in ["completed", "failed", "cancelled"]:
                    completion_data = {
                        "type": "completed",
                        "operation": current_status,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    yield f"data: {json.dumps(completion_data)}\n\n"
                    break

                await asyncio.sleep(1)  # Poll every second

        except Exception as e:
            logger.error(f"SSE streaming error: {e}")
            error_data = {
                "type": "error",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            yield f"data: {json.dumps(error_data)}\n\n"

    return StreamingResponse(
        progress_event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control",
        },
    )


@app.get("/operations", response_model=Dict[str, Any])
async def list_operations(
    status: Optional[str] = None,
    limit: int = 50,
    user: Optional[Dict] = Depends(get_optional_user),
):
    """
    List streaming operations with optional filtering.

    Provides an overview of all operations, their current status,
    and basic metadata for monitoring and debugging.
    """
    try:
        from .protocol.server import MCPProtocolServer, OperationStatus

        config = settings
        protocol_server = MCPProtocolServer(config)

        # Get all operations (in real implementation, this would be filtered by user/session)
        all_operations = [
            op.to_dict() for op in protocol_server.streaming_operations.values()
        ]

        # Filter by status if requested
        if status:
            try:
                filter_status = OperationStatus(status)
                all_operations = [
                    op for op in all_operations if op["status"] == filter_status.value
                ]
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status '{status}'. Valid statuses: {[s.value for s in OperationStatus]}",
                )

        # Apply limit
        operations = all_operations[:limit]

        # Calculate statistics
        status_counts = {}
        for op in all_operations:
            op_status = op["status"]
            status_counts[op_status] = status_counts.get(op_status, 0) + 1

        return {
            "operations": operations,
            "total_count": len(all_operations),
            "returned_count": len(operations),
            "status_counts": status_counts,
            "valid_statuses": [s.value for s in OperationStatus],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing operations: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to list operations: {str(e)}"
        )


# Connection Lifecycle Management Endpoints
@app.get("/sessions", response_model=Dict[str, Any])
async def list_sessions(
    state: Optional[str] = None,
    limit: int = 50,
    user: Optional[Dict] = Depends(get_optional_user),
):
    """
    List active MCP sessions with optional filtering.

    Provides comprehensive information about connection sessions,
    their current state, and resource usage statistics.
    """
    try:
        from .protocol.server import ConnectionState, MCPProtocolServer

        config = settings
        protocol_server = MCPProtocolServer(config)

        # Get all sessions
        all_sessions = [
            session.to_dict() for session in protocol_server.get_all_sessions()
        ]

        # Filter by state if requested
        if state:
            try:
                filter_state = ConnectionState(state)
                all_sessions = [
                    session
                    for session in all_sessions
                    if session["state"] == filter_state.value
                ]
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid state '{state}'. Valid states: {[s.value for s in ConnectionState]}",
                )

        # Apply limit
        sessions = all_sessions[:limit]

        # Get session statistics
        session_stats = protocol_server.get_session_statistics()

        return {
            "sessions": sessions,
            "total_count": len(all_sessions),
            "returned_count": len(sessions),
            "statistics": session_stats,
            "valid_states": [s.value for s in ConnectionState],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing sessions: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to list sessions: {str(e)}"
        )


@app.get("/sessions/{session_id}", response_model=Dict[str, Any])
async def get_session_details(
    session_id: str, user: Optional[Dict] = Depends(get_optional_user)
):
    """
    Get detailed information about a specific session.

    Provides comprehensive session information including state,
    resource usage, capabilities, and connection metadata.
    """
    try:
        from .protocol.server import MCPProtocolServer

        config = settings
        protocol_server = MCPProtocolServer(config)

        session = protocol_server.get_session(session_id)
        if not session:
            raise HTTPException(
                status_code=404, detail=f"Session '{session_id}' not found"
            )

        # Get session operations
        session_operations = [
            op.to_dict()
            for op in protocol_server.streaming_operations.values()
            if op.session_id == session_id
        ]

        return {
            "session": session.to_dict(),
            "operations": session_operations,
            "operation_count": len(session_operations),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting session details: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get session details: {str(e)}"
        )


@app.post("/sessions/{session_id}/disconnect", response_model=Dict[str, Any])
async def disconnect_session(
    session_id: str,
    request: Optional[Dict[str, Any]] = None,
    user: Optional[Dict] = Depends(get_optional_user),
):
    """
    Disconnect a specific session gracefully.

    Performs cleanup of resources and cancels any active operations
    associated with the session.
    """
    try:
        from .protocol.server import MCPProtocolServer

        config = settings
        protocol_server = MCPProtocolServer(config)

        reason = "Manual disconnect"
        graceful = True

        if request:
            reason = request.get("reason", reason)
            graceful = request.get("graceful", graceful)

        success = await protocol_server.disconnect_session(session_id, reason, graceful)

        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Session '{session_id}' not found or already disconnected",
            )

        return {
            "session_id": session_id,
            "disconnected": True,
            "reason": reason,
            "graceful": graceful,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error disconnecting session: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to disconnect session: {str(e)}"
        )


@app.post("/sessions/cleanup", response_model=Dict[str, Any])
async def cleanup_stale_sessions(
    request: Optional[Dict[str, Any]] = None,
    user: Optional[Dict] = Depends(get_optional_user),
):
    """
    Clean up stale and idle sessions.

    Removes sessions that have been idle for too long or are in
    disconnected states to free up server resources.
    """
    try:
        from .protocol.server import MCPProtocolServer

        config = settings
        protocol_server = MCPProtocolServer(config)

        idle_threshold_minutes = 30
        stale_threshold_hours = 24

        if request:
            idle_threshold_minutes = request.get(
                "idle_threshold_minutes", idle_threshold_minutes
            )
            stale_threshold_hours = request.get(
                "stale_threshold_hours", stale_threshold_hours
            )

        cleaned_count = await protocol_server.cleanup_stale_sessions(
            idle_threshold_minutes=idle_threshold_minutes,
            stale_threshold_hours=stale_threshold_hours,
        )

        return {
            "cleaned_sessions": cleaned_count,
            "idle_threshold_minutes": idle_threshold_minutes,
            "stale_threshold_hours": stale_threshold_hours,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error(f"Error cleaning up sessions: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to cleanup sessions: {str(e)}"
        )


@app.get("/sessions/statistics", response_model=Dict[str, Any])
async def get_session_statistics(user: Optional[Dict] = Depends(get_optional_user)):
    """
    Get comprehensive session statistics.

    Provides overview of all sessions including state distribution,
    resource usage, and operational metrics.
    """
    try:
        from .protocol.server import MCPProtocolServer

        config = settings
        protocol_server = MCPProtocolServer(config)

        statistics = protocol_server.get_session_statistics()

        # Add additional server-level statistics
        statistics.update(
            {
                "server_info": {
                    "name": APP_NAME,
                    "version": APP_VERSION,
                    "uptime": "N/A",  # Would be calculated from server start time
                    "memory_usage": "N/A",  # Would be calculated from system metrics
                },
                "endpoints": {
                    "sessions": "/sessions",
                    "session_details": "/sessions/{session_id}",
                    "disconnect": "/sessions/{session_id}/disconnect",
                    "cleanup": "/sessions/cleanup",
                    "statistics": "/sessions/statistics",
                },
            }
        )

        return statistics

    except Exception as e:
        logger.error(f"Error getting session statistics: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get session statistics: {str(e)}"
        )


@app.post("/sessions/{session_id}/heartbeat", response_model=Dict[str, Any])
async def session_heartbeat(
    session_id: str, user: Optional[Dict] = Depends(get_optional_user)
):
    """
    Send a heartbeat for a specific session.

    Updates the session's last activity timestamp and heartbeat count
    to keep the session alive and track connectivity.
    """
    try:
        from .protocol.server import MCPProtocolServer

        config = settings
        protocol_server = MCPProtocolServer(config)

        session = protocol_server.get_session(session_id)
        if not session:
            raise HTTPException(
                status_code=404, detail=f"Session '{session_id}' not found"
            )

        session.record_heartbeat()

        return {
            "session_id": session_id,
            "heartbeat_count": session.heartbeat_count,
            "last_heartbeat": (
                session.last_heartbeat.isoformat() if session.last_heartbeat else None
            ),
            "session_state": session.state.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing heartbeat: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to process heartbeat: {str(e)}"
        )


# Protocol Validation Endpoints


@app.post("/validation/request", response_model=Dict[str, Any])
async def validate_json_rpc_request(
    request_data: Dict[str, Any], user: Optional[Dict] = Depends(get_optional_user)
):
    """
    Validate a JSON-RPC request structure and parameters.

    This endpoint provides comprehensive validation for JSON-RPC requests
    including method-specific parameter validation for MCP protocol methods.
    """
    try:
        # Import the validator from protocol server
        from .protocol.server import MCPProtocolValidator

        validator = MCPProtocolValidator()

        # Validate the request structure
        validation_results = validator.validate_json_rpc_request(request_data)

        # Add method-specific validation if available
        method = request_data.get("method")
        if method == "initialize" and "params" in request_data:
            init_validation = validator.validate_mcp_initialize_params(
                request_data["params"]
            )
            validation_results.extend(init_validation)
        elif method == "tools/call" and "params" in request_data:
            tool_validation = validator.validate_mcp_tool_call_params(
                request_data["params"]
            )
            validation_results.extend(tool_validation)

        # Validate message size
        message_str = json.dumps(request_data)
        size_validation = validator.validate_message_size(message_str)
        validation_results.extend(size_validation)

        return {
            "validation_results": [r.to_dict() for r in validation_results],
            "is_valid": all(r.is_valid for r in validation_results),
            "error_count": len([r for r in validation_results if not r.is_valid]),
            "warning_count": len(
                [r for r in validation_results if r.severity.value == "warning"]
            ),
            "info_count": len(
                [r for r in validation_results if r.severity.value == "info"]
            ),
            "request_summary": {
                "method": request_data.get("method"),
                "has_id": "id" in request_data,
                "has_params": "params" in request_data,
                "message_size": len(message_str),
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error(f"Request validation error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Validation failed: {str(e)}")


@app.post("/validation/response", response_model=Dict[str, Any])
async def validate_json_rpc_response(
    response_data: Dict[str, Any], user: Optional[Dict] = Depends(get_optional_user)
):
    """
    Validate a JSON-RPC response structure.

    This endpoint validates JSON-RPC response format including proper
    error object structure and result/error field requirements.
    """
    try:
        from .protocol.server import MCPProtocolValidator

        validator = MCPProtocolValidator()

        # Validate the response structure
        validation_results = validator.validate_json_rpc_response(response_data)

        # Validate message size
        message_str = json.dumps(response_data)
        size_validation = validator.validate_message_size(message_str)
        validation_results.extend(size_validation)

        return {
            "validation_results": [r.to_dict() for r in validation_results],
            "is_valid": all(r.is_valid for r in validation_results),
            "error_count": len([r for r in validation_results if not r.is_valid]),
            "warning_count": len(
                [r for r in validation_results if r.severity.value == "warning"]
            ),
            "info_count": len(
                [r for r in validation_results if r.severity.value == "info"]
            ),
            "response_summary": {
                "has_result": "result" in response_data,
                "has_error": "error" in response_data,
                "has_id": "id" in response_data,
                "message_size": len(message_str),
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error(f"Response validation error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Validation failed: {str(e)}")


@app.get("/validation/summary", response_model=Dict[str, Any])
async def get_validation_summary(
    include_history: bool = False,
    recent_count: int = 10,
    user: Optional[Dict] = Depends(get_optional_user),
):
    """
    Get protocol validation statistics and summary.

    This endpoint provides insights into validation patterns,
    common errors, and protocol compliance metrics.
    """
    try:
        from .protocol.server import MCPProtocolValidator

        validator = MCPProtocolValidator()
        summary = validator.get_validation_summary()

        # Add recent validation history if requested
        if include_history and recent_count > 0:
            recent_history = (
                validator.validation_history[-recent_count:]
                if validator.validation_history
                else []
            )
            summary["recent_validations"] = [r.to_dict() for r in recent_history]

        # Add server-specific validation metrics
        summary.update(
            {
                "server_info": {
                    "name": APP_NAME,
                    "version": APP_VERSION,
                    "protocol_version": settings.mcp.protocol_version,
                },
                "validation_config": {
                    "max_message_size": validator.MAX_MESSAGE_SIZE,
                    "max_param_depth": validator.MAX_PARAM_DEPTH,
                    "validation_patterns": {
                        "id_pattern": validator.VALID_ID_PATTERN.pattern,
                        "method_pattern": validator.VALID_METHOD_PATTERN.pattern,
                    },
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

        return summary

    except Exception as e:
        logger.error(f"Validation summary error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to get validation summary: {str(e)}"
        )


@app.get("/validation/protocol", response_model=Dict[str, Any])
async def get_protocol_validation_info(
    user: Optional[Dict] = Depends(get_optional_user),
):
    """
    Get detailed information about MCP protocol validation rules and capabilities.

    This endpoint provides comprehensive information about supported
    protocol versions, validation rules, and compliance requirements.
    """
    try:
        from .protocol.server import (
            JSONRPCErrorCode,
            MCPCapability,
            MCPProtocolValidator,
            MCPProtocolVersion,
        )

        return {
            "protocol_info": {
                "supported_versions": [v.value for v in MCPProtocolVersion],
                "current_version": settings.mcp.protocol_version,
                "json_rpc_version": "2.0",
            },
            "supported_capabilities": [cap.value for cap in MCPCapability],
            "validation_rules": {
                "message_size": {
                    "max_size_bytes": MCPProtocolValidator.MAX_MESSAGE_SIZE,
                    "max_size_mb": MCPProtocolValidator.MAX_MESSAGE_SIZE
                    / (1024 * 1024),
                },
                "parameter_depth": {"max_depth": MCPProtocolValidator.MAX_PARAM_DEPTH},
                "id_format": {
                    "pattern": MCPProtocolValidator.VALID_ID_PATTERN.pattern,
                    "max_length": 64,
                    "description": "Alphanumeric characters, hyphens, underscores, and dots only",
                },
                "method_format": {
                    "pattern": MCPProtocolValidator.VALID_METHOD_PATTERN.pattern,
                    "description": "Must start with letter, can contain letters, numbers, underscores, and forward slashes",
                },
            },
            "error_codes": {
                "standard_json_rpc": {
                    "PARSE_ERROR": JSONRPCErrorCode.PARSE_ERROR.value,
                    "INVALID_REQUEST": JSONRPCErrorCode.INVALID_REQUEST.value,
                    "METHOD_NOT_FOUND": JSONRPCErrorCode.METHOD_NOT_FOUND.value,
                    "INVALID_PARAMS": JSONRPCErrorCode.INVALID_PARAMS.value,
                    "INTERNAL_ERROR": JSONRPCErrorCode.INTERNAL_ERROR.value,
                },
                "mcp_specific": {
                    "INITIALIZATION_ERROR": JSONRPCErrorCode.INITIALIZATION_ERROR.value,
                    "CAPABILITY_NOT_SUPPORTED": JSONRPCErrorCode.CAPABILITY_NOT_SUPPORTED.value,
                    "AUTHENTICATION_ERROR": JSONRPCErrorCode.AUTHENTICATION_ERROR.value,
                    "AUTHORIZATION_ERROR": JSONRPCErrorCode.AUTHORIZATION_ERROR.value,
                    "CONTEXT_ERROR": JSONRPCErrorCode.CONTEXT_ERROR.value,
                    "RATE_LIMIT_ERROR": JSONRPCErrorCode.RATE_LIMIT_ERROR.value,
                },
                "lightrag_specific": {
                    "VALIDATION_ERROR": JSONRPCErrorCode.VALIDATION_ERROR.value,
                    "LIGHTRAG_API_ERROR": JSONRPCErrorCode.LIGHTRAG_API_ERROR.value,
                    "CONTEXT_SWITCH_ERROR": JSONRPCErrorCode.CONTEXT_SWITCH_ERROR.value,
                    "DOCUMENT_NOT_FOUND": JSONRPCErrorCode.DOCUMENT_NOT_FOUND.value,
                    "QUERY_EXECUTION_ERROR": JSONRPCErrorCode.QUERY_EXECUTION_ERROR.value,
                    "KNOWLEDGE_GRAPH_ERROR": JSONRPCErrorCode.KNOWLEDGE_GRAPH_ERROR.value,
                },
            },
            "validation_methods": {
                "initialize": {
                    "required_fields": ["protocolVersion", "clientInfo"],
                    "client_info_fields": ["name", "version"],
                    "optional_fields": ["capabilities"],
                },
                "tools/call": {
                    "required_fields": ["name"],
                    "optional_fields": ["arguments"],
                    "argument_type": "object",
                },
            },
            "best_practices": [
                "Always include 'jsonrpc': '2.0' in requests and responses",
                "Use unique request IDs for tracking",
                "Include proper error objects with code and message",
                "Validate parameter types before sending requests",
                "Keep message sizes under 1MB for optimal performance",
                "Use structured error handling with appropriate error codes",
                "Implement proper capability negotiation during initialization",
                "Follow method naming conventions (e.g., 'tools/call', 'resources/list')",
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error(f"Protocol info error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to get protocol info: {str(e)}"
        )


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """
    Global exception handler for unhandled errors.
    """
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": "An unexpected error occurred",
            "type": "server_error",
        },
    )


if __name__ == "__main__":
    # Development server configuration
    logger.info(
        f"Starting development server on {settings.server.host}:{settings.server.port}"
    )

    uvicorn.run(
        "main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=settings.server.reload,
        log_level=settings.logging.level.value.lower(),
        workers=1,  # Single worker for development
    )
