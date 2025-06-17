"""
Shared fixtures for API tests.

This module provides common fixtures and utilities for testing
LightRAG API endpoints.
"""

import pytest
from unittest.mock import Mock, AsyncMock
from typing import Dict, List, Any
from fastapi import FastAPI
from fastapi.testclient import TestClient

from lightrag import LightRAG
from lightrag.base import DocProcessingStatus, DocStatus
from lightrag.api.routers.document_routes import create_document_routes, DocumentManager
from lightrag.api.routers.query_routes import create_query_routes


@pytest.fixture
def mock_lightrag():
    """Create a mock LightRAG instance with all necessary methods."""
    rag = Mock(spec=LightRAG)
    
    # Mock async methods for document operations
    rag.aget_docs_by_ids = AsyncMock()
    rag.aget_chunks_by_doc_id = AsyncMock()
    rag.get_docs_by_status = AsyncMock()
    
    # Mock async methods for query operations
    rag.aquery = AsyncMock()
    rag.aget_relationships_for_query = AsyncMock()
    
    # Mock other methods
    rag.aclear_cache = AsyncMock()
    
    return rag


@pytest.fixture
def mock_document_manager():
    """Create a mock DocumentManager instance."""
    manager = Mock(spec=DocumentManager)
    manager.is_supported_file = Mock(return_value=True)
    manager.input_dir = Mock()
    manager.supported_extensions = (
        ".txt", ".pdf", ".docx", ".pptx", ".xlsx", 
        ".html", ".md", ".json", ".csv"
    )
    return manager


@pytest.fixture
def test_app(mock_lightrag, mock_document_manager):
    """Create a test FastAPI application with both document and query routes."""
    app = FastAPI()
    
    # Add document routes
    doc_router = create_document_routes(mock_lightrag, mock_document_manager, api_key=None)
    app.include_router(doc_router, prefix="/documents")
    
    # Add query routes
    query_router = create_query_routes(mock_lightrag, api_key=None)
    app.include_router(query_router)
    
    return app, mock_lightrag, mock_document_manager


@pytest.fixture
def test_client(test_app):
    """Create a test client for the FastAPI application."""
    app, mock_rag, mock_doc_manager = test_app
    return TestClient(app), mock_rag, mock_doc_manager


@pytest.fixture
def sample_document() -> DocProcessingStatus:
    """Create a sample document for testing."""
    return DocProcessingStatus(
        content="This is a sample document content for testing purposes.",
        content_summary="This is a sample...",
        content_length=57,
        file_path="sample.txt",
        status=DocStatus.PROCESSED,
        created_at="2025-01-01T00:00:00Z",
        updated_at="2025-01-01T00:00:00Z",
        chunks_count=2,
        metadata={"author": "test", "category": "sample"},
        mime_type="text/plain"
    )


@pytest.fixture
def sample_chunks() -> List[Dict[str, Any]]:
    """Create sample chunks for testing."""
    return [
        {
            "id": "chunk_001",
            "content": "This is the first chunk of the document.",
            "tokens": 10,
            "chunk_order_index": 0,
            "full_doc_id": "doc_123",
            "file_path": "sample.txt"
        },
        {
            "id": "chunk_002",
            "content": "This is the second chunk of the document.",
            "tokens": 11,
            "chunk_order_index": 1,
            "full_doc_id": "doc_123",
            "file_path": "sample.txt"
        }
    ]


@pytest.fixture
def sample_relationships() -> List[Dict[str, Any]]:
    """Create sample relationships for testing."""
    return [
        {
            "source": "Machine Learning",
            "target": "Artificial Intelligence",
            "relationship": "is a subset of",
            "weight": 0.9,
            "description": "Machine Learning is a subset of Artificial Intelligence"
        },
        {
            "source": "Deep Learning",
            "target": "Machine Learning",
            "relationship": "is a type of",
            "weight": 0.8,
            "description": "Deep Learning is a type of Machine Learning"
        }
    ]


@pytest.fixture
def sample_query_response() -> str:
    """Create a sample query response for testing."""
    return """Machine Learning is a subset of Artificial Intelligence that enables computers to learn and make decisions from data without being explicitly programmed. It involves algorithms that can identify patterns, make predictions, and improve their performance over time."""


@pytest.fixture(scope="session")
def test_file_types():
    """Provide a list of file types for MIME type testing."""
    return {
        "text/plain": [".txt", ".log", ".conf"],
        "application/pdf": [".pdf"],
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
        "application/vnd.openxmlformats-officedocument.presentationml.presentation": [".pptx"],
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
        "text/html": [".html", ".htm"],
        "text/css": [".css"],
        "application/javascript": [".js"],
        "application/json": [".json"],
        "application/xml": [".xml"],
        "text/csv": [".csv"],
        "text/markdown": [".md"],
        "text/x-python": [".py"],
        "text/x-java": [".java"],
        "text/x-c": [".c"],
        "text/x-c++": [".cpp"],
        "application/typescript": [".ts"],
    }


@pytest.fixture
def mock_error_scenarios():
    """Provide common error scenarios for testing."""
    return {
        "document_not_found": {"status_code": 404, "detail": "Document not found"},
        "chunks_not_found": {"status_code": 404, "detail": "No chunks found"},
        "internal_error": {"status_code": 500, "detail": "Internal server error"},
        "database_error": {"status_code": 500, "detail": "Database connection failed"},
        "invalid_params": {"status_code": 422, "detail": "Invalid parameters"},
    }


class MockAsyncGenerator:
    """Helper class for mocking async generators in streaming responses."""
    
    def __init__(self, items: List[str]):
        self.items = items
        self.index = 0
    
    def __aiter__(self):
        return self
    
    async def __anext__(self):
        if self.index >= len(self.items):
            raise StopAsyncIteration
        item = self.items[self.index]
        self.index += 1
        return item


@pytest.fixture
def mock_async_generator_factory():
    """Factory for creating mock async generators."""
    return MockAsyncGenerator


# Mark all tests in this directory as API tests
pytestmark = pytest.mark.api 