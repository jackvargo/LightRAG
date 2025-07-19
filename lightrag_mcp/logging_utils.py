"""
LightRAG MCP Server - Logging Utilities

This module provides comprehensive logging utilities including structured logging,
performance monitoring, security event logging, and request tracing.
"""

import logging
import logging.config
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable, Dict, Optional, Union

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response as StarletteResponse

try:
    from .config import get_settings
except ImportError:
    # Handle direct execution case
    from config import get_settings


class TraceIDFilter(logging.Filter):
    """Filter to inject trace ID into log records."""

    def filter(self, record):
        """Add trace ID to log record if available."""
        if not hasattr(record, "trace_id"):
            record.trace_id = getattr(self, "_trace_id", "no-trace")
        return True

    def set_trace_id(self, trace_id: str):
        """Set the current trace ID."""
        self._trace_id = trace_id


class StructuredLogger:
    """Structured logger with context management."""

    def __init__(self, name: str):
        self.logger = structlog.get_logger(name)
        self.settings = get_settings()

    def debug(self, message: str, **kwargs):
        """Log debug message with context."""
        self.logger.debug(message, **kwargs)

    def info(self, message: str, **kwargs):
        """Log info message with context."""
        self.logger.info(message, **kwargs)

    def warning(self, message: str, **kwargs):
        """Log warning message with context."""
        self.logger.warning(message, **kwargs)

    def error(self, message: str, error: Optional[Exception] = None, **kwargs):
        """Log error message with context and exception details."""
        if error:
            kwargs["error_type"] = error.__class__.__name__
            kwargs["error_message"] = str(error)
            if hasattr(error, "__traceback__"):
                import traceback

                kwargs["traceback"] = "".join(traceback.format_tb(error.__traceback__))
        self.logger.error(message, **kwargs)

    def critical(self, message: str, error: Optional[Exception] = None, **kwargs):
        """Log critical message with context."""
        if error:
            kwargs["error_type"] = error.__class__.__name__
            kwargs["error_message"] = str(error)
        self.logger.critical(message, **kwargs)

    def bind(self, **context):
        """Bind context to logger (delegates to structlog)."""
        return self.logger.bind(**context)


class PerformanceLogger:
    """Logger for performance monitoring."""

    def __init__(self):
        self.logger = logging.getLogger("lightrag_mcp.performance")
        self.settings = get_settings()

    def log_query_performance(
        self,
        query: str,
        duration: float,
        result_count: int = 0,
        context: Optional[str] = None,
        **kwargs,
    ):
        """Log query performance metrics."""
        is_slow = duration > self.settings.logging.slow_query_threshold

        log_data = {
            "event_type": "query_performance",
            "query": query[:200] + "..." if len(query) > 200 else query,
            "duration_seconds": round(duration, 3),
            "result_count": result_count,
            "is_slow_query": is_slow,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if context:
            log_data["context"] = context

        log_data.update(kwargs)

        if is_slow:
            self.logger.warning(f"Slow query detected: {duration:.3f}s", extra=log_data)
        else:
            self.logger.info(f"Query completed: {duration:.3f}s", extra=log_data)

    def log_api_performance(
        self,
        endpoint: str,
        method: str,
        duration: float,
        status_code: int,
        user_id: Optional[str] = None,
        **kwargs,
    ):
        """Log API endpoint performance."""
        log_data = {
            "event_type": "api_performance",
            "endpoint": endpoint,
            "method": method,
            "duration_seconds": round(duration, 3),
            "status_code": status_code,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if user_id:
            log_data["user_id"] = user_id

        log_data.update(kwargs)

        self.logger.info(
            f"API call: {method} {endpoint} - {status_code} ({duration:.3f}s)",
            extra=log_data,
        )


class SecurityLogger:
    """Logger for security events."""

    def __init__(self):
        self.logger = logging.getLogger("lightrag_mcp.auth")
        self.settings = get_settings()

    def log_authentication_attempt(
        self,
        username: str,
        success: bool,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        **kwargs,
    ):
        """Log authentication attempts."""
        log_data = {
            "event_type": "authentication_attempt",
            "username": username,
            "success": success,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if ip_address:
            log_data["ip_address"] = ip_address
        if user_agent:
            log_data["user_agent"] = user_agent

        log_data.update(kwargs)

        if success:
            self.logger.info(
                f"Successful authentication for user: {username}", extra=log_data
            )
        else:
            self.logger.warning(
                f"Failed authentication attempt for user: {username}", extra=log_data
            )

    def log_authorization_failure(
        self,
        user_id: str,
        resource: str,
        action: str,
        ip_address: Optional[str] = None,
        **kwargs,
    ):
        """Log authorization failures."""
        log_data = {
            "event_type": "authorization_failure",
            "user_id": user_id,
            "resource": resource,
            "action": action,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if ip_address:
            log_data["ip_address"] = ip_address

        log_data.update(kwargs)

        self.logger.warning(
            f"Authorization denied for user {user_id} on {resource}:{action}",
            extra=log_data,
        )

    def log_token_event(
        self, event_type: str, user_id: str, token_type: str = "access", **kwargs
    ):
        """Log token-related events."""
        log_data = {
            "event_type": f"token_{event_type}",
            "user_id": user_id,
            "token_type": token_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        log_data.update(kwargs)

        self.logger.info(f"Token {event_type} for user: {user_id}", extra=log_data)


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for request logging and trace ID injection."""

    def __init__(self, app):
        super().__init__(app)
        self.performance_logger = PerformanceLogger()
        self.trace_filter = TraceIDFilter()
        self.settings = get_settings()

        # Add trace filter to all relevant loggers
        if self.settings.logging.include_trace_id:
            for logger_name in ["lightrag_mcp", "uvicorn"]:
                logger = logging.getLogger(logger_name)
                logger.addFilter(self.trace_filter)

    async def dispatch(self, request: Request, call_next) -> StarletteResponse:
        """Process request with logging and trace ID injection."""
        # Generate trace ID
        trace_id = str(uuid.uuid4())

        # Set trace ID in filter
        if self.settings.logging.include_trace_id:
            self.trace_filter.set_trace_id(trace_id)

        # Add trace ID to request state
        request.state.trace_id = trace_id

        # Record start time
        start_time = time.time()

        try:
            # Process request
            response = await call_next(request)

            # Calculate duration
            duration = time.time() - start_time

            # Log API performance
            self.performance_logger.log_api_performance(
                endpoint=request.url.path,
                method=request.method,
                duration=duration,
                status_code=response.status_code,
                trace_id=trace_id,
                query_params=(
                    dict(request.query_params) if request.query_params else None
                ),
            )

            # Add trace ID to response headers
            response.headers["X-Trace-ID"] = trace_id

            return response

        except Exception as e:
            duration = time.time() - start_time

            # Log error
            logger = StructuredLogger("lightrag_mcp.middleware")
            logger.error(
                "Request processing failed",
                error=e,
                trace_id=trace_id,
                endpoint=request.url.path,
                method=request.method,
                duration=duration,
            )

            raise


def setup_logging():
    """Setup comprehensive logging configuration."""
    settings = get_settings()
    log_config = settings.get_log_config()

    # Configure standard logging
    logging.config.dictConfig(log_config)

    # Configure structlog if JSON logging is enabled
    if settings.logging.json_format:
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.UnicodeDecoder(),
                structlog.processors.JSONRenderer(),
            ],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )


def get_logger(name: str) -> StructuredLogger:
    """Get a structured logger instance."""
    return StructuredLogger(name)


def performance_monitor(operation_name: str):
    """Decorator for monitoring operation performance."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            logger = PerformanceLogger()

            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time

                # Determine result count if possible
                result_count = 0
                if hasattr(result, "__len__"):
                    try:
                        result_count = len(result)
                    except:
                        pass

                logger.log_query_performance(
                    query=operation_name,
                    duration=duration,
                    result_count=result_count,
                    function=func.__name__,
                )

                return result

            except Exception as e:
                duration = time.time() - start_time
                logger.log_query_performance(
                    query=operation_name,
                    duration=duration,
                    function=func.__name__,
                    error=str(e),
                )
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            logger = PerformanceLogger()

            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time

                # Determine result count if possible
                result_count = 0
                if hasattr(result, "__len__"):
                    try:
                        result_count = len(result)
                    except:
                        pass

                logger.log_query_performance(
                    query=operation_name,
                    duration=duration,
                    result_count=result_count,
                    function=func.__name__,
                )

                return result

            except Exception as e:
                duration = time.time() - start_time
                logger.log_query_performance(
                    query=operation_name,
                    duration=duration,
                    function=func.__name__,
                    error=str(e),
                )
                raise

        # Return appropriate wrapper based on function type
        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


@contextmanager
def log_context(**context_vars):
    """Context manager for adding structured logging context."""
    # Store old context
    old_context = getattr(log_context, "_context", {})

    # Set new context
    new_context = {**old_context, **context_vars}
    log_context._context = new_context

    try:
        yield
    finally:
        # Restore old context
        log_context._context = old_context


# Global logger instances
security_logger = SecurityLogger()
performance_logger = PerformanceLogger()
