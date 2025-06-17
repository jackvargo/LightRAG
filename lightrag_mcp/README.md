# LightRAG MCP Server

A Model Context Protocol (MCP) server that provides intelligent access to LightRAG knowledge graphs through standardized MCP tools and resources.

## Overview

This package enables AI agents and applications to interact with LightRAG's powerful knowledge graph capabilities via the MCP protocol, providing:

- **Context Management**: Switch between different knowledge contexts
- **Semantic Search**: Find concepts, relationships, and documents
- **Query Processing**: Support for multiple query modes (naive, local, global, hybrid)
- **Document Access**: Retrieve full documents and processed chunks
- **Authentication**: OAuth 2.1 security with session management

## Installation

```bash
# Install with UV (recommended)
uv add lightrag-mcp-server

# Install with pip
pip install lightrag-mcp-server
```

## Quick Start

```python
from lightrag_mcp import MCPServer

# Initialize the MCP server
server = MCPServer()

# Start the server
server.run()
```

## Development

This package is part of the LightRAG project and requires Python 3.10+.

## License

MIT License - see LICENSE file for details. 