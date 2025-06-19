"""
LightRAG MCP Server - Configuration Management

This module provides comprehensive configuration management for the MCP server,
including environment-based settings, validation, and multiple deployment modes.
"""

import os
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings


class Environment(str, Enum):
    """Deployment environment types."""

    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"


class AuthMode(str, Enum):
    """Authentication modes for different deployment scenarios."""

    OAUTH = "oauth"
    API_KEY = "api_key"
    NONE = "none"


class LogLevel(str, Enum):
    """Logging levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ServerConfig(BaseModel):
    """Server configuration settings."""

    host: str = Field(default="127.0.0.1", description="Server host address")
    port: int = Field(default=8000, description="Server port number")
    workers: int = Field(default=1, description="Number of worker processes")
    reload: bool = Field(
        default=False, description="Enable auto-reload for development"
    )

    @field_validator("port")
    @classmethod
    def validate_port(cls, v):
        if not 1 <= v <= 65535:
            raise ValueError("Port must be between 1 and 65535")
        return v


class AuthConfig(BaseModel):
    """Authentication configuration settings."""

    mode: AuthMode = Field(default=AuthMode.OAUTH, description="Authentication mode")
    jwt_secret_key: str = Field(
        default="change-in-production", description="JWT secret key"
    )
    jwt_algorithm: str = Field(default="HS256", description="JWT algorithm")
    access_token_expire_minutes: int = Field(
        default=30, description="Access token expiration"
    )
    refresh_token_expire_days: int = Field(
        default=7, description="Refresh token expiration"
    )
    api_key: Optional[str] = Field(
        default=None, description="API key for simple auth mode"
    )

    @field_validator("jwt_secret_key")
    @classmethod
    def validate_secret_key(cls, v):
        if v == "change-in-production":
            # Allow default in development, warn in production
            import warnings

            warnings.warn("Using default JWT secret key. Change for production!")
        return v


class LightRAGConfig(BaseModel):
    """LightRAG API client configuration."""

    base_url: str = Field(
        default="http://localhost:9621", description="LightRAG API base URL"
    )
    api_key: Optional[str] = Field(default=None, description="LightRAG API key")
    timeout: int = Field(default=30, description="Request timeout in seconds")
    max_retries: int = Field(default=3, description="Maximum retry attempts")

    # Authentication for LightRAG API
    username: str = Field(default="admin", description="LightRAG API username")
    password: str = Field(default="admin123", description="LightRAG API password")

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v):
        if not v.startswith(("http://", "https://")):
            raise ValueError("Base URL must start with http:// or https://")
        return v.rstrip("/")


class RedisConfig(BaseModel):
    """Redis configuration for caching and sessions."""

    url: str = Field(
        default="redis://localhost:6379", description="Redis connection URL"
    )
    password: Optional[str] = Field(default=None, description="Redis password")
    db: int = Field(default=0, description="Redis database number")
    max_connections: int = Field(default=10, description="Maximum connection pool size")

    # Session settings
    session_ttl: int = Field(default=3600, description="Session TTL in seconds")
    cache_ttl: int = Field(default=300, description="Cache TTL in seconds")

    @field_validator("db")
    @classmethod
    def validate_db(cls, v):
        if not 0 <= v <= 15:
            raise ValueError("Redis DB must be between 0 and 15")
        return v


class MCPConfig(BaseModel):
    """MCP protocol configuration."""

    protocol_version: str = Field(default="1.0", description="MCP protocol version")
    max_request_size: int = Field(
        default=1048576, description="Max request size in bytes"
    )  # 1MB
    request_timeout: int = Field(default=30, description="Request timeout in seconds")

    # Tool configuration
    enable_tools: bool = Field(default=True, description="Enable MCP tools")
    enable_resources: bool = Field(default=True, description="Enable MCP resources")
    enable_prompts: bool = Field(default=True, description="Enable MCP prompts")

    # Rate limiting
    rate_limit_per_minute: int = Field(
        default=60, description="Requests per minute per user"
    )

    @field_validator("max_request_size")
    @classmethod
    def validate_request_size(cls, v):
        if v > 10 * 1024 * 1024:  # 10MB max
            raise ValueError("Max request size cannot exceed 10MB")
        return v


class LoggingConfig(BaseModel):
    """Comprehensive logging configuration."""

    level: LogLevel = Field(default=LogLevel.INFO, description="Log level")

    # Format configurations
    format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="Log format string",
    )
    json_format: bool = Field(default=False, description="Use structured JSON logging")
    include_trace_id: bool = Field(default=True, description="Include trace ID in logs")

    # File logging
    file_enabled: bool = Field(default=False, description="Enable file logging")
    file_path: Optional[str] = Field(
        default="logs/mcp-server.log", description="Log file path"
    )
    max_file_size: int = Field(
        default=10485760, description="Max log file size in bytes"
    )  # 10MB
    backup_count: int = Field(default=5, description="Number of backup log files")

    # Error logging
    error_file_enabled: bool = Field(
        default=True, description="Enable separate error file logging"
    )
    error_file_path: Optional[str] = Field(
        default="logs/mcp-server-errors.log", description="Error log file path"
    )

    # Performance logging
    performance_enabled: bool = Field(
        default=False, description="Enable performance logging"
    )
    performance_file_path: Optional[str] = Field(
        default="logs/mcp-performance.log", description="Performance log file path"
    )
    slow_query_threshold: float = Field(
        default=1.0, description="Slow query threshold in seconds"
    )

    # Access logging
    access_log_enabled: bool = Field(default=True, description="Enable access logging")
    access_log_path: Optional[str] = Field(
        default="logs/mcp-access.log", description="Access log file path"
    )
    access_log_format: str = Field(
        default='%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s',
        description="Access log format (Apache combined format)",
    )

    # Security logging
    security_log_enabled: bool = Field(
        default=True, description="Enable security event logging"
    )
    security_log_path: Optional[str] = Field(
        default="logs/mcp-security.log", description="Security log file path"
    )

    # Third-party library logging
    suppress_noisy_loggers: bool = Field(
        default=True, description="Suppress noisy third-party loggers"
    )
    third_party_level: LogLevel = Field(
        default=LogLevel.WARNING, description="Third-party library log level"
    )

    @field_validator("slow_query_threshold")
    @classmethod
    def validate_threshold(cls, v):
        if v < 0.1:
            raise ValueError("Slow query threshold must be at least 0.1 seconds")
        return v


class Settings(BaseSettings):
    """Main application settings with environment variable support."""

    # Environment
    environment: Environment = Field(default=Environment.DEVELOPMENT, env="ENVIRONMENT")
    debug: bool = Field(default=False, env="DEBUG")

    # Application metadata
    app_name: str = Field(default="LightRAG MCP Server", env="APP_NAME")
    app_version: str = Field(default="0.1.0", env="APP_VERSION")

    # Configuration sections
    server: ServerConfig = Field(default_factory=ServerConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    lightrag: LightRAGConfig = Field(default_factory=LightRAGConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    mcp: MCPConfig = Field(default_factory=MCPConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    # CORS settings
    cors_origins: Union[str, List[str]] = Field(default=["*"], env="CORS_ORIGINS")
    cors_allow_credentials: bool = Field(default=True, env="CORS_ALLOW_CREDENTIALS")

    class Config:
        """Pydantic configuration."""

        env_file = [".env.mcp", ".env.mcp.local", ".env.mcp.production"]
        env_file_encoding = "utf-8"
        env_nested_delimiter = "__"
        case_sensitive = False
        extra = "ignore"  # Ignore extra environment variables

        # Environment variable examples:
        # SERVER__HOST=0.0.0.0
        # AUTH__MODE=oauth
        # LIGHTRAG__BASE_URL=https://api.lightrag.com
        # REDIS__URL=redis://redis:6379

    @model_validator(mode="after")
    def validate_environment_specific_settings(self):
        """Validate settings based on environment."""
        if self.environment == Environment.PRODUCTION:
            # Production validations
            if self.debug:
                raise ValueError("Debug mode cannot be enabled in production")

            if self.server.reload:
                raise ValueError("Auto-reload cannot be enabled in production")

            # Ensure secure settings
            if self.auth.jwt_secret_key == "change-in-production":
                raise ValueError("Must set custom JWT secret key in production")

        elif self.environment == Environment.DEVELOPMENT:
            # Development optimizations
            if not hasattr(self, "_development_optimized"):
                self.server.reload = True
                self.debug = True
                self._development_optimized = True

        return self

    def get_cors_origins(self) -> List[str]:
        """Get CORS origins as a list."""
        if isinstance(self.cors_origins, str):
            return [origin.strip() for origin in self.cors_origins.split(",")]
        return self.cors_origins

    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.environment == Environment.DEVELOPMENT

    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.environment == Environment.PRODUCTION

    def get_log_config(self) -> Dict[str, Any]:
        """Get comprehensive logging configuration dictionary."""
        # Base formatters
        formatters = {
            "standard": {"format": self.logging.format},
            "detailed": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(funcName)s - %(message)s"
            },
            "security": {
                "format": "%(asctime)s - SECURITY - %(levelname)s - %(message)s"
            },
            "performance": {"format": "%(asctime)s - PERF - %(message)s"},
        }

        # Add JSON formatter if enabled
        if self.logging.json_format:
            formatters["json"] = {
                "class": "pythonjsonlogger.jsonlogger.JsonFormatter",
                "format": "%(asctime)s %(name)s %(levelname)s %(filename)s %(lineno)d %(funcName)s %(message)s",
            }

        # Base handlers
        handlers = {
            "console": {
                "level": self.logging.level.value,
                "class": "logging.StreamHandler",
                "formatter": "json" if self.logging.json_format else "standard",
            },
        }

        # Ensure log directories exist
        self._ensure_log_directories()

        # File handler
        if self.logging.file_enabled and self.logging.file_path:
            handlers["file"] = {
                "level": self.logging.level.value,
                "class": "logging.handlers.RotatingFileHandler",
                "filename": self.logging.file_path,
                "maxBytes": self.logging.max_file_size,
                "backupCount": self.logging.backup_count,
                "formatter": "json" if self.logging.json_format else "detailed",
            }

        # Error file handler
        if self.logging.error_file_enabled and self.logging.error_file_path:
            handlers["error_file"] = {
                "level": "ERROR",
                "class": "logging.handlers.RotatingFileHandler",
                "filename": self.logging.error_file_path,
                "maxBytes": self.logging.max_file_size,
                "backupCount": self.logging.backup_count,
                "formatter": "json" if self.logging.json_format else "detailed",
            }

        # Performance file handler
        if self.logging.performance_enabled and self.logging.performance_file_path:
            handlers["performance_file"] = {
                "level": "INFO",
                "class": "logging.handlers.RotatingFileHandler",
                "filename": self.logging.performance_file_path,
                "maxBytes": self.logging.max_file_size,
                "backupCount": self.logging.backup_count,
                "formatter": "performance",
            }

        # Access log handler
        if self.logging.access_log_enabled and self.logging.access_log_path:
            handlers["access_file"] = {
                "level": "INFO",
                "class": "logging.handlers.RotatingFileHandler",
                "filename": self.logging.access_log_path,
                "maxBytes": self.logging.max_file_size,
                "backupCount": self.logging.backup_count,
                "formatter": "standard",
            }

        # Security log handler
        if self.logging.security_log_enabled and self.logging.security_log_path:
            handlers["security_file"] = {
                "level": "INFO",
                "class": "logging.handlers.RotatingFileHandler",
                "filename": self.logging.security_log_path,
                "maxBytes": self.logging.max_file_size,
                "backupCount": self.logging.backup_count,
                "formatter": "security",
            }

        # Determine base handlers for application loggers
        base_handlers = ["console"]
        if self.logging.file_enabled:
            base_handlers.append("file")
        if self.logging.error_file_enabled:
            base_handlers.append("error_file")

        # Configure loggers
        loggers = {
            "": {  # Root logger
                "handlers": base_handlers,
                "level": self.logging.level.value,
                "propagate": False,
            },
            "lightrag_mcp": {
                "handlers": base_handlers,
                "level": self.logging.level.value,
                "propagate": False,
            },
            "lightrag_mcp.auth": {
                "handlers": base_handlers
                + (["security_file"] if self.logging.security_log_enabled else []),
                "level": self.logging.level.value,
                "propagate": False,
            },
            "lightrag_mcp.performance": {
                "handlers": ["console"]
                + (["performance_file"] if self.logging.performance_enabled else []),
                "level": "INFO",
                "propagate": False,
            },
            "uvicorn.access": {
                "handlers": ["console"]
                + (["access_file"] if self.logging.access_log_enabled else []),
                "level": "INFO",
                "propagate": False,
            },
        }

        # Suppress noisy third-party loggers if enabled
        if self.logging.suppress_noisy_loggers:
            noisy_loggers = [
                "httpx",
                "httpcore",
                "urllib3",
                "requests",
                "asyncio",
                "multipart",
                "starlette",
                "fastapi",
            ]
            for logger_name in noisy_loggers:
                loggers[logger_name] = {
                    "level": self.logging.third_party_level.value,
                    "propagate": False,
                }

        config = {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": formatters,
            "handlers": handlers,
            "loggers": loggers,
        }

        return config

    def _ensure_log_directories(self) -> None:
        """Ensure all log directories exist."""
        log_paths = [
            self.logging.file_path,
            self.logging.error_file_path,
            self.logging.performance_file_path,
            self.logging.access_log_path,
            self.logging.security_log_path,
        ]

        for log_path in log_paths:
            if log_path:
                log_dir = Path(log_path).parent
                log_dir.mkdir(parents=True, exist_ok=True)


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get application settings instance."""
    return settings


def reload_settings() -> Settings:
    """Reload settings from environment."""
    global settings
    settings = Settings()
    return settings
