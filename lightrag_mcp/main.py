"""
LightRAG MCP Server - Main FastAPI Application

This module provides the main FastAPI application for the LightRAG MCP server,
including basic health checks, CORS configuration, and application lifecycle management.
"""

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import redis.asyncio as redis
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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
        "supported_transports": [
            "http"
            # TODO: Add WebSocket support in future
        ],
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
            "real_time_updates": False,  # TODO: Implement if needed
        },
        "limits": {
            "max_request_size": settings.mcp.max_request_size,
            "request_timeout": settings.mcp.request_timeout,
            "max_concurrent_requests": 10,  # TODO: Make configurable
        },
        "health_check": {"endpoint": "/health", "interval_seconds": 30},
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
