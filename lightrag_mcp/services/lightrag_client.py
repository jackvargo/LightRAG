"""
LightRAG MCP Server - LightRAG API Client

This module provides a comprehensive HTTP client for communicating with the LightRAG API,
including authentication, error handling, retry logic, and all necessary endpoints.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union

import httpx
from httpx import HTTPError, Response, Timeout
from pydantic import BaseModel

from ..config import LightRAGConfig, Settings, get_settings

logger = logging.getLogger(__name__)


class LightRAGError(Exception):
    """Base exception for LightRAG API errors."""

    pass


class AuthenticationError(LightRAGError):
    """Authentication with LightRAG API failed."""

    pass


class APIError(LightRAGError):
    """Generic LightRAG API error."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_data: Optional[Dict] = None,
    ):
        self.status_code = status_code
        self.response_data = response_data
        super().__init__(message)


class TimeoutError(LightRAGError):
    """Request timeout error."""

    pass


class RetryableError(LightRAGError):
    """Error that can be retried."""

    pass


class QueryRequest(BaseModel):
    """Request model for LightRAG queries."""

    query: str
    mode: str = "hybrid"  # naive, local, global, hybrid, mix
    only_need_context: bool = False
    response_type: str = "Multiple Paragraphs"


class QueryResponse(BaseModel):
    """Response model for LightRAG queries."""

    response: str
    sources: Optional[List[Dict[str, Any]]] = None
    relationships: Optional[List[Dict[str, Any]]] = None
    metadata: Optional[Dict[str, Any]] = None


class DocumentStatus(BaseModel):
    """Document status model."""

    doc_id: str
    filename: str
    status: str
    file_size: Optional[int] = None
    upload_time: Optional[str] = None
    processed_time: Optional[str] = None
    error_message: Optional[str] = None
    mime_type: Optional[str] = None
    file_path: Optional[str] = None


class ContextInfo(BaseModel):
    """Context information model."""

    name: str
    description: Optional[str] = None
    created_at: Optional[str] = None
    documents_count: int = 0
    status: str = "active"


class LightRAGClient:
    """
    Asynchronous HTTP client for LightRAG API with authentication and error handling.
    """

    def __init__(self, config: Union[Settings, LightRAGConfig, None] = None):
        """Initialize the LightRAG client."""
        if config is None:
            self.settings = get_settings()
            lightrag_config = self.settings.lightrag
        elif isinstance(config, Settings):
            self.settings = config
            lightrag_config = config.lightrag
        elif isinstance(config, LightRAGConfig):
            lightrag_config = config
            self.settings = None
        else:
            raise ValueError("config must be Settings, LightRAGConfig, or None")

        self.base_url = lightrag_config.base_url
        self.username = lightrag_config.username
        self.password = lightrag_config.password
        self.timeout = lightrag_config.timeout
        self.max_retries = lightrag_config.max_retries

        # Authentication state
        self._auth_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None
        self._client: Optional[httpx.AsyncClient] = None

        logger.info(f"Initialized LightRAG client for {self.base_url}")

    async def __aenter__(self):
        """Async context manager entry."""
        await self._ensure_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def _ensure_client(self):
        """Ensure HTTP client is initialized."""
        if self._client is None:
            timeout = Timeout(
                connect=10.0, read=self.timeout, write=self.timeout, pool=self.timeout
            )

            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=timeout,
                headers={"User-Agent": "LightRAG-MCP-Client/1.0"},
            )

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _authenticate(self) -> str:
        """Authenticate with LightRAG API and get access token."""
        await self._ensure_client()

        auth_data = {"username": self.username, "password": self.password}

        try:
            logger.debug("Authenticating with LightRAG API")
            response = await self._client.post("/auth/login", json=auth_data)

            if response.status_code == 200:
                token_data = response.json()
                self._auth_token = token_data.get("access_token")

                # Calculate token expiration (default 30 minutes)
                expires_in = token_data.get("expires_in", 1800)  # 30 minutes default
                self._token_expires_at = datetime.now() + timedelta(
                    seconds=expires_in - 60
                )  # 1 minute buffer

                logger.info("Successfully authenticated with LightRAG API")
                return self._auth_token
            else:
                raise AuthenticationError(
                    f"Authentication failed: {response.status_code}"
                )

        except HTTPError as e:
            raise AuthenticationError(f"Authentication request failed: {e}")

    async def _get_auth_token(self) -> str:
        """Get valid authentication token, refreshing if necessary."""
        if (
            not self._auth_token
            or not self._token_expires_at
            or datetime.now() >= self._token_expires_at
        ):

            await self._authenticate()

        return self._auth_token

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        json: Optional[Dict] = None,
        params: Optional[Dict] = None,
        files: Optional[Dict] = None,
        authenticated: bool = True,
    ) -> Response:
        """Make HTTP request with authentication and retry logic."""
        await self._ensure_client()

        # Prepare headers
        headers = {}
        if authenticated:
            token = await self._get_auth_token()
            headers["Authorization"] = f"Bearer {token}"

        # Prepare request args
        request_kwargs = {"headers": headers, "params": params or {}}

        if files:
            request_kwargs["files"] = files
            if data:
                request_kwargs["data"] = data
        elif json:
            request_kwargs["json"] = json
        elif data:
            request_kwargs["data"] = data

        # Retry logic
        last_exception = None
        for attempt in range(self.max_retries + 1):
            try:
                if attempt > 0:
                    wait_time = min(2**attempt, 10)  # Exponential backoff, max 10s
                    logger.debug(
                        f"Retrying request after {wait_time}s (attempt {attempt + 1})"
                    )
                    await asyncio.sleep(wait_time)

                response = await self._client.request(
                    method, endpoint, **request_kwargs
                )

                # Handle authentication errors
                if response.status_code == 401 and authenticated:
                    logger.warning("Authentication expired, refreshing token")
                    self._auth_token = None
                    self._token_expires_at = None
                    if attempt < self.max_retries:
                        continue  # Retry with new token

                # Handle server errors (5xx) as retryable
                if 500 <= response.status_code < 600 and attempt < self.max_retries:
                    logger.warning(f"Server error {response.status_code}, retrying...")
                    continue

                return response

            except httpx.TimeoutException as e:
                last_exception = TimeoutError(f"Request timeout: {e}")
                if attempt < self.max_retries:
                    logger.warning(
                        f"Request timeout, retrying... (attempt {attempt + 1})"
                    )
                    continue

            except httpx.HTTPError as e:
                last_exception = RetryableError(f"HTTP error: {e}")
                if attempt < self.max_retries:
                    logger.warning(f"HTTP error, retrying... (attempt {attempt + 1})")
                    continue

        # All retries exhausted
        if last_exception:
            raise last_exception
        else:
            raise APIError("Max retries exhausted")

    def _handle_response(self, response: Response) -> Dict[str, Any]:
        """Handle HTTP response and extract data."""
        try:
            if response.status_code == 200:
                return response.json() if response.content else {}
            elif response.status_code == 204:
                return {}
            else:
                error_data = {}
                try:
                    error_data = response.json()
                except:
                    pass

                error_msg = error_data.get("detail", f"HTTP {response.status_code}")
                raise APIError(error_msg, response.status_code, error_data)

        except ValueError as e:
            raise APIError(f"Invalid JSON response: {e}", response.status_code)

    # Authentication Methods

    async def authenticate(self) -> str:
        """Manually authenticate with LightRAG API and return access token."""
        return await self._authenticate()

    @property
    def access_token(self) -> Optional[str]:
        """Get current access token."""
        return self._auth_token

    @property
    def session(self) -> Optional[httpx.AsyncClient]:
        """Get current HTTP session."""
        return self._client

    # Health and Status Methods

    async def health_check(self) -> Dict[str, Any]:
        """Check LightRAG API health."""
        response = await self._make_request("GET", "/health", authenticated=False)
        return self._handle_response(response)

    async def get_status(self) -> Dict[str, Any]:
        """Get LightRAG API status."""
        response = await self._make_request("GET", "/status")
        return self._handle_response(response)

    # Context Management Methods

    async def list_contexts(self) -> Dict[str, Any]:
        """List available contexts."""
        response = await self._make_request("GET", "/contexts")
        return self._handle_response(response)

    async def get_context(self, context_name: str) -> Dict[str, Any]:
        """Get information about a specific context."""
        response = await self._make_request("GET", f"/contexts/{context_name}")
        return self._handle_response(response)

    async def switch_context(self, context_name: str) -> Dict[str, Any]:
        """Switch to a different context."""
        response = await self._make_request("POST", f"/contexts/{context_name}/switch")
        return self._handle_response(response)

    async def get_current_context(self) -> str:
        """Get current active context."""
        response = await self._make_request("GET", "/contexts/current")
        data = self._handle_response(response)
        return data.get("context", "default")

    # Document Management Methods

    async def list_documents(self) -> Dict[str, Any]:
        """List all documents in current context."""
        response = await self._make_request("GET", "/documents")
        return self._handle_response(response)

    async def get_document_status(self, doc_id: str) -> DocumentStatus:
        """Get status of a specific document."""
        response = await self._make_request("GET", f"/documents/{doc_id}/status")
        data = self._handle_response(response)
        return DocumentStatus(**data)

    async def get_document_content(self, doc_id: str) -> Dict[str, Any]:
        """Get full content of a document."""
        response = await self._make_request("GET", f"/documents/{doc_id}/content")
        return self._handle_response(response)

    async def get_document_chunks(self, doc_id: str) -> List[Dict[str, Any]]:
        """Get processed chunks of a document."""
        response = await self._make_request("GET", f"/documents/{doc_id}/chunks")
        data = self._handle_response(response)
        return data.get("chunks", [])

    async def upload_document(self, file_path: str, filename: str) -> DocumentStatus:
        """Upload a document to LightRAG."""
        with open(file_path, "rb") as f:
            files = {"file": (filename, f, "application/octet-stream")}
            response = await self._make_request(
                "POST", "/documents/upload", files=files
            )

        data = self._handle_response(response)
        return DocumentStatus(**data)

    async def delete_document(self, doc_id: str) -> Dict[str, Any]:
        """Delete a document."""
        response = await self._make_request("DELETE", f"/documents/{doc_id}")
        return self._handle_response(response)

    # Query Methods

    async def query(
        self,
        query: str,
        mode: str = "hybrid",
        only_need_context: bool = False,
        response_type: str = "Multiple Paragraphs",
        include_relationships: bool = False,
    ) -> Dict[str, Any]:
        """Execute a query against the knowledge graph."""
        query_data = {
            "query": query,
            "mode": mode,
            "only_need_context": only_need_context,
            "response_type": response_type,
            "include_relationships": include_relationships,
        }

        response = await self._make_request("POST", "/query", json=query_data)
        return self._handle_response(response)

    async def search_documents(
        self, query: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Search documents by content."""
        params = {"query": query, "limit": limit}
        response = await self._make_request("GET", "/search/documents", params=params)
        data = self._handle_response(response)
        return data.get("results", [])

    # Graph Methods

    async def get_graph_info(self) -> Dict[str, Any]:
        """Get information about the knowledge graph."""
        response = await self._make_request("GET", "/graph/info")
        return self._handle_response(response)

    async def get_relationships(
        self, entity: str, depth: int = 1
    ) -> List[Dict[str, Any]]:
        """Get relationships for an entity."""
        params = {"entity": entity, "depth": depth}
        response = await self._make_request(
            "GET", "/graph/relationships", params=params
        )
        data = self._handle_response(response)
        return data.get("relationships", [])

    async def explore_graph(self, start_entity: str, depth: int = 1) -> Dict[str, Any]:
        """Explore the knowledge graph from a starting entity."""
        params = {"start_entity": start_entity, "depth": depth}
        response = await self._make_request("GET", "/graph/explore", params=params)
        return self._handle_response(response)

    # Utility Methods

    async def clear_cache(self) -> Dict[str, Any]:
        """Clear the LightRAG cache."""
        response = await self._make_request("POST", "/cache/clear")
        return self._handle_response(response)

    async def get_statistics(self) -> Dict[str, Any]:
        """Get LightRAG statistics."""
        response = await self._make_request("GET", "/statistics")
        return self._handle_response(response)


# Singleton client instance
_client_instance: Optional[LightRAGClient] = None


def get_lightrag_client(settings: Optional[Settings] = None) -> LightRAGClient:
    """Get singleton LightRAG client instance."""
    global _client_instance
    if _client_instance is None:
        _client_instance = LightRAGClient(settings)
    return _client_instance


async def close_lightrag_client():
    """Close the singleton LightRAG client."""
    global _client_instance
    if _client_instance:
        await _client_instance.close()
        _client_instance = None
