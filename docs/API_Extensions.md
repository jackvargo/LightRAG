# LightRAG API Extensions for MCP Server Capability

This document describes the API extensions added to LightRAG to support MCP (Model Context Protocol) server capabilities. These extensions provide enhanced document content retrieval, chunk access, and relationship data for graph exploration.

## Table of Contents

1. [Document Content Retrieval](#document-content-retrieval)
2. [Chunk Retrieval Endpoints](#chunk-retrieval-endpoints)
3. [Enhanced Query Endpoints](#enhanced-query-endpoints)
4. [Document Status Extensions](#document-status-extensions)
5. [Error Handling](#error-handling)
6. [Usage Examples](#usage-examples)

## Document Content Retrieval

### GET `/documents/{doc_id}/content`

Retrieves the actual file content for a document, serving the original file when available or falling back to stored content.

#### Parameters

- `doc_id` (path, required): The document ID to retrieve content for

#### Response

- **Content-Type**: Detected from file extension (e.g., `text/plain`, `application/pdf`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document`)
- **Content-Length**: File size in bytes
- **Content-Disposition**: `attachment; filename="original_filename.ext"`

#### Features

- **File System Integration**: Serves actual files from the document's original location
- **Context Input Directory Resolution**: Automatically resolves file paths using the current context's input directory
- **File Size Protection**: Files larger than 100MB fall back to stored content to prevent memory issues
- **Streaming Response**: Large files are streamed in chunks to optimize memory usage
- **Fallback Behavior**: If the original file is not found, returns the stored document content
- **MIME Type Detection**: Automatically detects and sets appropriate Content-Type headers

#### Response Codes

- `200 OK`: File content returned successfully
- `404 Not Found`: Document ID not found
- `500 Internal Server Error`: File access error or server error

#### Example

```bash
GET /documents/doc_123/content
```

```http
HTTP/1.1 200 OK
Content-Type: application/pdf
Content-Length: 2048576
Content-Disposition: attachment; filename="research_paper.pdf"

[PDF binary content]
```

## Chunk Retrieval Endpoints

### GET `/chunks/{chunk_id}`

Retrieves a single chunk by its ID with complete metadata.

#### Parameters

- `chunk_id` (path, required): The chunk ID to retrieve

#### Response

```json
{
  "id": "chunk_456",
  "content": "This is the chunk content with metadata",
  "tokens": 25,
  "chunk_order_index": 2,
  "full_doc_id": "doc_456",
  "file_path": "/path/to/document.pdf"
}
```

#### Response Fields

- `id`: The chunk identifier
- `content`: The actual text content of the chunk
- `tokens`: Number of tokens in the chunk
- `chunk_order_index`: Position of this chunk within the document (0-based)
- `full_doc_id`: ID of the parent document
- `file_path`: Original file path of the source document

#### Response Codes

- `200 OK`: Chunk retrieved successfully
- `404 Not Found`: Chunk ID not found

### GET `/chunks?chunk_ids={id1,id2,id3}`

Retrieves multiple chunks in a single request for efficient bulk access.

#### Parameters

- `chunk_ids` (query, required): Comma-separated list of chunk IDs

#### Validation Rules

- Maximum 50 chunk IDs per request
- Each chunk ID must be ≤ 255 characters
- `chunk_ids` parameter cannot be empty

#### Response

```json
[
  {
    "id": "chunk_1",
    "content": "First chunk content",
    "tokens": 20,
    "chunk_order_index": 0,
    "full_doc_id": "doc_123",
    "file_path": "/docs/file1.txt"
  },
  {
    "id": "chunk_2",
    "content": "Second chunk content",
    "tokens": 22,
    "chunk_order_index": 1,
    "full_doc_id": "doc_123",
    "file_path": "/docs/file1.txt"
  }
]
```

#### Response Codes

- `200 OK`: Chunks retrieved successfully (only valid chunks returned)
- `400 Bad Request`: Invalid parameters (too many IDs, empty list, ID too long)

#### Example

```bash
GET /chunks?chunk_ids=chunk_1,chunk_2,chunk_3
```

## Enhanced Query Endpoints

### POST `/query`

Enhanced query endpoint with optional relationship data inclusion.

#### Request Body

```json
{
  "query": "What is machine learning?",
  "mode": "hybrid",
  "include_relationships": true,
  "top_k": 10,
  "response_type": "Multiple Paragraphs"
}
```

#### New Parameters

- `include_relationships` (boolean, optional, default: false): Include relationship data in the response

#### Response with Relationships

```json
{
  "response": "Machine learning is a subset of artificial intelligence...",
  "relationships": [
    {
      "entity1": "Machine Learning",
      "entity2": "Python",
      "relationship": "implemented_in",
      "weight": 0.85,
      "source_id": "chunk_1||chunk_3||chunk_7",
      "chunk_ids": ["chunk_1", "chunk_3", "chunk_7"],
      "chunk_metadata": [
        {
          "chunk_id": "chunk_1",
          "full_doc_id": "doc_ml_guide",
          "file_path": "/guides/ml_guide.md",
          "tokens": 150,
          "chunk_order_index": 0
        }
      ]
    }
  ]
}
```

#### Relationship Fields

- `entity1`, `entity2`: The entities in the relationship
- `relationship`: Description of the relationship
- `weight`: Relationship strength (0.0 to 1.0)
- `source_id`: Pipe-delimited list of source chunk IDs
- `chunk_ids`: Array of chunk IDs that support this relationship
- `chunk_metadata`: Detailed metadata for chunks (subset of chunk_ids for performance)

### POST `/query/stream`

Streaming version of the query endpoint with relationship support.

#### Request Body

Same as `/query` endpoint.

#### Response

- **Content-Type**: `text/plain; charset=utf-8`
- **Transfer-Encoding**: `chunked`

When `include_relationships` is true, relationships are returned after the streaming response completes.

## Document Status Extensions

### GET `/documents/status`

Enhanced document status endpoint with file metadata.

#### Response

```json
[
  {
    "doc_id": "doc_123",
    "status": "completed",
    "file_path": "/docs/example.pdf",
    "mime_type": "application/pdf",
    "file_exists": true,
    "file_size": 2048576,
    "processed_at": "2024-01-15T10:30:00Z"
  }
]
```

#### New Fields

- `mime_type`: MIME type of the original file
- `file_exists`: Boolean indicating if the original file still exists
- `file_size`: Size of the original file in bytes

## Error Handling

### Standard Error Response

```json
{
  "detail": "Error description",
  "error_code": "SPECIFIC_ERROR_CODE",
  "context": {
    "additional": "error context"
  }
}
```

### Common Error Codes

- `DOCUMENT_NOT_FOUND`: Document ID does not exist
- `CHUNK_NOT_FOUND`: Chunk ID does not exist
- `FILE_ACCESS_ERROR`: Cannot access original file
- `VALIDATION_ERROR`: Request parameter validation failed
- `TOO_MANY_CHUNK_IDS`: Bulk request exceeds 50 chunk limit
- `CHUNK_ID_TOO_LONG`: Chunk ID exceeds 255 character limit

## Usage Examples

### MCP Graph Exploration Workflow

```python
# 1. Query with relationships
response = requests.post("/query", json={
    "query": "Explain machine learning concepts",
    "mode": "hybrid",
    "include_relationships": True
})

# 2. Extract chunk references from relationships
chunk_ids = []
for rel in response.json()["relationships"]:
    chunk_ids.extend(rel["chunk_ids"])

# 3. Retrieve full chunk content
chunks_response = requests.get(f"/chunks?chunk_ids={','.join(chunk_ids[:50])}")

# 4. Get original document content for specific chunks
for chunk in chunks_response.json():
    doc_content = requests.get(f"/documents/{chunk['full_doc_id']}/content")
```

### Document Content Retrieval

```python
# Check document status first
status_response = requests.get("/documents/status")
for doc in status_response.json():
    if doc["file_exists"] and doc["mime_type"] == "application/pdf":
        # Retrieve original PDF file
        content = requests.get(f"/documents/{doc['doc_id']}/content")
        with open(f"downloaded_{doc['doc_id']}.pdf", "wb") as f:
            f.write(content.content)
```

### Chunk-Based Analysis

```python
# Get chunks for a specific document
doc_chunks = requests.get(f"/documents/{doc_id}/chunks")

# Analyze chunk relationships
chunk_ids = [chunk["id"] for chunk in doc_chunks.json()]
chunks_data = requests.get(f"/chunks?chunk_ids={','.join(chunk_ids[:50])}")

# Process chunks in document order
sorted_chunks = sorted(chunks_data.json(), key=lambda x: x["chunk_order_index"])
```

## Performance Considerations

1. **File Size Limits**: Files larger than 100MB automatically fall back to stored content
2. **Chunk Bulk Limits**: Maximum 50 chunks per bulk request to prevent performance issues
3. **Streaming Responses**: Large files are streamed to optimize memory usage
4. **Relationship Metadata**: Only a subset of chunk metadata is included in relationship responses for performance

## Authentication

All endpoints require the same authentication as the base LightRAG API:

```bash
curl -H "Authorization: Bearer your-api-key" \
     -X GET http://localhost:9621/documents/doc_123/content
```

## Rate Limiting

The same rate limiting rules apply as the base LightRAG API. Consider implementing client-side caching for frequently accessed chunks and document content.
