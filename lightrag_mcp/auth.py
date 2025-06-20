"""
LightRAG MCP Server - OAuth 2.1 Authentication

This module provides OAuth 2.1 authentication implementation for the MCP server,
including JWT token handling, authentication middleware, and security dependencies.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

# Import config types
from .config import AuthMode

# Import security logger - delay import to avoid circular dependency
logger = logging.getLogger(__name__)

# Security configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Bearer token security scheme
security = HTTPBearer()


class TokenData(BaseModel):
    """Token data model for JWT payload."""

    username: Optional[str] = None
    scopes: list[str] = []
    exp: Optional[datetime] = None
    iat: Optional[datetime] = None


class User(BaseModel):
    """User model for authentication."""

    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    disabled: bool = False
    scopes: list[str] = []


class UserInDB(User):
    """User model with hashed password for database storage."""

    hashed_password: str


class Token(BaseModel):
    """OAuth 2.1 token response model."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: Optional[str] = None
    scope: Optional[str] = None


class AuthenticationError(HTTPException):
    """Custom authentication error."""

    def __init__(self, detail: str = "Authentication failed"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


class AuthorizationError(HTTPException):
    """Custom authorization error."""

    def __init__(self, detail: str = "Insufficient permissions"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
        )


# Mock user database - TODO: Replace with actual database
fake_users_db = {
    "admin": {
        "username": "admin",
        "email": "admin@lightrag.com",
        "full_name": "MCP Admin",
        "hashed_password": pwd_context.hash("admin123"),  # Default password
        "disabled": False,
        "scopes": ["read", "write", "admin"],
    },
    "user": {
        "username": "user",
        "email": "user@lightrag.com",
        "full_name": "MCP User",
        "hashed_password": pwd_context.hash("user123"),
        "disabled": False,
        "scopes": ["read"],
    },
}


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Generate password hash."""
    return pwd_context.hash(password)


def get_user(username: str) -> Optional[UserInDB]:
    """Get user from database by username."""
    if username in fake_users_db:
        user_dict = fake_users_db[username]
        return UserInDB(**user_dict)
    return None


def authenticate_user(
    username: str, password: str, request: Optional[Request] = None
) -> Optional[UserInDB]:
    """Authenticate user with username and password."""
    # Get IP address and user agent for security logging
    ip_address = None
    user_agent = None
    if request:
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("User-Agent")

    user = get_user(username)
    if not user:
        # Log failed authentication attempt
        _log_auth_attempt(
            username, False, ip_address, user_agent, reason="user_not_found"
        )
        return None

    if not verify_password(password, user.hashed_password):
        # Log failed authentication attempt
        _log_auth_attempt(
            username, False, ip_address, user_agent, reason="invalid_password"
        )
        return None

    # Log successful authentication
    _log_auth_attempt(username, True, ip_address, user_agent)
    return user


def _log_auth_attempt(
    username: str,
    success: bool,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    **kwargs,
):
    """Log authentication attempt using security logger."""
    try:
        # Delayed import to avoid circular dependency
        from .logging_utils import security_logger

        security_logger.log_authentication_attempt(
            username=username,
            success=success,
            ip_address=ip_address,
            user_agent=user_agent,
            **kwargs,
        )
    except ImportError:
        # Fallback to basic logging if security logger not available
        logger.info(
            f"Authentication {'successful' if success else 'failed'} for user: {username}"
        )


def create_access_token(
    data: Dict[str, Any], expires_delta: Optional[timedelta] = None
) -> str:
    """Create JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        )

    to_encode.update(
        {"exp": expire, "iat": datetime.now(timezone.utc), "type": "access"}
    )

    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    # Log token creation
    username = data.get("sub", "unknown")
    _log_token_event("created", username, "access")

    return encoded_jwt


def create_refresh_token(data: Dict[str, Any]) -> str:
    """Create JWT refresh token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    to_encode.update(
        {"exp": expire, "iat": datetime.now(timezone.utc), "type": "refresh"}
    )

    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    # Log token creation
    username = data.get("sub", "unknown")
    _log_token_event("created", username, "refresh")

    return encoded_jwt


def _log_token_event(
    event_type: str, user_id: str, token_type: str = "access", **kwargs
):
    """Log token-related events using security logger."""
    try:
        # Delayed import to avoid circular dependency
        from .logging_utils import security_logger

        security_logger.log_token_event(
            event_type=event_type, user_id=user_id, token_type=token_type, **kwargs
        )
    except ImportError:
        # Fallback to basic logging if security logger not available
        logger.info(f"Token {event_type} for user: {user_id} (type: {token_type})")


def verify_token(token: str, token_type: str = "access") -> TokenData:
    """Verify and decode JWT token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        # Check token type
        if payload.get("type") != token_type:
            raise AuthenticationError("Invalid token type")

        # Extract token data
        username: str = payload.get("sub")
        scopes: list = payload.get("scopes", [])
        exp = payload.get("exp")
        iat = payload.get("iat")

        if username is None:
            raise AuthenticationError("Invalid token payload")

        # Convert timestamps
        exp_dt = datetime.fromtimestamp(exp, tz=timezone.utc) if exp else None
        iat_dt = datetime.fromtimestamp(iat, tz=timezone.utc) if iat else None

        return TokenData(username=username, scopes=scopes, exp=exp_dt, iat=iat_dt)

    except jwt.ExpiredSignatureError:
        raise AuthenticationError("Token has expired")
    except JWTError as e:
        logger.error(f"JWT verification failed: {e}")
        raise AuthenticationError("Invalid token")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> User:
    """Get current authenticated user from JWT token."""
    token = credentials.credentials
    token_data = verify_token(token)

    user = get_user(username=token_data.username)
    if user is None:
        raise AuthenticationError("User not found")

    if user.disabled:
        raise AuthenticationError("User account is disabled")

    return User(
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        disabled=user.disabled,
        scopes=user.scopes,
    )


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Get current active user (non-disabled)."""
    if current_user.disabled:
        raise AuthenticationError("User account is disabled")
    return current_user


def require_scopes(required_scopes: list[str]):
    """Dependency factory for scope-based authorization."""

    async def check_scopes(
        current_user: User = Depends(get_current_active_user),
    ) -> User:
        for scope in required_scopes:
            if scope not in current_user.scopes:
                raise AuthorizationError(
                    f"Operation requires '{scope}' scope. User has: {current_user.scopes}"
                )
        return current_user

    return check_scopes


def require_admin():
    """Dependency for admin-only operations."""
    return require_scopes(["admin"])


def require_write():
    """Dependency for write operations."""
    return require_scopes(["write"])


def require_read():
    """Dependency for read operations."""
    return require_scopes(["read"])


async def login_for_access_token(
    username: str, password: str, request: Optional[Request] = None
) -> Token:
    """Authenticate user and return OAuth 2.1 tokens."""
    user = authenticate_user(username, password, request)
    if not user:
        raise AuthenticationError("Incorrect username or password")

    # Create tokens
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username, "scopes": user.scopes},
        expires_delta=access_token_expires,
    )

    refresh_token = create_refresh_token(
        data={"sub": user.username, "scopes": user.scopes}
    )

    logger.info(f"User {user.username} successfully authenticated")

    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # Convert to seconds
        refresh_token=refresh_token,
        scope=" ".join(user.scopes),
    )


async def refresh_access_token(refresh_token: str) -> Token:
    """Refresh access token using refresh token."""
    token_data = verify_token(refresh_token, token_type="refresh")

    user = get_user(username=token_data.username)
    if not user or user.disabled:
        raise AuthenticationError("Invalid refresh token")

    # Create new access token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username, "scopes": user.scopes},
        expires_delta=access_token_expires,
    )

    logger.info(f"Access token refreshed for user {user.username}")

    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        scope=" ".join(user.scopes),
    )


# Authentication middleware class
class AuthenticationMiddleware:
    """Authentication middleware for request validation."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        """Process requests with authentication checks."""
        # TODO: Implement middleware logic for automatic token validation
        # This can be used for automatic authentication on all routes
        await self.app(scope, receive, send)


# FastAPI Middleware for Authentication
class FastAPIAuthenticationMiddleware:
    """
    FastAPI-compatible authentication middleware that handles different auth modes
    and provides automatic request validation.
    """

    def __init__(self, app, settings=None):
        self.app = app
        from .config import get_settings

        self.settings = settings or get_settings()

    async def __call__(self, scope, receive, send):
        """Process HTTP requests with authentication validation."""
        # Only process HTTP requests
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = scope
        path = request.get("path", "")
        method = request.get("method", "")

        # Skip authentication for public endpoints
        public_endpoints = {
            "/",
            "/health",
            "/discovery",
            "/docs",
            "/redoc",
            "/openapi.json",
        }

        if path in public_endpoints or path.startswith("/static"):
            await self.app(scope, receive, send)
            return

        # Handle authentication based on mode
        if self.settings.auth.mode == AuthMode.NONE:
            # No authentication required
            await self.app(scope, receive, send)
            return

        elif self.settings.auth.mode == AuthMode.API_KEY:
            # API key authentication
            if not await self._validate_api_key(scope):
                await self._send_auth_error(scope, receive, send, "Invalid API key")
                return

        elif self.settings.auth.mode == AuthMode.OAUTH:
            # OAuth 2.1 JWT authentication
            if not await self._validate_jwt_token(scope):
                await self._send_auth_error(
                    scope, receive, send, "Invalid or missing token"
                )
                return

        # Authentication successful, continue to application
        await self.app(scope, receive, send)

    async def _validate_api_key(self, scope) -> bool:
        """Validate API key from request headers."""
        headers = dict(scope.get("headers", []))

        # Look for API key in headers
        api_key = None
        for header_name, header_value in headers.items():
            if header_name.lower() == b"x-api-key":
                api_key = header_value.decode()
                break
            elif header_name.lower() == b"authorization":
                auth_header = header_value.decode()
                if auth_header.startswith("ApiKey "):
                    api_key = auth_header[7:]  # Remove "ApiKey " prefix
                break

        if not api_key:
            return False

        # Validate against configured API key
        return api_key == self.settings.auth.api_key

    async def _validate_jwt_token(self, scope) -> bool:
        """Validate JWT token from Authorization header."""
        headers = dict(scope.get("headers", []))

        # Look for Authorization header
        auth_header = None
        for header_name, header_value in headers.items():
            if header_name.lower() == b"authorization":
                auth_header = header_value.decode()
                break

        if not auth_header:
            return False

        # Extract Bearer token
        if not auth_header.startswith("Bearer "):
            return False

        token = auth_header[7:]  # Remove "Bearer " prefix

        try:
            # Verify the token
            token_data = verify_token(token)

            # Add user info to request scope for downstream use
            scope["user"] = {
                "username": token_data.username,
                "scopes": token_data.scopes,
            }

            return True

        except (AuthenticationError, AuthorizationError):
            return False

    async def _send_auth_error(self, scope, receive, send, message: str):
        """Send authentication error response."""
        response_body = {
            "error": "authentication_failed",
            "message": message,
            "type": "auth_error",
        }

        import json

        response_bytes = json.dumps(response_body).encode()

        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    [b"content-type", b"application/json"],
                    [
                        b"www-authenticate",
                        (
                            b"Bearer"
                            if self.settings.auth.mode == AuthMode.OAUTH
                            else b"ApiKey"
                        ),
                    ],
                ],
            }
        )

        await send(
            {
                "type": "http.response.body",
                "body": response_bytes,
            }
        )


# Route-level authentication decorators
def require_authentication(scopes: Optional[List[str]] = None):
    """
    Decorator factory for route-level authentication requirements.

    Args:
        scopes: List of required scopes for the route
    """

    def decorator(func):
        func._requires_auth = True
        func._required_scopes = scopes or []
        return func

    return decorator


def public_endpoint(func):
    """Decorator to mark an endpoint as public (no authentication required)."""
    func._public_endpoint = True
    return func


# FastAPI Dependencies for Route-Level Authentication
async def get_current_user_from_request(request: Request) -> Optional[User]:
    """FastAPI dependency to get current user from request scope."""
    user_data = getattr(request.scope, "user", None)
    if not user_data:
        return None

    # Get full user data from database
    user = get_user(user_data["username"])
    if not user:
        return None

    return User(
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        disabled=user.disabled,
        scopes=user.scopes,
    )


async def require_authenticated_user(request: Request) -> User:
    """FastAPI dependency that requires an authenticated user."""
    user = await get_current_user_from_request(request)
    if not user:
        raise AuthenticationError("Authentication required")
    return user


def create_scope_dependency(required_scopes: List[str]):
    """Create a FastAPI dependency that requires specific scopes."""

    async def check_user_scopes(
        user: User = Depends(require_authenticated_user),
    ) -> User:
        for scope in required_scopes:
            if scope not in user.scopes:
                raise AuthorizationError(
                    f"Operation requires '{scope}' scope. User has: {user.scopes}"
                )
        return user

    return check_user_scopes


# Pre-defined scope dependencies
RequireRead = Depends(create_scope_dependency(["read"]))
RequireWrite = Depends(create_scope_dependency(["write"]))
RequireAdmin = Depends(create_scope_dependency(["admin"]))


# Optional authentication dependency (returns None if not authenticated)
async def get_optional_user(request: Request) -> Optional[User]:
    """FastAPI dependency that optionally returns the current user if authenticated."""
    try:
        return await get_current_user_from_request(request)
    except:
        return None
