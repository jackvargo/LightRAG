# Product Requirements Document: LightRAG MCP Server Capability

## Introduction/Overview

This document outlines the requirements for implementing a Model Context Protocol (MCP) server capability for LightRAG. The MCP server will provide developers and knowledge workers with seamless access to LightRAG's graph-based retrieval system through code development environments like Cursor, Claude Code, and GitHub Copilot.

The goal is to create an enhanced RAG tool that exposes proprietary documentation and institutional knowledge directly into the context window of agentic development tools, leveraging LightRAG's graph-based approach for superior information discovery compared to traditional RAG systems.

## Goals

1. **Developer Acceleration**: Enable developers to quickly research system capabilities, best practices, design patterns, and coding standards through their IDE
2. **Knowledge Accessibility**: Provide employees with easy access to project execution methodologies (SOPs) and "how-to" guidance
3. **Enhanced Context**: Deliver graph-based relationship discovery alongside traditional document retrieval for richer context
4. **Seamless Integration**: Offer native MCP protocol support for any compatible development environment
5. **Multi-Context Support**: Enable access to different knowledge repositories through LightRAG's existing multi-context capability

## User Stories

### Developer User Stories
- As a **software developer**, I want to search project documentation from within my IDE so that I can quickly understand system architecture without context switching
- As a **developer**, I want to explore entity relationships in our codebase documentation so that I can understand dependencies and design patterns
- As a **development team member**, I want to access different project contexts (frontend, backend, mobile) so that I can get relevant information for my current work
- As a **code reviewer**, I want to quickly retrieve full documentation sections so that I can verify implementation against standards
- As a **developer**, I want real-time streaming of search results so that I can see information as it becomes available

### Knowledge Worker User Stories
- As a **project manager**, I want to search SOPs and methodologies so that I can provide accurate guidance to team members
- As a **new employee**, I want to discover related processes and procedures so that I can understand the full context of my work
- As a **quality assurance specialist**, I want to access testing guidelines and standards so that I can ensure compliance

### System Administrator User Stories
- As a **system administrator**, I want to configure authentication and rate limiting so that I can control access to sensitive documentation
- As a **administrator**, I want to monitor MCP server usage so that I can optimize performance and identify bottlenecks

## Functional Requirements

### Core MCP Server Infrastructure
1. The system MUST implement a separate lightweight FastAPI service that communicates with the main LightRAG API
2. The system MUST support the full MCP specification including tools, resources, and prompts
3. The system MUST support both Server-Sent Events (SSE) and WebSocket communication protocols
4. The system MUST implement session-based response caching with configurable TTL
5. The system MUST provide configurable rate limiting per client/user

### Authentication & Security
6. The system MUST support user authentication using LightRAG's existing authentication system
7. The system MUST support token-based authentication for MCP clients
8. The system MUST validate client permissions before providing access to contexts

### Context Management
9. The system MUST support connection-level context configuration (set once per session)
10. The system MUST provide a `switch_context` tool for dynamic context switching during sessions
11. The system MUST provide a `list_contexts` tool that returns available contexts for the authenticated user
12. The system MUST provide a `get_context_info` tool that returns metadata and document count for a specific context

### Query and Search Tools
13. The system MUST provide a `query` tool with mode parameters (naive, local, global, hybrid, mix) for parameter-based access
14. The system MUST provide semantic tools by purpose (`find_concept`, `get_relationships`, `search_docs`) for intuitive access
15. The system MUST provide a `search_documents` tool that performs semantic search and returns snippets with source references
16. The system MUST provide a `get_full_document` tool that retrieves raw document content by document ID (requires Phase 1 LightRAG API)
17. The system MUST provide a `get_processed_chunks` tool that returns chunked/processed content (requires Phase 1 LightRAG API)
18. The system MUST provide a `get_summary` tool that returns chat-style summarized responses to queries

### Graph Exploration
19. The system MUST provide an `explore_graph` tool for entity and relationship exploration
20. All content retrieval tools MUST offer optional relationship "depth" parameters to include related entities and relationships
21. The system MUST return relationship data alongside content to minimize additional API calls

### Real-time Communication
22. The system MUST stream query results in real-time as they are processed by LightRAG
23. The system MUST provide status updates during long-running operations (especially context switching which involves storage reinitialization)
24. The system MUST support both SSE (for streaming results) and WebSocket (for bidirectional communication)

### Caching and Performance
25. The system MUST implement session-based caching to avoid redundant LightRAG API calls
26. The system MUST provide a `clear_cache` tool for explicit cache management
27. The system MUST set appropriate HTTP cache headers for client-side optimization

### Discovery and Help
28. The system MUST provide a discovery endpoint that describes all available tools, parameters, and capabilities
29. The system MUST provide a built-in `help` tool that explains query modes, best practices, and usage guidance
30. The system MUST return rich error messages with suggested alternatives when operations fail

### Content Access Levels
31. The system MUST support multiple content access levels: raw content, processed chunks, and summarized responses
32. The system MUST preserve source document references in all response types
33. The system MUST indicate content confidence levels and retrieval method used

## Non-Goals (Out of Scope)

- **Document Ingestion**: The MCP server will NOT provide document upload or ingestion capabilities (handled by LightRAG UI)
- **Context Creation**: The MCP server will NOT support creating new contexts or managing context configuration
- **Document Processing**: The MCP server will NOT handle expensive document processing operations
- **User Management**: The MCP server will NOT provide user creation or role management (delegated to main LightRAG system)
- **Advanced Scaling**: Initial implementation will target 10s of concurrent users, not enterprise-scale deployment
- **Custom LLM Integration**: The MCP server will NOT provide alternative LLM model configurations

## Design Considerations

### Service Architecture
- **Microservice Design**: Separate FastAPI service enables independent deployment and scaling
- **API Gateway Pattern**: All LightRAG communication goes through the main API to maintain consistency
- **Stateless Design**: Session data stored externally to enable horizontal scaling

### Protocol Implementation
- **MCP Compliance**: Full adherence to MCP specification for maximum client compatibility
- **WebSocket Management**: Connection pooling and cleanup for efficient resource usage
- **Error Handling**: Graceful degradation when LightRAG API is unavailable

### User Experience
- **Progressive Disclosure**: Simple tools for basic use cases, advanced parameters for power users
- **Contextual Help**: Built-in guidance helps LLM agents understand capabilities
- **Response Streaming**: Real-time feedback improves perceived performance

## Technical Considerations

### Dependencies
- **MCP Python SDK**: For protocol implementation and client communication
- **FastAPI**: For REST API and WebSocket support
- **Redis/Memory Store**: For session-based caching
- **HTTP Client**: For communication with main LightRAG API

### Integration Points
- **LightRAG API**: All document operations routed through existing REST endpoints
- **Authentication Service**: Leverage existing user authentication and token validation
- **Context Manager**: Interface with LightRAG's multi-context switching capability

### Performance Requirements
- **User Experience**: Provide real-time status updates and progress indicators for long-running operations to keep users informed
- **Concurrent Users**: Support 10-50 concurrent sessions initially
- **Cache Hit Ratio**: Target 60%+ cache hit ratio for repeated queries
- **Error Rate**: Maintain <1% error rate under normal load

### Deployment
- **Container Ready**: Docker container for consistent deployment
- **Configuration**: Environment-based configuration for different environments
- **Health Checks**: Comprehensive health monitoring for operational visibility

## Success Metrics

### Adoption Metrics
- **Active Users**: Number of developers actively using MCP integration weekly
- **Session Duration**: Average time developers spend in MCP-enhanced coding sessions
- **Query Volume**: Number of documentation queries per developer per day

### Performance Metrics
- **Response Time**: P95 response time for different query types
- **Cache Effectiveness**: Cache hit ratio and performance improvement from caching
- **Error Rate**: Percentage of failed requests and user-reported issues

### User Satisfaction
- **Developer Productivity**: Reduced time to find relevant documentation (measured via survey)
- **Context Switch Reduction**: Decreased need to leave development environment for documentation
- **Knowledge Discovery**: Increased discovery of related documentation through graph exploration

### Technical Metrics
- **API Utilization**: Usage patterns across different MCP tools
- **Context Switching**: Frequency and patterns of context changes
- **Relationship Exploration**: Usage of graph traversal features vs. traditional search

## Implementation Notes (Based on Current LightRAG API Analysis)

### **Current LightRAG API Capabilities Confirmed**
Based on codebase analysis, the following capabilities are available and can be leveraged:

1. **✅ Authentication**: JWT-based authentication with role-based access control already implemented
2. **✅ Context Management**: Full context switching, listing, creation, deletion, and statistics
3. **✅ Query Modes**: All query modes (naive, local, global, hybrid, mix) with streaming support
4. **✅ Graph Exploration**: Graph label listing and knowledge graph retrieval with configurable depth and node limits
5. **✅ Document Management**: Upload, text insertion, batch processing, scanning, and status tracking
6. **✅ Pipeline Status**: Real-time processing status with detailed progress information
7. **✅ Cache Management**: Cache clearing by mode with existing cache infrastructure
8. **⚠️ Processed Chunks**: Text chunks are internally managed but not directly exposed via API endpoint
9. **❌ Document by ID Retrieval**: No direct document content retrieval by ID endpoint currently exists

### **Required LightRAG API Extensions**
To fully support the MCP server requirements, these endpoints need to be added to LightRAG:

1. **Document Content Retrieval**:
   - `GET /documents/{doc_id}/content` - retrieve raw document content with MIME type
   - Must return original file content with proper headers

2. **Processed Chunk Access**:
   - `GET /documents/{doc_id}/chunks` - retrieve processed text chunks as JSON array
   - Include chunk metadata (position, size, relationships)

3. **Enhanced Search**:
   - Modify existing search endpoints to return document IDs with content snippets
   - Include source document metadata in all search responses

4. **Relationship Data**:
   - Add optional `include_relationships` parameter to query endpoints
   - Return relationship depth data alongside content responses

### **MCP Server Architecture Decisions**

Based on current LightRAG capabilities and MCP specification research:

1. **✅ Separate FastAPI Service**: Maintains clean separation and enables independent scaling
2. **✅ Full MCP Specification Support**: Tools, Resources, and Prompts all valuable for developer workflows
3. **✅ OAuth 2.1 Authentication**: Aligns with MCP standard and LightRAG's existing JWT implementation
4. **✅ SSE/WebSocket Support**: MCP's Streamable HTTP approach confirmed compatible
5. **✅ Session-based Caching**: Redis implementation with connection-lifetime sessions
6. **✅ Rate Limiting**: Per-user/session as specified in user feedback

## Implementation Decisions (Finalized)

### **1. Relationship Depth Configuration**
- **Default**: Return single nearest nodes (depth=1)
- **Maximum**: Up to 5 nodes deep for relationship exploration
- **Implementation**: Configurable per query with reasonable defaults to prevent performance issues

### **2. Document ID Format**
- **Standard**: Use LightRAG's internal document status IDs directly
- **Benefit**: Maintains consistency with existing LightRAG API and reduces ID mapping complexity

### **3. Prompt Templates**
- **Configuration**: JSON-configurable at server level for organizational customization
- **Built-in Templates**:
  - Documentation search workflows
  - Architecture discovery patterns
  - Best practice validation prompts
  - Code review guidance templates
  - **User Story Context Builder**: Compile context relevant to new user stories and existing code elements

### **4. Error Recovery Strategy**
- **Approach**: Fail immediately with detailed, actionable error messages
- **Rationale**: Provides clear feedback for debugging and avoids hiding system issues behind queues

### **5. Cache Invalidation Strategy**
- **Context Switch**: Clear entire session cache when switching contexts
- **Manual Control**: Provide explicit cache clearing command/tool
- **Scope**: Session-based cache tied to connection lifetime

### **6. Resource Content Handling**
Following [MCP Resource Specification](https://modelcontextprotocol.io/specification/2025-03-26/server/resources):
- **Text Content**: Documents served as `text/plain` or appropriate MIME type with full content
- **Binary Content**: Files served as base64-encoded blobs with proper MIME types
- **Large Files**: Use standard HTTP content-length headers; chunking handled by MCP client
- **URI Scheme**: Use `file://` scheme for document resources as per MCP standard

## Implementation Phases

### **Phase 1: LightRAG API Extensions** (Separate Implementation)
Before implementing the MCP server, the following LightRAG API endpoints must be added:

1. **Document Content Retrieval**
   - `GET /documents/{doc_id}/content` - Raw document content
   - `GET /documents/{doc_id}/chunks` - Processed text chunks
   - Response includes MIME type and content length

2. **Enhanced Search with Document References**
   - Modify existing search to return document IDs with content snippets
   - Include source document metadata in search results

3. **Relationship Data in Query Responses**
   - Add optional `include_relationships` parameter to query endpoints
   - Return relationship depth data alongside content

4. **Document Metadata Enhancement**
   - Extend document status to include MIME types and file paths
   - Support for binary file handling and content type detection

### **Phase 2: MCP Server Implementation**
After Phase 1 is complete and tested:

1. **Core MCP Infrastructure** - OAuth 2.1, JSON-RPC, SSE/WebSocket
2. **Tool Implementation** - All specified MCP tools using enhanced LightRAG API
3. **Resource Implementation** - Document and chunk exposure as MCP resources
4. **Prompt Templates** - Configurable JSON-based prompt system
5. **Session Management** - Redis-based caching and session handling
