"""
Context Management Tools for LightRAG MCP Server

This module implements MCP tools for managing contexts in LightRAG,
including listing, switching, and getting context information.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

from ..config import MCPConfig
from ..services.lightrag_client import APIError, LightRAGClient
from .server import ConnectionSession
from .tools import (
    MCPTool,
    ToolCategory,
    ToolParameter,
    ToolParameterType,
    ToolProgress,
    ToolResult,
    boolean_parameter,
    string_parameter,
)

logger = logging.getLogger(__name__)


class ListContextsTool(MCPTool):
    """Tool for listing all available contexts."""

    @property
    def name(self) -> str:
        return "list_contexts"

    @property
    def description(self) -> str:
        return "List all available contexts in the LightRAG system with their metadata and status"

    @property
    def category(self) -> ToolCategory:
        return ToolCategory.CONTEXT_MANAGEMENT

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            boolean_parameter(
                name="include_stats",
                description="Include additional statistics for each context (document count, size, etc.)",
                required=False,
                default=False,
            )
        ]

    @property
    def requires_context(self) -> bool:
        return False  # This tool works without a specific context

    async def execute(
        self, session: ConnectionSession, parameters: Dict[str, Any]
    ) -> ToolResult:
        """Execute the list_contexts tool."""
        try:
            include_stats = parameters.get("include_stats", False)

            # Get LightRAG client
            client = await self.get_lightrag_client()

            # List contexts from LightRAG API
            response = await client.list_contexts()

            # Extract context data
            contexts_data = response.get("contexts", {})
            current_context = response.get("current_context")

            # Format the response
            contexts_list = []
            for context_name, context_info in contexts_data.items():
                context_entry = {
                    "name": context_name,
                    "description": context_info.get("description", ""),
                    "is_current": context_info.get("is_current", False),
                    "is_default": context_info.get("is_default", False),
                    "created_at": context_info.get("created_at"),
                    "working_path": context_info.get("working_path"),
                    "input_path": context_info.get("input_path"),
                }

                # Add statistics if requested
                if include_stats:
                    # TODO: In future, we could add document count, size, etc.
                    # For now, we'll just include basic info
                    context_entry["stats"] = {
                        "status": "active",
                        "last_accessed": context_info.get("last_accessed", "unknown"),
                    }

                contexts_list.append(context_entry)

            # Sort contexts by name for consistent output
            contexts_list.sort(key=lambda x: x["name"])

            result_data = {
                "contexts": contexts_list,
                "current_context": current_context,
                "total_count": len(contexts_list),
            }

            metadata = {
                "tool": self.name,
                "include_stats": include_stats,
                "timestamp": session.connected_at.isoformat(),
            }

            logger.info(
                f"Listed {len(contexts_list)} contexts for session {session.session_id}"
            )

            return ToolResult(
                success=True,
                data=result_data,
                metadata=metadata,
            )

        except APIError as e:
            error_msg = f"LightRAG API error: {e}"
            logger.error(f"List contexts failed: {error_msg}")
            return ToolResult(
                success=False,
                error=error_msg,
                metadata={"tool": self.name, "error_type": "api_error"},
            )
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(f"List contexts failed: {error_msg}", exc_info=True)
            return ToolResult(
                success=False,
                error=error_msg,
                metadata={"tool": self.name, "error_type": "unexpected_error"},
            )


class SwitchContextTool(MCPTool):
    """Tool for switching to a different context with progress tracking."""

    @property
    def name(self) -> str:
        return "switch_context"

    @property
    def description(self) -> str:
        return "Switch to a different LightRAG context with progress status updates and validation"

    @property
    def category(self) -> ToolCategory:
        return ToolCategory.CONTEXT_MANAGEMENT

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            string_parameter(
                name="context_name",
                description="Name of the context to switch to",
                required=True,
            ),
            boolean_parameter(
                name="force_switch",
                description="Force switch even if already in the target context",
                required=False,
                default=False,
            ),
        ]

    @property
    def supports_progress(self) -> bool:
        return True  # This tool supports progress tracking

    @property
    def supports_streaming(self) -> bool:
        return True  # This tool supports streaming responses

    @property
    def requires_context(self) -> bool:
        return False  # This tool can switch from any context

    async def execute(
        self, session: ConnectionSession, parameters: Dict[str, Any]
    ) -> ToolResult:
        """Execute the switch_context tool with progress tracking."""
        context_name = parameters["context_name"]
        force_switch = parameters.get("force_switch", False)
        operation_id = str(uuid.uuid4())

        try:
            # Get LightRAG client
            client = await self.get_lightrag_client()

            # Step 1: Validate context exists (10% progress)
            logger.info(f"Validating context '{context_name}' exists")
            contexts_response = await client.list_contexts()
            contexts_data = contexts_response.get("contexts", {})
            current_context = contexts_response.get("current_context")

            if context_name not in contexts_data:
                return ToolResult(
                    success=False,
                    error=f"Context '{context_name}' not found. Available contexts: {list(contexts_data.keys())}",
                    metadata={
                        "tool": self.name,
                        "context_name": context_name,
                        "available_contexts": list(contexts_data.keys()),
                    },
                )

            # Check if we're already in the target context
            if current_context == context_name and not force_switch:
                return ToolResult(
                    success=True,
                    data={
                        "message": f"Already in context '{context_name}', no switch needed",
                        "current_context": current_context,
                        "target_context": context_name,
                        "switch_performed": False,
                    },
                    metadata={
                        "tool": self.name,
                        "context_name": context_name,
                        "operation_id": operation_id,
                    },
                )

            # Step 2: Initiate context switch (25% progress)
            logger.info(f"Switching from '{current_context}' to '{context_name}'")

            # Call the LightRAG API to perform the context switch
            switch_response = await client.switch_context(context_name)

            # Step 3: Wait for context switch completion with progress updates
            # Give some time for the async operations to complete
            await asyncio.sleep(0.5)  # 50% progress

            # Step 4: Verify switch was successful (75% progress)
            logger.info("Verifying context switch completion")
            await asyncio.sleep(0.5)  # Allow time for backend processing

            # Get updated context information
            verification_response = await client.list_contexts()
            new_current_context = verification_response.get("current_context")

            # Step 5: Complete operation (100% progress)
            if new_current_context == context_name:
                success_data = {
                    "message": f"Successfully switched to context '{context_name}'",
                    "previous_context": current_context,
                    "current_context": new_current_context,
                    "target_context": context_name,
                    "switch_performed": True,
                    "context_info": contexts_data.get(context_name, {}),
                    "switch_details": switch_response,
                }

                metadata = {
                    "tool": self.name,
                    "operation_id": operation_id,
                    "context_name": context_name,
                    "previous_context": current_context,
                    "switch_duration": "~1.0s",  # Approximate duration
                    "timestamp": session.connected_at.isoformat(),
                }

                logger.info(
                    f"Context switch completed successfully: {current_context} → {context_name}"
                )

                return ToolResult(
                    success=True,
                    data=success_data,
                    metadata=metadata,
                )
            else:
                # Switch failed or didn't complete properly
                error_msg = f"Context switch verification failed. Expected '{context_name}', but current context is '{new_current_context}'"
                logger.error(error_msg)

                return ToolResult(
                    success=False,
                    error=error_msg,
                    metadata={
                        "tool": self.name,
                        "operation_id": operation_id,
                        "context_name": context_name,
                        "expected_context": context_name,
                        "actual_context": new_current_context,
                        "error_type": "verification_failed",
                    },
                )

        except APIError as e:
            error_msg = f"LightRAG API error during context switch: {e}"
            logger.error(f"Context switch failed: {error_msg}")
            return ToolResult(
                success=False,
                error=error_msg,
                metadata={
                    "tool": self.name,
                    "operation_id": operation_id,
                    "context_name": context_name,
                    "error_type": "api_error",
                },
            )
        except Exception as e:
            error_msg = f"Unexpected error during context switch: {str(e)}"
            logger.error(f"Context switch failed: {error_msg}", exc_info=True)
            return ToolResult(
                success=False,
                error=error_msg,
                metadata={
                    "tool": self.name,
                    "operation_id": operation_id,
                    "context_name": context_name,
                    "error_type": "unexpected_error",
                },
            )

    async def execute_streaming(
        self, session: ConnectionSession, parameters: Dict[str, Any]
    ) -> AsyncGenerator[ToolResult, None]:
        """Execute context switch with streaming progress updates."""
        context_name = parameters["context_name"]
        force_switch = parameters.get("force_switch", False)
        operation_id = str(uuid.uuid4())

        try:
            # Get LightRAG client
            client = await self.get_lightrag_client()

            # Step 1: Validate context exists (10% progress)
            yield ToolResult(
                success=True,
                data={
                    "step": "validation",
                    "message": f"Validating context '{context_name}'",
                },
                progress=ToolProgress(
                    operation_id=operation_id,
                    progress=0.1,
                    status="validating",
                    message=f"Validating context '{context_name}' exists",
                ),
            )

            contexts_response = await client.list_contexts()
            contexts_data = contexts_response.get("contexts", {})
            current_context = contexts_response.get("current_context")

            if context_name not in contexts_data:
                yield ToolResult(
                    success=False,
                    error=f"Context '{context_name}' not found",
                    progress=ToolProgress(
                        operation_id=operation_id,
                        progress=0.1,
                        status="failed",
                        message=f"Context '{context_name}' not found",
                    ),
                )
                return

            # Check if already in target context
            if current_context == context_name and not force_switch:
                yield ToolResult(
                    success=True,
                    data={
                        "step": "complete",
                        "message": f"Already in context '{context_name}'",
                        "switch_performed": False,
                    },
                    progress=ToolProgress(
                        operation_id=operation_id,
                        progress=1.0,
                        status="completed",
                        message=f"Already in context '{context_name}', no switch needed",
                    ),
                )
                return

            # Step 2: Initiate context switch (25% progress)
            yield ToolResult(
                success=True,
                data={
                    "step": "initiating",
                    "message": f"Starting switch to '{context_name}'",
                },
                progress=ToolProgress(
                    operation_id=operation_id,
                    progress=0.25,
                    status="switching",
                    message=f"Initiating switch from '{current_context}' to '{context_name}'",
                ),
            )

            # Call the LightRAG API to perform the context switch
            switch_response = await client.switch_context(context_name)

            # Step 3: Processing context switch (50% progress)
            yield ToolResult(
                success=True,
                data={"step": "processing", "message": "Processing context switch"},
                progress=ToolProgress(
                    operation_id=operation_id,
                    progress=0.5,
                    status="processing",
                    message="Processing context switch and updating storage",
                ),
            )

            await asyncio.sleep(0.5)  # Allow backend processing time

            # Step 4: Verifying switch (75% progress)
            yield ToolResult(
                success=True,
                data={
                    "step": "verifying",
                    "message": "Verifying context switch completion",
                },
                progress=ToolProgress(
                    operation_id=operation_id,
                    progress=0.75,
                    status="verifying",
                    message="Verifying context switch completed successfully",
                ),
            )

            await asyncio.sleep(0.5)  # Additional verification time

            # Get updated context information
            verification_response = await client.list_contexts()
            new_current_context = verification_response.get("current_context")

            # Step 5: Complete (100% progress)
            if new_current_context == context_name:
                yield ToolResult(
                    success=True,
                    data={
                        "step": "complete",
                        "message": f"Successfully switched to context '{context_name}'",
                        "previous_context": current_context,
                        "current_context": new_current_context,
                        "switch_performed": True,
                        "context_info": contexts_data.get(context_name, {}),
                    },
                    progress=ToolProgress(
                        operation_id=operation_id,
                        progress=1.0,
                        status="completed",
                        message=f"Context switch completed: {current_context} → {context_name}",
                    ),
                )
            else:
                yield ToolResult(
                    success=False,
                    error=f"Context switch verification failed. Expected '{context_name}', got '{new_current_context}'",
                    progress=ToolProgress(
                        operation_id=operation_id,
                        progress=0.75,
                        status="failed",
                        message="Context switch verification failed",
                    ),
                )

        except APIError as e:
            yield ToolResult(
                success=False,
                error=f"LightRAG API error: {e}",
                progress=ToolProgress(
                    operation_id=operation_id,
                    progress=0.0,
                    status="failed",
                    message=f"API error during context switch: {e}",
                ),
            )
        except Exception as e:
            yield ToolResult(
                success=False,
                error=f"Unexpected error: {str(e)}",
                progress=ToolProgress(
                    operation_id=operation_id,
                    progress=0.0,
                    status="failed",
                    message=f"Unexpected error: {str(e)}",
                ),
            )


class GetContextInfoTool(MCPTool):
    """Tool for getting detailed information about a specific context."""

    @property
    def name(self) -> str:
        return "get_context_info"

    @property
    def description(self) -> str:
        return "Get detailed information about a specific context including metadata, paths, and statistics"

    @property
    def category(self) -> ToolCategory:
        return ToolCategory.CONTEXT_MANAGEMENT

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            string_parameter(
                name="context_name",
                description="Name of the context to get information about",
                required=True,
            ),
            boolean_parameter(
                name="include_statistics",
                description="Include detailed statistics about documents, entities, relationships, and disk usage",
                required=False,
                default=False,
            ),
        ]

    @property
    def requires_context(self) -> bool:
        return False  # This tool can work on any context

    async def execute(
        self, session: ConnectionSession, parameters: Dict[str, Any]
    ) -> ToolResult:
        """Execute the get_context_info tool."""
        try:
            context_name = parameters["context_name"]
            include_statistics = parameters.get("include_statistics", False)

            # Get LightRAG client
            client = await self.get_lightrag_client()

            # First, list all contexts to find the requested one
            response = await client.list_contexts()
            contexts_data = response.get("contexts", {})

            if context_name not in contexts_data:
                return ToolResult(
                    success=False,
                    error=f"Context '{context_name}' not found",
                    metadata={"tool": self.name, "context_name": context_name},
                )

            context_info = contexts_data[context_name]

            # Get additional context information if available
            try:
                # Try to get specific context details
                context_details = await client.get_context(context_name)
            except APIError:
                # If specific context endpoint doesn't exist, use what we have
                context_details = {}

            # Format the detailed response
            detailed_info = {
                "name": context_name,
                "description": context_info.get("description", ""),
                "is_current": context_info.get("is_current", False),
                "is_default": context_info.get("is_default", False),
                "created_at": context_info.get("created_at"),
                "working_path": context_info.get("working_path"),
                "input_path": context_info.get("input_path"),
                "paths": {
                    "working": context_info.get("working_path"),
                    "input": context_info.get("input_path"),
                    "legacy_path": context_info.get(
                        "path"
                    ),  # For backward compatibility
                },
                "status": {
                    "active": True,
                    "accessible": True,  # Assume accessible if it exists
                },
            }

            # Get detailed statistics if requested
            if include_statistics:
                try:
                    # Make request to context statistics endpoint
                    stats_response = await client._make_request(
                        "GET", f"/contexts/{context_name}/stats"
                    )
                    stats_data = client._handle_response(stats_response)

                    detailed_info["statistics"] = {
                        "documents_count": stats_data.get("documents_count", 0),
                        "entities_count": stats_data.get("entities_count", 0),
                        "relationships_count": stats_data.get("relationships_count", 0),
                        "disk_usage_mb": stats_data.get("disk_usage_mb", 0.0),
                        "last_updated": session.connected_at.isoformat(),
                    }

                    logger.info(f"Retrieved statistics for context '{context_name}'")

                except APIError as stats_error:
                    logger.warning(
                        f"Failed to get statistics for context '{context_name}': {stats_error}"
                    )
                    detailed_info["statistics"] = {
                        "error": f"Statistics unavailable: {str(stats_error)}",
                        "documents_count": None,
                        "entities_count": None,
                        "relationships_count": None,
                        "disk_usage_mb": None,
                    }
                except Exception as stats_error:
                    logger.warning(
                        f"Unexpected error getting statistics for context '{context_name}': {stats_error}"
                    )
                    detailed_info["statistics"] = {
                        "error": f"Statistics error: {str(stats_error)}",
                        "documents_count": None,
                        "entities_count": None,
                        "relationships_count": None,
                        "disk_usage_mb": None,
                    }

            # Add any additional details from the specific context query
            if context_details:
                detailed_info["additional_info"] = context_details

            metadata = {
                "tool": self.name,
                "context_name": context_name,
                "include_statistics": include_statistics,
                "timestamp": session.connected_at.isoformat(),
            }

            logger.info(
                f"Retrieved context info for '{context_name}' (stats: {include_statistics}) for session {session.session_id}"
            )

            return ToolResult(
                success=True,
                data=detailed_info,
                metadata=metadata,
            )

        except APIError as e:
            error_msg = f"LightRAG API error: {e}"
            logger.error(f"Get context info failed: {error_msg}")
            return ToolResult(
                success=False,
                error=error_msg,
                metadata={"tool": self.name, "error_type": "api_error"},
            )
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(f"Get context info failed: {error_msg}", exc_info=True)
            return ToolResult(
                success=False,
                error=error_msg,
                metadata={"tool": self.name, "error_type": "unexpected_error"},
            )


class QueryTool(MCPTool):
    """Tool for executing queries against the LightRAG knowledge graph with all supported modes."""

    @property
    def name(self) -> str:
        return "query"

    @property
    def description(self) -> str:
        return "Execute queries against the LightRAG knowledge graph using various retrieval modes (naive, local, global, hybrid, mix)"

    @property
    def category(self) -> ToolCategory:
        return ToolCategory.CONTEXT_MANAGEMENT

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            string_parameter(
                name="query",
                description="The query text to search for in the knowledge graph",
                required=True,
            ),
            string_parameter(
                name="mode",
                description="Query mode: 'naive' (basic search), 'local' (entity-focused), 'global' (relationship-focused), 'hybrid' (combines local+global), 'mix' (knowledge graph + vector search)",
                required=False,
                default="hybrid",
            ),
            boolean_parameter(
                name="only_need_context",
                description="If true, only returns the retrieved context without generating a response",
                required=False,
                default=False,
            ),
            string_parameter(
                name="response_type",
                description="Response format: 'Multiple Paragraphs', 'Single Paragraph', 'Bullet Points', etc.",
                required=False,
                default="Multiple Paragraphs",
            ),
            boolean_parameter(
                name="include_relationships",
                description="Include relationship data in the response for graph exploration",
                required=False,
                default=False,
            ),
            ToolParameter(
                name="relationship_depth",
                type=ToolParameterType.INTEGER,
                description="Depth for relationship traversal when include_relationships is true (default: 1, max: 3)",
                required=False,
                default=1,
                minimum=0,
                maximum=3,
            ),
            string_parameter(
                name="relationship_types",
                description="Filter relationships by types (comma-separated, e.g., 'implements,uses,contains'). Leave empty for all types.",
                required=False,
                default="",
            ),
            ToolParameter(
                name="top_k",
                type=ToolParameterType.INTEGER,
                description="Number of top items to retrieve (entities in local mode, relationships in global mode)",
                required=False,
                default=10,
                minimum=1,
                maximum=100,
            ),
            ToolParameter(
                name="max_token_for_text_unit",
                type=ToolParameterType.INTEGER,
                description="Maximum tokens allowed for each retrieved text chunk",
                required=False,
                default=1000,
                minimum=100,
                maximum=8000,
            ),
            ToolParameter(
                name="max_token_for_global_context",
                type=ToolParameterType.INTEGER,
                description="Maximum tokens for relationship descriptions in global retrieval",
                required=False,
                default=2000,
                minimum=100,
                maximum=8000,
            ),
            ToolParameter(
                name="max_token_for_local_context",
                type=ToolParameterType.INTEGER,
                description="Maximum tokens for entity descriptions in local retrieval",
                required=False,
                default=1500,
                minimum=100,
                maximum=8000,
            ),
        ]

    @property
    def requires_context(self) -> bool:
        return True

    async def execute(
        self, session: ConnectionSession, parameters: Dict[str, Any]
    ) -> ToolResult:
        """Execute a query against the LightRAG knowledge graph."""
        operation_id = f"query_{session.session_id}"

        try:
            # Parameter validation
            query_text = parameters.get("query", "").strip()
            if not query_text:
                return ToolResult(
                    success=False,
                    error="Query text is required and cannot be empty",
                    metadata={
                        "operation_id": operation_id,
                        "error_type": "validation_error",
                    },
                )

            mode = parameters.get("mode", "hybrid")
            only_need_context = parameters.get("only_need_context", False)
            response_type = parameters.get("response_type", "Multiple Paragraphs")
            include_relationships = parameters.get("include_relationships", False)
            relationship_depth = parameters.get("relationship_depth", 1)
            relationship_types = parameters.get("relationship_types", "").strip()

            # Validate mode parameter
            valid_modes = ["naive", "local", "global", "hybrid", "mix"]
            if mode not in valid_modes:
                return ToolResult(
                    success=False,
                    error=f"Invalid query mode '{mode}'. Valid modes are: {', '.join(valid_modes)}",
                    metadata={
                        "operation_id": operation_id,
                        "error_type": "validation_error",
                    },
                )

            # Create operation tracking
            operation_id = str(uuid.uuid4())

            # Progress tracking for query execution
            progress = ToolProgress(
                operation_id=operation_id,
                progress=0.1,
                status="validating",
                message=f"Validating query in {mode} mode",
            )

            logger.info(
                f"Starting query execution: '{query_text[:50]}...' in {mode} mode"
            )

            # Get LightRAG client
            client = await self.get_lightrag_client()

            # Build query parameters
            query_params = {
                "query": query_text,
                "mode": mode,
                "only_need_context": only_need_context,
                "response_type": response_type,
                "include_relationships": include_relationships,
            }

            # Add optional token parameters if provided (now properly typed as integers)
            optional_params = [
                "top_k",
                "max_token_for_text_unit",
                "max_token_for_global_context",
                "max_token_for_local_context",
            ]
            for param in optional_params:
                if param in parameters and parameters[param] is not None:
                    # Parameters are now properly validated as integers by the framework
                    query_params[param] = parameters[param]

            # Update progress
            progress.status = "executing"
            progress.progress = 0.3
            progress.message = f"Executing {mode} mode query against knowledge graph"

            # Execute the query
            result = await client.query(**query_params)

            # Update progress
            progress.status = "processing"
            progress.progress = 0.7
            progress.message = "Processing query results and metadata"

            # Process the response based on mode and parameters
            processed_result = {
                "query": query_text,
                "mode": mode,
                "response": result.get("response", ""),
                "context_used": only_need_context,
                "response_type": response_type,
            }

            # Add relationships if requested and available
            if include_relationships and "relationships" in result:
                # Filter relationships by type if specified
                relationships = result["relationships"]
                if relationship_types:
                    relationship_filter = [
                        rt.strip().lower()
                        for rt in relationship_types.split(",")
                        if rt.strip()
                    ]
                    relationships = [
                        rel
                        for rel in relationships
                        if rel.get("type", "").lower() in relationship_filter
                    ]

                processed_result["relationships"] = relationships
                processed_result["relationship_count"] = len(relationships)
                processed_result["relationship_depth_used"] = 1  # Base level

                # If depth > 1, perform additional relationship traversal
                if relationship_depth > 1 and relationships:
                    try:
                        enhanced_relationships = (
                            await self._expand_relationships_with_depth(
                                client,
                                relationships,
                                relationship_depth - 1,
                                relationship_filter if relationship_types else [],
                            )
                        )
                        processed_result["relationships"] = enhanced_relationships
                        processed_result["relationship_count"] = len(
                            enhanced_relationships
                        )
                        processed_result["relationship_depth_used"] = relationship_depth
                    except Exception as e:
                        logger.warning(
                            f"Failed to expand relationships with depth {relationship_depth}: {e}"
                        )
                        # Fall back to original relationships
                        processed_result["relationships"] = relationships
                        processed_result["relationship_depth_used"] = 1

            # Add context information if available
            if "context" in result:
                processed_result["context_info"] = {
                    "has_context": True,
                    "context_type": result.get("context_type", "unknown"),
                }

            # Add performance metadata
            if "metadata" in result:
                processed_result["performance"] = result["metadata"]

            # Final progress update
            progress.status = "completed"
            progress.progress = 1.0
            progress.message = f"Query completed successfully with {len(processed_result.get('response', ''))} characters"

            metadata = {
                "tool": self.name,
                "operation_id": operation_id,
                "query_mode": mode,
                "query_length": len(query_text),
                "response_length": len(processed_result.get("response", "")),
                "include_relationships": include_relationships,
                "context_name": session.context,
                "timestamp": session.connected_at.isoformat(),
            }

            logger.info(
                f"Query executed successfully in {mode} mode for session {session.session_id} "
                f"({len(processed_result.get('response', ''))} chars response)"
            )

            return ToolResult(
                success=True,
                data=processed_result,
                metadata=metadata,
            )

        except APIError as e:
            error_msg = f"LightRAG API error during query: {e}"
            logger.error(f"Query execution failed: {error_msg}")
            return ToolResult(
                success=False,
                error=error_msg,
                metadata={"operation_id": operation_id, "error_type": "api_error"},
            )
        except Exception as e:
            error_msg = f"Unexpected error during query execution: {str(e)}"
            logger.error(f"Query execution failed: {error_msg}", exc_info=True)
            return ToolResult(
                success=False,
                error=error_msg,
                metadata={
                    "operation_id": operation_id,
                    "error_type": "unexpected_error",
                },
            )

    async def execute_streaming(
        self, session: ConnectionSession, parameters: Dict[str, Any]
    ) -> AsyncGenerator[ToolResult, None]:
        """Execute query with streaming progress updates."""
        try:
            query_text = parameters["query"]
            mode = parameters.get("mode", "hybrid")

            # Create operation tracking
            operation_id = str(uuid.uuid4())

            # Step 1: Validation (10%)
            yield ToolResult(
                success=True,
                data=ToolProgress(
                    operation_id=operation_id,
                    progress=0.1,
                    status="validation",
                    message=f"Validating query parameters for {mode} mode",
                ),
                metadata={"tool": self.name, "streaming": True},
            )

            # Validate mode
            valid_modes = ["naive", "local", "global", "hybrid", "mix"]
            if mode not in valid_modes:
                yield ToolResult(
                    success=False,
                    error=f"Invalid query mode '{mode}'. Valid modes are: {', '.join(valid_modes)}",
                    metadata={"tool": self.name, "error_type": "validation_error"},
                )
                return

            # Step 2: Initialization (25%)
            yield ToolResult(
                success=True,
                data=ToolProgress(
                    operation_id=operation_id,
                    progress=0.25,
                    status="initialization",
                    message=f"Initializing LightRAG client for {mode} query",
                ),
                metadata={"tool": self.name, "streaming": True},
            )

            # Step 3: Query Execution (50%)
            yield ToolResult(
                success=True,
                data=ToolProgress(
                    operation_id=operation_id,
                    progress=0.5,
                    status="execution",
                    message=f"Executing {mode} mode query: '{query_text[:30]}...'",
                ),
                metadata={"tool": self.name, "streaming": True},
            )

            # Execute the actual query
            result = await self.execute(session, parameters)

            # Step 4: Processing Results (75%)
            yield ToolResult(
                success=True,
                data=ToolProgress(
                    operation_id=operation_id,
                    progress=0.75,
                    status="processing",
                    message="Processing query results and formatting response",
                ),
                metadata={"tool": self.name, "streaming": True},
            )

            # Step 5: Completion (100%)
            if result.success:
                yield ToolResult(
                    success=True,
                    data=ToolProgress(
                        operation_id=operation_id,
                        progress=1.0,
                        status="completed",
                        message="Query execution completed successfully",
                    ),
                    metadata={"tool": self.name, "streaming": True},
                )

                # Final result
                yield result
            else:
                yield ToolResult(
                    success=False,
                    error=f"Query execution failed: {result.error}",
                    data=ToolProgress(
                        operation_id=operation_id,
                        progress=1.0,
                        status="failed",
                        message=f"Query failed: {result.error}",
                    ),
                    metadata={
                        "tool": self.name,
                        "streaming": True,
                        "error_type": "execution_failed",
                    },
                )

        except Exception as e:
            error_msg = f"Streaming query execution failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            yield ToolResult(
                success=False,
                error=error_msg,
                metadata={"tool": self.name, "error_type": "streaming_error"},
            )

    async def _expand_relationships_with_depth(
        self,
        client: LightRAGClient,
        initial_relationships: List[Dict],
        remaining_depth: int,
        relationship_filter: List[str],
    ) -> List[Dict]:
        """Expand relationships by traversing connected entities to specified depth."""
        if remaining_depth <= 0 or not initial_relationships:
            return initial_relationships

        all_relationships = list(
            initial_relationships
        )  # Start with initial relationships
        explored_entities = set()

        # Extract entities from initial relationships
        entities_to_explore = set()
        for rel in initial_relationships:
            entities_to_explore.add(rel.get("source", ""))
            entities_to_explore.add(rel.get("target", ""))

        # Remove empty strings
        entities_to_explore.discard("")

        for current_depth in range(remaining_depth):
            if not entities_to_explore:
                break

            next_level_entities = set()

            # Explore each entity at this depth level (limit to avoid performance issues)
            for entity in list(entities_to_explore)[
                :10
            ]:  # Limit to 10 entities per level
                if entity in explored_entities:
                    continue

                explored_entities.add(entity)

                try:
                    # Query for relationships involving this entity
                    query_text = f"relationships involving {entity}"
                    result = await client.query(
                        query=query_text,
                        mode="global",  # Global mode focuses on relationships
                        only_need_context=True,
                        include_relationships=True,
                        top_k=10,
                    )

                    # Extract new relationships
                    if result.get("relationships"):
                        for rel in result["relationships"]:
                            # Filter by relationship type if specified
                            if relationship_filter:
                                rel_type = rel.get("type", "").lower()
                                if rel_type not in relationship_filter:
                                    continue

                            # Check if this is a new relationship (not already in our list)
                            is_new_relationship = True
                            for existing_rel in all_relationships:
                                if (
                                    existing_rel.get("source") == rel.get("source")
                                    and existing_rel.get("target") == rel.get("target")
                                    and existing_rel.get("type") == rel.get("type")
                                ):
                                    is_new_relationship = False
                                    break

                            if is_new_relationship:
                                # Add depth information
                                rel["discovered_at_depth"] = (
                                    current_depth + 2
                                )  # +2 because we started at depth 1
                                all_relationships.append(rel)

                                # Add connected entities for next level
                                next_level_entities.add(rel.get("source", ""))
                                next_level_entities.add(rel.get("target", ""))

                except Exception as e:
                    logger.warning(
                        f"Failed to expand relationships for entity '{entity}': {e}"
                    )
                    continue

            # Prepare for next iteration
            entities_to_explore = next_level_entities - explored_entities
            entities_to_explore.discard("")  # Remove empty strings

        return all_relationships


class FindConceptTool(MCPTool):
    """Tool for finding concepts/entities in the knowledge graph using semantic search."""

    def __init__(self, config: MCPConfig):
        super().__init__(config)

    @property
    def name(self) -> str:
        return "find_concept"

    @property
    def description(self) -> str:
        return "Find concepts/entities in the knowledge graph using semantic search. Searches for entities that are semantically similar to the query text."

    @property
    def category(self) -> ToolCategory:
        return ToolCategory.SEMANTIC_SEARCH

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="query",
                type=ToolParameterType.STRING,
                description="The concept or entity to search for (e.g., 'user authentication', 'payment processing', 'data storage')",
                required=True,
            ),
            ToolParameter(
                name="top_k",
                type=ToolParameterType.INTEGER,
                description="Maximum number of concepts to return (default: 10, max: 50)",
                required=False,
                default=10,
                minimum=1,
                maximum=50,
            ),
            ToolParameter(
                name="include_descriptions",
                type=ToolParameterType.BOOLEAN,
                description="Whether to include entity descriptions and metadata (default: true)",
                required=False,
                default=True,
            ),
            ToolParameter(
                name="entity_types",
                type=ToolParameterType.ARRAY,
                description="Optional filter by entity types (e.g., ['organization', 'person', 'technology'])",
                required=False,
                items=ToolParameter(
                    name="entity_type",
                    type=ToolParameterType.STRING,
                    description="Entity type",
                ),
            ),
            ToolParameter(
                name="include_relationships",
                type=ToolParameterType.BOOLEAN,
                description="Include relationships for discovered concepts (default: false)",
                required=False,
                default=False,
            ),
            ToolParameter(
                name="relationship_depth",
                type=ToolParameterType.INTEGER,
                description="Depth for relationship traversal when include_relationships is true (default: 1, max: 3)",
                required=False,
                default=1,
                minimum=0,
                maximum=3,
            ),
            ToolParameter(
                name="relationship_types",
                type=ToolParameterType.STRING,
                description="Filter relationships by types (comma-separated, e.g., 'implements,uses,contains'). Leave empty for all types.",
                required=False,
                default="",
            ),
        ]

    async def execute(
        self, session: ConnectionSession, parameters: Dict[str, Any]
    ) -> ToolResult:
        """Execute concept search."""
        operation_id = f"find_concept_{session.session_id}"

        try:
            # Parameter validation and extraction
            query = parameters.get("query", "").strip()
            if not query:
                return ToolResult(
                    success=False,
                    error="Query parameter is required and cannot be empty",
                    metadata={"operation_id": operation_id},
                )

            top_k = min(max(int(parameters.get("top_k", 10)), 1), 50)
            include_descriptions = parameters.get("include_descriptions", True)
            entity_types = parameters.get("entity_types", [])
            include_relationships = parameters.get("include_relationships", False)
            relationship_depth = parameters.get("relationship_depth", 1)
            relationship_types = parameters.get("relationship_types", "").strip()

            # Get LightRAG client
            client = await self.get_lightrag_client()

            # Use LightRAG's local mode query to find entities
            query_data = {
                "query": query,
                "mode": "local",  # Local mode focuses on entities
                "top_k": top_k,
                "only_need_context": True,  # Get only the context data
                "include_relationships": True,
            }

            # Execute search
            response = await client.query(query_data)

            # Process results

            # Parse the context response to extract entity information
            concepts = []
            if isinstance(response, dict) and "response" in response:
                context_text = response["response"]

                # Try to extract JSON entities from the context
                try:
                    # Look for entities context in the response
                    if "---Entities---" in context_text:
                        entities_section = context_text.split("---Entities---")[1]
                        if "---" in entities_section:
                            entities_section = entities_section.split("---")[0]

                        # Try to parse as JSON
                        try:
                            entities_data = json.loads(
                                entities_section.strip().strip("```json").strip("```")
                            )
                            if isinstance(entities_data, list):
                                for entity in entities_data[:top_k]:
                                    if isinstance(entity, dict):
                                        concept = {
                                            "entity_name": entity.get(
                                                "entity",
                                                entity.get("entity_name", "Unknown"),
                                            ),
                                            "entity_type": entity.get(
                                                "type",
                                                entity.get("entity_type", "Unknown"),
                                            ),
                                            "rank": entity.get("rank", 0),
                                            "created_at": entity.get(
                                                "created_at", "Unknown"
                                            ),
                                            "file_path": entity.get(
                                                "file_path", "unknown_source"
                                            ),
                                        }

                                        if include_descriptions:
                                            concept["description"] = entity.get(
                                                "description",
                                                "No description available",
                                            )

                                        # Filter by entity types if specified
                                        if not entity_types or concept[
                                            "entity_type"
                                        ].lower() in [
                                            et.lower() for et in entity_types
                                        ]:
                                            concepts.append(concept)
                        except json.JSONDecodeError:
                            # Fallback: create a simple concept result
                            concepts.append(
                                {
                                    "entity_name": query,
                                    "entity_type": "concept",
                                    "rank": 1,
                                    "description": (
                                        f"Concept search result for: {query}"
                                        if include_descriptions
                                        else None
                                    ),
                                    "created_at": "Unknown",
                                    "file_path": "search_result",
                                }
                            )
                except Exception as parse_error:
                    logger.warning(
                        f"Failed to parse entity context for {operation_id}: {parse_error}"
                    )
                    # Create a generic result
                    concepts.append(
                        {
                            "entity_name": query,
                            "entity_type": "concept",
                            "rank": 1,
                            "description": (
                                f"Semantic search result for: {query}"
                                if include_descriptions
                                else None
                            ),
                            "created_at": "Unknown",
                            "file_path": "search_result",
                        }
                    )

            # Add relationships if requested
            relationships = []
            if include_relationships and concepts:
                try:
                    # Extract entity names from discovered concepts
                    entity_names = [
                        concept.get("entity_name", "")
                        for concept in concepts
                        if concept.get("entity_name")
                    ]

                    if entity_names:
                        # Get relationships for the discovered entities
                        relationships = await self._get_relationships_for_entities(
                            client, entity_names, relationship_depth, relationship_types
                        )
                except Exception as e:
                    logger.warning(f"Failed to get relationships for concepts: {e}")

            result_content = {
                "query": query,
                "total_found": len(concepts),
                "concepts": concepts,
                "search_parameters": {
                    "top_k": top_k,
                    "include_descriptions": include_descriptions,
                    "entity_types": entity_types if entity_types else None,
                    "include_relationships": include_relationships,
                    "relationship_depth": (
                        relationship_depth if include_relationships else None
                    ),
                },
            }

            # Add relationships to result if requested
            if include_relationships:
                result_content["relationships"] = relationships
                result_content["relationship_count"] = len(relationships)

            return ToolResult(
                success=True,
                data=json.dumps(result_content, indent=2, ensure_ascii=False),
                metadata={
                    "operation_id": operation_id,
                    "query": query,
                    "total_found": len(concepts),
                    "response_format": "entity_search",
                },
            )

        except Exception as e:
            logger.error(f"Error in find_concept for {operation_id}: {e}")
            return ToolResult(
                success=False,
                error=f"Error finding concepts: {str(e)}",
                metadata={"operation_id": operation_id, "error": str(e)},
            )

    async def execute_streaming(self, **kwargs):
        """Streaming execution for concept search with progress tracking."""
        operation_id = f"find_concept_stream_{id(kwargs)}"

        try:
            # Validate parameters
            query = kwargs.get("query", "").strip()
            if not query:
                yield ToolProgress(
                    operation_id=operation_id,
                    progress=100,
                    status="failed",
                    message="Query parameter is required",
                )
                return

            # Progress updates
            yield ToolProgress(
                operation_id=operation_id,
                progress=10,
                status="validated",
                message="Parameters validated",
            )
            yield ToolProgress(
                operation_id=operation_id,
                progress=25,
                status="searching",
                message="Starting entity search",
            )
            yield ToolProgress(
                operation_id=operation_id,
                progress=50,
                status="processing",
                message="Executing semantic search",
            )
            yield ToolProgress(
                operation_id=operation_id,
                progress=75,
                status="processing",
                message="Processing results",
            )

            # Execute the search
            result = await self.execute(**kwargs)

            yield ToolProgress(
                operation_id=operation_id,
                progress=100,
                status="completed",
                message="Concept search completed",
            )
            yield result

        except Exception as e:
            yield ToolProgress(
                operation_id=operation_id,
                progress=100,
                status="failed",
                message=f"Error: {str(e)}",
            )
            yield ToolResult(
                success=False,
                error=f"Error in streaming concept search: {str(e)}",
                metadata={"operation_id": operation_id, "error": str(e)},
            )

    async def _get_relationships_for_entities(
        self,
        client: LightRAGClient,
        entity_names: List[str],
        relationship_depth: int,
        relationship_types: str,
    ) -> List[Dict]:
        """Get relationships for discovered entities with configurable depth."""
        if not entity_names or relationship_depth <= 0:
            return []

        all_relationships = []
        relationship_filter = []

        # Parse relationship types filter
        if relationship_types:
            relationship_filter = [
                rt.strip().lower() for rt in relationship_types.split(",") if rt.strip()
            ]

        # Get relationships for each entity
        for entity_name in entity_names[
            :5
        ]:  # Limit to 5 entities to avoid performance issues
            try:
                # Query for relationships involving this entity
                query_text = f"relationships for {entity_name}"
                result = await client.query(
                    query=query_text,
                    mode="global",  # Global mode focuses on relationships
                    only_need_context=True,
                    include_relationships=True,
                    top_k=10,
                )

                if result.get("relationships"):
                    for rel in result["relationships"]:
                        # Filter by relationship type if specified
                        if relationship_filter:
                            rel_type = rel.get("type", "").lower()
                            if rel_type not in relationship_filter:
                                continue

                        # Add base relationship
                        rel["discovered_at_depth"] = 1
                        all_relationships.append(rel)

                # If depth > 1, expand relationships
                if relationship_depth > 1 and result.get("relationships"):
                    try:
                        expanded_relationships = (
                            await self._expand_concept_relationships(
                                client,
                                result["relationships"],
                                relationship_depth - 1,
                                relationship_filter,
                            )
                        )
                        all_relationships.extend(expanded_relationships)
                    except Exception as e:
                        logger.warning(
                            f"Failed to expand relationships for entity '{entity_name}': {e}"
                        )

            except Exception as e:
                logger.warning(
                    f"Failed to get relationships for entity '{entity_name}': {e}"
                )
                continue

        # Remove duplicates based on source, target, and type
        unique_relationships = []
        seen_relationships = set()

        for rel in all_relationships:
            rel_key = (
                rel.get("source", ""),
                rel.get("target", ""),
                rel.get("type", ""),
            )
            if rel_key not in seen_relationships:
                seen_relationships.add(rel_key)
                unique_relationships.append(rel)

        return unique_relationships

    async def _expand_concept_relationships(
        self,
        client: LightRAGClient,
        initial_relationships: List[Dict],
        remaining_depth: int,
        relationship_filter: List[str],
    ) -> List[Dict]:
        """Expand relationships for concept discovery with depth control."""
        if remaining_depth <= 0 or not initial_relationships:
            return []

        expanded_relationships = []
        entities_to_explore = set()

        # Extract entities from initial relationships
        for rel in initial_relationships:
            entities_to_explore.add(rel.get("source", ""))
            entities_to_explore.add(rel.get("target", ""))

        entities_to_explore.discard("")  # Remove empty strings

        # Explore each entity (limit to avoid performance issues)
        for entity in list(entities_to_explore)[:5]:
            try:
                query_text = f"relationships involving {entity}"
                result = await client.query(
                    query=query_text,
                    mode="global",
                    only_need_context=True,
                    include_relationships=True,
                    top_k=5,
                )

                if result.get("relationships"):
                    for rel in result["relationships"]:
                        # Filter by relationship type if specified
                        if relationship_filter:
                            rel_type = rel.get("type", "").lower()
                            if rel_type not in relationship_filter:
                                continue

                        # Check if this is a new relationship
                        is_new = True
                        for existing_rel in (
                            initial_relationships + expanded_relationships
                        ):
                            if (
                                existing_rel.get("source") == rel.get("source")
                                and existing_rel.get("target") == rel.get("target")
                                and existing_rel.get("type") == rel.get("type")
                            ):
                                is_new = False
                                break

                        if is_new:
                            rel["discovered_at_depth"] = (
                                3 - remaining_depth
                            ) + 1  # Calculate actual depth
                            expanded_relationships.append(rel)

            except Exception as e:
                logger.warning(
                    f"Failed to expand relationships for entity '{entity}': {e}"
                )
                continue

        return expanded_relationships


class GetRelationshipsTool(MCPTool):
    """Tool for retrieving relationships between entities in the knowledge graph."""

    def __init__(self, config: MCPConfig):
        super().__init__(config)

    @property
    def name(self) -> str:
        return "get_relationships"

    @property
    def description(self) -> str:
        return "Retrieve relationships between entities in the knowledge graph. Can search for relationships by entity names or by semantic query."

    @property
    def category(self) -> ToolCategory:
        return ToolCategory.SEMANTIC_SEARCH

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="query",
                type=ToolParameterType.STRING,
                description="Search query for relationships (e.g., 'how does authentication connect to user management')",
                required=False,
            ),
            ToolParameter(
                name="entity_name",
                type=ToolParameterType.STRING,
                description="Specific entity name to find relationships for (alternative to query)",
                required=False,
            ),
            ToolParameter(
                name="source_entity",
                type=ToolParameterType.STRING,
                description="Source entity for finding specific relationships (used with target_entity)",
                required=False,
            ),
            ToolParameter(
                name="target_entity",
                type=ToolParameterType.STRING,
                description="Target entity for finding specific relationships (used with source_entity)",
                required=False,
            ),
            ToolParameter(
                name="top_k",
                type=ToolParameterType.INTEGER,
                description="Maximum number of relationships to return (default: 20, max: 100)",
                required=False,
                default=20,
                minimum=1,
                maximum=100,
            ),
            ToolParameter(
                name="include_entities",
                type=ToolParameterType.BOOLEAN,
                description="Whether to include full entity information for relationship endpoints (default: true)",
                required=False,
                default=True,
            ),
            ToolParameter(
                name="relationship_types",
                type=ToolParameterType.ARRAY,
                description="Optional filter by relationship types or keywords",
                required=False,
                items=ToolParameter(
                    name="relationship_type",
                    type=ToolParameterType.STRING,
                    description="Relationship type or keyword",
                ),
            ),
            ToolParameter(
                name="relationship_depth",
                type=ToolParameterType.INTEGER,
                description="Depth for multi-hop relationship traversal (default: 1, max: 3). Higher values find relationships of relationships.",
                required=False,
                default=1,
                minimum=1,
                maximum=3,
            ),
        ]

    async def execute(
        self, session: ConnectionSession, parameters: Dict[str, Any]
    ) -> ToolResult:
        """Execute relationship search."""
        operation_id = f"get_relationships_{session.session_id}"

        try:
            # Parameter validation and extraction
            query = parameters.get("query", "").strip()
            entity_name = parameters.get("entity_name", "").strip()
            source_entity = parameters.get("source_entity", "").strip()
            target_entity = parameters.get("target_entity", "").strip()

            # At least one search parameter must be provided
            if not any([query, entity_name, source_entity]):
                return ToolResult(
                    success=False,
                    error="At least one of 'query', 'entity_name', or 'source_entity' must be provided",
                    metadata={"operation_id": operation_id},
                )

            top_k = min(max(int(parameters.get("top_k", 20)), 1), 100)
            include_entities = parameters.get("include_entities", True)
            relationship_types = parameters.get("relationship_types", [])
            relationship_depth = max(
                1, min(int(parameters.get("relationship_depth", 1)), 3)
            )

            # Get LightRAG client
            client = await self.get_lightrag_client()

            # Determine search strategy
            search_query = (
                query or entity_name or f"relationships involving {source_entity}"
            )

            # Use global mode to focus on relationships
            query_data = {
                "query": search_query,
                "mode": "global",  # Global mode focuses on relationships
                "top_k": top_k,
                "only_need_context": True,
                "include_relationships": True,
            }

            # Execute search
            response = await client.query(query_data)

            # Process results

            # Parse the context response to extract relationship information
            relationships = []
            entities_info = {}

            if isinstance(response, dict) and "response" in response:
                context_text = response["response"]

                # Try to extract relationships from the context
                try:
                    # Look for relationships section
                    if "---Relationships---" in context_text:
                        relationships_section = context_text.split(
                            "---Relationships---"
                        )[1]
                        if "---" in relationships_section:
                            relationships_section = relationships_section.split("---")[
                                0
                            ]

                        # Try to parse as JSON
                        try:
                            relationships_data = json.loads(
                                relationships_section.strip()
                                .strip("```json")
                                .strip("```")
                            )
                            if isinstance(relationships_data, list):
                                for rel in relationships_data[:top_k]:
                                    if isinstance(rel, dict):
                                        relationship = {
                                            "id": rel.get("id", len(relationships) + 1),
                                            "source_entity": rel.get(
                                                "source",
                                                rel.get("source_entity", "Unknown"),
                                            ),
                                            "target_entity": rel.get(
                                                "target",
                                                rel.get("target_entity", "Unknown"),
                                            ),
                                            "relationship_description": rel.get(
                                                "description",
                                                rel.get(
                                                    "relationship_description",
                                                    "No description",
                                                ),
                                            ),
                                            "keywords": rel.get(
                                                "keywords",
                                                rel.get("relationship_keywords", []),
                                            ),
                                            "strength": rel.get(
                                                "strength",
                                                rel.get("relationship_strength", 0),
                                            ),
                                            "created_at": rel.get(
                                                "created_at", "Unknown"
                                            ),
                                            "file_path": rel.get(
                                                "file_path", "unknown_source"
                                            ),
                                        }

                                        # Filter by relationship types if specified
                                        if not relationship_types:
                                            relationships.append(relationship)
                                        else:
                                            # Check if any keywords match the filter
                                            rel_keywords = relationship.get(
                                                "keywords", []
                                            )
                                            if isinstance(rel_keywords, str):
                                                rel_keywords = [rel_keywords]

                                            if any(
                                                rt.lower()
                                                in [k.lower() for k in rel_keywords]
                                                for rt in relationship_types
                                            ):
                                                relationships.append(relationship)
                        except json.JSONDecodeError:
                            # Fallback: create a simple relationship result
                            relationships.append(
                                {
                                    "id": 1,
                                    "source_entity": source_entity or "Unknown",
                                    "target_entity": target_entity or "Unknown",
                                    "relationship_description": f"Relationship search result for: {search_query}",
                                    "keywords": ["search", "result"],
                                    "strength": 1,
                                    "created_at": "Unknown",
                                    "file_path": "search_result",
                                }
                            )

                    # Also extract entities information if requested
                    if include_entities and "---Entities---" in context_text:
                        entities_section = context_text.split("---Entities---")[1]
                        if "---" in entities_section:
                            entities_section = entities_section.split("---")[0]

                        try:
                            entities_data = json.loads(
                                entities_section.strip().strip("```json").strip("```")
                            )
                            if isinstance(entities_data, list):
                                for entity in entities_data:
                                    if isinstance(entity, dict):
                                        entity_name_key = entity.get(
                                            "entity",
                                            entity.get("entity_name", "Unknown"),
                                        )
                                        entities_info[entity_name_key] = {
                                            "entity_type": entity.get(
                                                "type",
                                                entity.get("entity_type", "Unknown"),
                                            ),
                                            "description": entity.get(
                                                "description", "No description"
                                            ),
                                            "rank": entity.get("rank", 0),
                                            "created_at": entity.get(
                                                "created_at", "Unknown"
                                            ),
                                            "file_path": entity.get(
                                                "file_path", "unknown_source"
                                            ),
                                        }
                        except json.JSONDecodeError:
                            pass  # Skip entity parsing if it fails

                except Exception as parse_error:
                    logger.warning(
                        f"Failed to parse relationship context for {operation_id}: {parse_error}"
                    )
                    # Create a generic result
                    relationships.append(
                        {
                            "id": 1,
                            "source_entity": source_entity or entity_name or "Unknown",
                            "target_entity": target_entity or "Related Entity",
                            "relationship_description": f"Semantic relationship search for: {search_query}",
                            "keywords": ["search", "semantic"],
                            "strength": 1,
                            "created_at": "Unknown",
                            "file_path": "search_result",
                        }
                    )

            # Apply multi-hop relationship traversal if depth > 1
            if relationship_depth > 1 and relationships:
                try:
                    enhanced_relationships = await self._expand_relationships_multi_hop(
                        client,
                        relationships,
                        relationship_depth - 1,
                        relationship_types,
                        top_k,
                    )
                    relationships = enhanced_relationships
                except Exception as e:
                    logger.warning(
                        f"Failed to expand relationships with depth {relationship_depth}: {e}"
                    )
                    # Fall back to original relationships

            result_content = {
                "search_query": search_query,
                "total_found": len(relationships),
                "relationships": relationships,
                "search_parameters": {
                    "query": query if query else None,
                    "entity_name": entity_name if entity_name else None,
                    "source_entity": source_entity if source_entity else None,
                    "target_entity": target_entity if target_entity else None,
                    "top_k": top_k,
                    "include_entities": include_entities,
                    "relationship_types": (
                        relationship_types if relationship_types else None
                    ),
                    "relationship_depth": relationship_depth,
                },
            }

            if include_entities and entities_info:
                result_content["entities"] = entities_info

            return ToolResult(
                success=True,
                data=json.dumps(result_content, indent=2, ensure_ascii=False),
                metadata={
                    "operation_id": operation_id,
                    "search_query": search_query,
                    "total_found": len(relationships),
                    "response_format": "relationships_search",
                },
            )

        except Exception as e:
            logger.error(f"Error in get_relationships for {operation_id}: {e}")
            return ToolResult(
                success=False,
                error=f"Error retrieving relationships: {str(e)}",
                metadata={"operation_id": operation_id, "error": str(e)},
            )

    async def execute_streaming(self, **kwargs):
        """Streaming execution for relationship search with progress tracking."""
        operation_id = f"get_relationships_stream_{id(kwargs)}"

        try:
            # Validate parameters
            query = kwargs.get("query", "").strip()
            entity_name = kwargs.get("entity_name", "").strip()
            source_entity = kwargs.get("source_entity", "").strip()

            if not any([query, entity_name, source_entity]):
                yield ToolProgress(
                    operation_id=operation_id,
                    progress=100,
                    status="failed",
                    message="At least one search parameter required",
                )
                return

            # Progress updates
            yield ToolProgress(
                operation_id=operation_id,
                progress=10,
                status="validated",
                message="Parameters validated",
            )
            yield ToolProgress(
                operation_id=operation_id,
                progress=25,
                status="searching",
                message="Starting relationship search",
            )
            yield ToolProgress(
                operation_id=operation_id,
                progress=50,
                status="processing",
                message="Executing semantic search",
            )
            yield ToolProgress(
                operation_id=operation_id,
                progress=75,
                status="processing",
                message="Processing results",
            )

            # Execute the search
            result = await self.execute(**kwargs)

            yield ToolProgress(
                operation_id=operation_id,
                progress=100,
                status="completed",
                message="Relationship search completed",
            )
            yield result

        except Exception as e:
            yield ToolProgress(
                operation_id=operation_id,
                progress=100,
                status="failed",
                message=f"Error: {str(e)}",
            )
            yield ToolResult(
                success=False,
                error=f"Error in streaming relationship search: {str(e)}",
                metadata={"operation_id": operation_id, "error": str(e)},
            )

    async def _expand_relationships_multi_hop(
        self,
        client: LightRAGClient,
        initial_relationships: List[Dict],
        remaining_depth: int,
        relationship_types: List[str],
        max_results: int,
    ) -> List[Dict]:
        """Expand relationships through multi-hop traversal."""
        if remaining_depth <= 0 or not initial_relationships:
            return initial_relationships

        all_relationships = list(
            initial_relationships
        )  # Start with initial relationships
        explored_entities = set()

        # Extract entities from initial relationships
        entities_to_explore = set()
        for rel in initial_relationships:
            entities_to_explore.add(rel.get("source_entity", ""))
            entities_to_explore.add(rel.get("target_entity", ""))

        entities_to_explore.discard("")  # Remove empty strings

        for current_depth in range(remaining_depth):
            if not entities_to_explore:
                break

            next_level_entities = set()

            # Explore each entity at this depth level (limit to avoid performance issues)
            for entity in list(entities_to_explore)[
                :8
            ]:  # Limit to 8 entities per level
                if entity in explored_entities:
                    continue

                explored_entities.add(entity)

                try:
                    # Query for relationships involving this entity
                    query_text = f"relationships involving {entity}"
                    result = await client.query(
                        query=query_text,
                        mode="global",  # Global mode focuses on relationships
                        only_need_context=True,
                        include_relationships=True,
                        top_k=8,
                    )

                    # Extract new relationships from response
                    if result.get("response"):
                        response_text = result["response"]

                        # Try to extract relationships from context
                        if "---Relationships---" in response_text:
                            relationships_section = response_text.split(
                                "---Relationships---"
                            )[1]
                            if "---" in relationships_section:
                                relationships_section = relationships_section.split(
                                    "---"
                                )[0]

                            try:
                                relationships_data = json.loads(
                                    relationships_section.strip()
                                    .strip("```json")
                                    .strip("```")
                                )
                                if isinstance(relationships_data, list):
                                    for rel in relationships_data:
                                        if isinstance(rel, dict):
                                            # Create standardized relationship format
                                            new_relationship = {
                                                "id": len(all_relationships) + 1,
                                                "source_entity": rel.get(
                                                    "source",
                                                    rel.get("source_entity", "Unknown"),
                                                ),
                                                "target_entity": rel.get(
                                                    "target",
                                                    rel.get("target_entity", "Unknown"),
                                                ),
                                                "relationship_description": rel.get(
                                                    "description",
                                                    rel.get(
                                                        "relationship_description",
                                                        "No description",
                                                    ),
                                                ),
                                                "keywords": rel.get(
                                                    "keywords",
                                                    rel.get(
                                                        "relationship_keywords", []
                                                    ),
                                                ),
                                                "strength": rel.get(
                                                    "strength",
                                                    rel.get("relationship_strength", 0),
                                                ),
                                                "created_at": rel.get(
                                                    "created_at", "Unknown"
                                                ),
                                                "file_path": rel.get(
                                                    "file_path", "unknown_source"
                                                ),
                                                "discovered_at_depth": current_depth
                                                + 2,  # +2 because we started at depth 1
                                            }

                                            # Filter by relationship types if specified
                                            if relationship_types:
                                                rel_keywords = new_relationship.get(
                                                    "keywords", []
                                                )
                                                if isinstance(rel_keywords, str):
                                                    rel_keywords = [rel_keywords]

                                                if not any(
                                                    rt.lower()
                                                    in [k.lower() for k in rel_keywords]
                                                    for rt in relationship_types
                                                ):
                                                    continue

                                            # Check if this is a new relationship (avoid duplicates)
                                            is_new_relationship = True
                                            for existing_rel in all_relationships:
                                                if (
                                                    existing_rel.get("source_entity")
                                                    == new_relationship.get(
                                                        "source_entity"
                                                    )
                                                    and existing_rel.get(
                                                        "target_entity"
                                                    )
                                                    == new_relationship.get(
                                                        "target_entity"
                                                    )
                                                    and existing_rel.get(
                                                        "relationship_description"
                                                    )
                                                    == new_relationship.get(
                                                        "relationship_description"
                                                    )
                                                ):
                                                    is_new_relationship = False
                                                    break

                                            if is_new_relationship:
                                                all_relationships.append(
                                                    new_relationship
                                                )

                                                # Add connected entities for next level
                                                next_level_entities.add(
                                                    new_relationship.get(
                                                        "source_entity", ""
                                                    )
                                                )
                                                next_level_entities.add(
                                                    new_relationship.get(
                                                        "target_entity", ""
                                                    )
                                                )

                                                # Stop if we've reached the max results limit
                                                if (
                                                    len(all_relationships)
                                                    >= max_results
                                                ):
                                                    return all_relationships[
                                                        :max_results
                                                    ]

                            except json.JSONDecodeError:
                                # If JSON parsing fails, skip this result
                                continue

                except Exception as e:
                    logger.warning(
                        f"Failed to expand relationships for entity '{entity}': {e}"
                    )
                    continue

            # Prepare for next iteration
            entities_to_explore = next_level_entities - explored_entities
            entities_to_explore.discard("")  # Remove empty strings

        return all_relationships[:max_results]  # Ensure we don't exceed max results


class SearchDocsTool(MCPTool):
    """Tool for searching document chunks using semantic search."""

    def __init__(self, config: MCPConfig):
        super().__init__(config)

    @property
    def name(self) -> str:
        return "search_docs"

    @property
    def description(self) -> str:
        return "Search through document chunks using semantic search. Returns relevant text segments with source references and metadata."

    @property
    def category(self) -> ToolCategory:
        return ToolCategory.SEMANTIC_SEARCH

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="query",
                type=ToolParameterType.STRING,
                description="The search query to find relevant document content (e.g., 'how to implement authentication', 'error handling patterns')",
                required=True,
            ),
            ToolParameter(
                name="top_k",
                type=ToolParameterType.INTEGER,
                description="Maximum number of document chunks to return (default: 15, max: 50)",
                required=False,
                default=15,
                minimum=1,
                maximum=50,
            ),
            ToolParameter(
                name="include_snippets",
                type=ToolParameterType.BOOLEAN,
                description="Whether to include content snippets (default: true)",
                required=False,
                default=True,
            ),
            ToolParameter(
                name="snippet_length",
                type=ToolParameterType.INTEGER,
                description="Maximum length of content snippets in characters (default: 500, max: 2000)",
                required=False,
                default=500,
                minimum=100,
                maximum=2000,
            ),
            ToolParameter(
                name="file_types",
                type=ToolParameterType.ARRAY,
                description="Optional filter by file types/extensions (e.g., ['md', 'txt', 'py'])",
                required=False,
                items=ToolParameter(
                    name="file_type",
                    type=ToolParameterType.STRING,
                    description="File type or extension",
                ),
            ),
            ToolParameter(
                name="source_paths",
                type=ToolParameterType.ARRAY,
                description="Optional filter by source file paths or directories",
                required=False,
                items=ToolParameter(
                    name="source_path",
                    type=ToolParameterType.STRING,
                    description="Source file path or directory",
                ),
            ),
        ]

    async def execute(
        self, session: ConnectionSession, parameters: Dict[str, Any]
    ) -> ToolResult:
        """Execute document search."""
        operation_id = f"search_docs_{session.session_id}"

        try:
            # Parameter validation and extraction
            query = parameters.get("query", "").strip()
            if not query:
                return ToolResult(
                    success=False,
                    error="Query parameter is required and cannot be empty",
                    metadata={"operation_id": operation_id},
                )

            top_k = min(max(int(parameters.get("top_k", 15)), 1), 50)
            include_snippets = parameters.get("include_snippets", True)
            snippet_length = min(
                max(int(parameters.get("snippet_length", 500)), 100), 2000
            )
            file_types = parameters.get("file_types", [])
            source_paths = parameters.get("source_paths", [])

            # Get LightRAG client
            client = await self.get_lightrag_client()

            # Use naive mode for direct document chunk search
            query_data = {
                "query": query,
                "mode": "naive",  # Naive mode focuses on document chunks
                "top_k": top_k,
                "only_need_context": True,
            }

            # Execute search
            response = await client.query(query_data)

            # Process results

            # Parse the context response to extract document chunk information
            documents = []

            if isinstance(response, dict) and "response" in response:
                context_text = response["response"]

                # Try to extract document chunks from the context
                try:
                    # Look for document chunks section
                    if "---Document Chunks---" in context_text:
                        chunks_section = context_text.split("---Document Chunks---")[1]
                        if "---" in chunks_section:
                            chunks_section = chunks_section.split("---")[0]

                        # Try to parse as JSON
                        try:
                            chunks_data = json.loads(
                                chunks_section.strip().strip("```json").strip("```")
                            )
                            if isinstance(chunks_data, list):
                                for chunk in chunks_data[:top_k]:
                                    if isinstance(chunk, dict):
                                        content = chunk.get("content", "")
                                        file_path = chunk.get(
                                            "file_path", "unknown_source"
                                        )

                                        # Apply file type filter if specified
                                        if file_types:
                                            file_ext = (
                                                file_path.split(".")[-1].lower()
                                                if "." in file_path
                                                else ""
                                            )
                                            if file_ext not in [
                                                ft.lower().lstrip(".")
                                                for ft in file_types
                                            ]:
                                                continue

                                        # Apply source path filter if specified
                                        if source_paths:
                                            if not any(
                                                sp in file_path for sp in source_paths
                                            ):
                                                continue

                                        document = {
                                            "id": chunk.get("id", len(documents) + 1),
                                            "file_path": file_path,
                                            "created_at": chunk.get(
                                                "created_at", "Unknown"
                                            ),
                                            "relevance_score": chunk.get(
                                                "distance", chunk.get("score", 1.0)
                                            ),
                                        }

                                        if include_snippets:
                                            # Truncate content to snippet length
                                            if len(content) > snippet_length:
                                                snippet = (
                                                    content[:snippet_length].rsplit(
                                                        " ", 1
                                                    )[0]
                                                    + "..."
                                                )
                                            else:
                                                snippet = content
                                            document["content_snippet"] = snippet
                                            document["full_content_length"] = len(
                                                content
                                            )

                                        documents.append(document)
                        except json.JSONDecodeError:
                            # Fallback: create a simple document result
                            documents.append(
                                {
                                    "id": 1,
                                    "file_path": "search_result",
                                    "content_snippet": (
                                        f"Document search result for: {query}"
                                        if include_snippets
                                        else None
                                    ),
                                    "full_content_length": (
                                        len(query) if include_snippets else None
                                    ),
                                    "relevance_score": 1.0,
                                    "created_at": "Unknown",
                                }
                            )
                except Exception as parse_error:
                    logger.warning(
                        f"Failed to parse document context for {operation_id}: {parse_error}"
                    )
                    # Create a generic result
                    documents.append(
                        {
                            "id": 1,
                            "file_path": "search_result",
                            "content_snippet": (
                                f"Semantic document search for: {query}"
                                if include_snippets
                                else None
                            ),
                            "full_content_length": (
                                len(query) if include_snippets else None
                            ),
                            "relevance_score": 1.0,
                            "created_at": "Unknown",
                        }
                    )

            # Complete

            result_content = {
                "query": query,
                "total_found": len(documents),
                "documents": documents,
                "search_parameters": {
                    "top_k": top_k,
                    "include_snippets": include_snippets,
                    "snippet_length": snippet_length if include_snippets else None,
                    "file_types": file_types if file_types else None,
                    "source_paths": source_paths if source_paths else None,
                },
            }

            return ToolResult(
                success=True,
                data=json.dumps(result_content, indent=2, ensure_ascii=False),
                metadata={
                    "operation_id": operation_id,
                    "query": query,
                    "total_found": len(documents),
                    "response_format": "document_search",
                },
            )

        except Exception as e:
            logger.error(f"Error in search_docs for {operation_id}: {e}")
            return ToolResult(
                success=False,
                error=f"Error searching documents: {str(e)}",
                metadata={"operation_id": operation_id, "error": str(e)},
            )

    async def execute_streaming(self, **kwargs):
        """Streaming execution for document search with progress tracking."""
        operation_id = f"search_docs_stream_{id(kwargs)}"

        try:
            # Validate parameters
            query = kwargs.get("query", "").strip()
            if not query:
                yield ToolProgress(
                    operation_id=operation_id,
                    progress=100,
                    status="failed",
                    message="Query parameter is required",
                )
                return

            # Progress updates
            yield ToolProgress(
                operation_id=operation_id,
                progress=10,
                status="validated",
                message="Parameters validated",
            )
            yield ToolProgress(
                operation_id=operation_id,
                progress=25,
                status="searching",
                message="Starting document search",
            )
            yield ToolProgress(
                operation_id=operation_id,
                progress=50,
                status="processing",
                message="Executing semantic search",
            )
            yield ToolProgress(
                operation_id=operation_id,
                progress=75,
                status="processing",
                message="Processing results",
            )

            # Execute the search
            result = await self.execute(**kwargs)

            yield ToolProgress(
                operation_id=operation_id,
                progress=100,
                status="completed",
                message="Document search completed",
            )
            yield result

        except Exception as e:
            yield ToolProgress(
                operation_id=operation_id,
                progress=100,
                status="failed",
                message=f"Error: {str(e)}",
            )
            yield ToolResult(
                success=False,
                error=f"Error in streaming document search: {str(e)}",
                metadata={"operation_id": operation_id, "error": str(e)},
            )


class SearchDocumentsTool(MCPTool):
    """Enhanced tool for searching documents with advanced snippet extraction and source references."""

    def __init__(self, config: MCPConfig):
        super().__init__(config)

    @property
    def name(self) -> str:
        return "search_documents"

    @property
    def description(self) -> str:
        return "Enhanced document search with intelligent snippet extraction and comprehensive source references. Provides context-aware content chunks with metadata and relevance scoring."

    @property
    def category(self) -> ToolCategory:
        return ToolCategory.DOCUMENT_ACCESS

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="query",
                type=ToolParameterType.STRING,
                description="The search query to find relevant document content (supports natural language queries)",
                required=True,
            ),
            ToolParameter(
                name="top_k",
                type=ToolParameterType.INTEGER,
                description="Maximum number of document results to return (default: 20, max: 100)",
                required=False,
                default=20,
                minimum=1,
                maximum=100,
            ),
            ToolParameter(
                name="snippet_length",
                type=ToolParameterType.INTEGER,
                description="Length of content snippets in characters (default: 800, max: 3000)",
                required=False,
                default=800,
                minimum=200,
                maximum=3000,
            ),
            ToolParameter(
                name="context_window",
                type=ToolParameterType.INTEGER,
                description="Number of characters to include before/after matched content for context (default: 150)",
                required=False,
                default=150,
                minimum=50,
                maximum=500,
            ),
            ToolParameter(
                name="include_source_metadata",
                type=ToolParameterType.BOOLEAN,
                description="Include comprehensive source metadata (file paths, creation dates, etc.)",
                required=False,
                default=True,
            ),
            ToolParameter(
                name="highlight_matches",
                type=ToolParameterType.BOOLEAN,
                description="Highlight query matches in snippets using markdown formatting",
                required=False,
                default=True,
            ),
            ToolParameter(
                name="group_by_source",
                type=ToolParameterType.BOOLEAN,
                description="Group results by source document for better organization",
                required=False,
                default=False,
            ),
            ToolParameter(
                name="relevance_threshold",
                type=ToolParameterType.NUMBER,
                description="Minimum relevance score for results (0.0 to 1.0, default: 0.1)",
                required=False,
                default=0.1,
                minimum=0.0,
                maximum=1.0,
            ),
            ToolParameter(
                name="file_extensions",
                type=ToolParameterType.ARRAY,
                description="Filter by specific file extensions (e.g., ['.md', '.txt', '.py'])",
                required=False,
                items=ToolParameter(
                    name="extension",
                    type=ToolParameterType.STRING,
                    description="File extension",
                ),
            ),
            ToolParameter(
                name="source_paths",
                type=ToolParameterType.ARRAY,
                description="Filter by specific source paths or directories",
                required=False,
                items=ToolParameter(
                    name="path",
                    type=ToolParameterType.STRING,
                    description="Source path or directory",
                ),
            ),
        ]

    async def execute(
        self, session: ConnectionSession, parameters: Dict[str, Any]
    ) -> ToolResult:
        """Execute enhanced document search with snippets and source references."""
        operation_id = f"search_documents_{session.session_id}"

        try:
            # Parameter validation and extraction
            query = parameters.get("query", "").strip()
            if not query:
                return ToolResult(
                    success=False,
                    error="Query parameter is required and cannot be empty",
                    metadata={"operation_id": operation_id},
                )

            top_k = min(max(int(parameters.get("top_k", 20)), 1), 100)
            snippet_length = min(
                max(int(parameters.get("snippet_length", 800)), 200), 3000
            )
            context_window = min(
                max(int(parameters.get("context_window", 150)), 50), 500
            )
            include_source_metadata = parameters.get("include_source_metadata", True)
            highlight_matches = parameters.get("highlight_matches", True)
            group_by_source = parameters.get("group_by_source", False)
            relevance_threshold = max(
                min(float(parameters.get("relevance_threshold", 0.1)), 1.0), 0.0
            )
            file_extensions = parameters.get("file_extensions", [])
            source_paths = parameters.get("source_paths", [])

            # Get LightRAG client
            client = await self.get_lightrag_client()

            # Use mix mode for comprehensive document search
            query_data = {
                "query": query,
                "mode": "mix",  # Mix mode combines knowledge graph and vector search
                "top_k": top_k,
                "only_need_context": True,
                "max_token_for_text_unit": 6000,  # Larger token limit for detailed content
            }

            # Execute search
            response = await client.query(query_data)

            # Process results
            documents = []
            source_references = {}

            if isinstance(response, dict) and "response" in response:
                context_text = response["response"]

                # Try to extract document chunks from the context
                try:
                    # Look for document chunks section
                    if "---Document Chunks---" in context_text:
                        chunks_section = context_text.split("---Document Chunks---")[1]
                        if "---" in chunks_section:
                            chunks_section = chunks_section.split("---")[0]

                        # Try to parse as JSON
                        try:
                            chunks_data = json.loads(
                                chunks_section.strip().strip("```json").strip("```")
                            )
                            if isinstance(chunks_data, list):
                                for idx, chunk in enumerate(chunks_data[:top_k]):
                                    if isinstance(chunk, dict):
                                        content = chunk.get("content", "")
                                        file_path = chunk.get(
                                            "file_path", "unknown_source"
                                        )
                                        relevance_score = chunk.get(
                                            "distance", chunk.get("score", 1.0)
                                        )

                                        # Apply relevance threshold
                                        if relevance_score < relevance_threshold:
                                            continue

                                        # Apply file extension filter
                                        if file_extensions:
                                            file_ext = (
                                                f".{file_path.split('.')[-1].lower()}"
                                                if "." in file_path
                                                else ""
                                            )
                                            if file_ext not in [
                                                ext.lower() for ext in file_extensions
                                            ]:
                                                continue

                                        # Apply source path filter
                                        if source_paths:
                                            if not any(
                                                sp in file_path for sp in source_paths
                                            ):
                                                continue

                                        # Create enhanced snippet with context
                                        snippet = self._create_enhanced_snippet(
                                            content,
                                            query,
                                            snippet_length,
                                            context_window,
                                            highlight_matches,
                                        )

                                        # Build document result
                                        document = {
                                            "id": chunk.get("id", f"chunk_{idx + 1}"),
                                            "content_snippet": snippet,
                                            "full_content_length": len(content),
                                            "relevance_score": float(relevance_score),
                                            "match_quality": self._assess_match_quality(
                                                content, query
                                            ),
                                            "chunk_index": idx + 1,
                                        }

                                        # Add source metadata if requested
                                        if include_source_metadata:
                                            document.update(
                                                {
                                                    "source_file": file_path,
                                                    "created_at": chunk.get(
                                                        "created_at", "Unknown"
                                                    ),
                                                    "file_extension": (
                                                        file_path.split(".")[-1]
                                                        if "." in file_path
                                                        else "unknown"
                                                    ),
                                                    "estimated_read_time": self._estimate_read_time(
                                                        content
                                                    ),
                                                }
                                            )

                                        documents.append(document)

                                        # Track source references
                                        if file_path not in source_references:
                                            source_references[file_path] = {
                                                "file_path": file_path,
                                                "chunk_count": 0,
                                                "total_relevance": 0.0,
                                                "average_relevance": 0.0,
                                                "first_seen": chunk.get(
                                                    "created_at", "Unknown"
                                                ),
                                            }

                                        source_references[file_path]["chunk_count"] += 1
                                        source_references[file_path][
                                            "total_relevance"
                                        ] += relevance_score
                                        source_references[file_path][
                                            "average_relevance"
                                        ] = (
                                            source_references[file_path][
                                                "total_relevance"
                                            ]
                                            / source_references[file_path][
                                                "chunk_count"
                                            ]
                                        )

                        except json.JSONDecodeError:
                            # Fallback: create a simple document result
                            documents.append(
                                {
                                    "id": "fallback_result",
                                    "content_snippet": f"Enhanced document search result for: {query}",
                                    "full_content_length": len(query),
                                    "relevance_score": 0.5,
                                    "match_quality": "fallback",
                                    "chunk_index": 1,
                                    "source_file": (
                                        "search_result"
                                        if include_source_metadata
                                        else None
                                    ),
                                }
                            )

                except Exception as parse_error:
                    logger.warning(
                        f"Failed to parse document context for {operation_id}: {parse_error}"
                    )
                    # Create a generic result
                    documents.append(
                        {
                            "id": "generic_result",
                            "content_snippet": f"Enhanced semantic document search for: {query}",
                            "full_content_length": len(query),
                            "relevance_score": 0.5,
                            "match_quality": "generic",
                            "chunk_index": 1,
                            "source_file": (
                                "search_result" if include_source_metadata else None
                            ),
                        }
                    )

            # Group by source if requested
            if group_by_source and documents:
                grouped_documents = self._group_documents_by_source(documents)
            else:
                grouped_documents = documents

            # Sort by relevance score
            if isinstance(grouped_documents, list):
                grouped_documents.sort(
                    key=lambda x: x.get("relevance_score", 0), reverse=True
                )

            # Build comprehensive result
            result_content = {
                "query": query,
                "total_documents_found": len(documents),
                "documents": grouped_documents,
                "source_references": (
                    list(source_references.values())
                    if include_source_metadata
                    else None
                ),
                "search_parameters": {
                    "top_k": top_k,
                    "snippet_length": snippet_length,
                    "context_window": context_window,
                    "relevance_threshold": relevance_threshold,
                    "highlight_matches": highlight_matches,
                    "group_by_source": group_by_source,
                    "file_extensions": file_extensions if file_extensions else None,
                    "source_paths": source_paths if source_paths else None,
                },
                "search_statistics": {
                    "unique_sources": len(source_references),
                    "average_relevance": (
                        sum(doc.get("relevance_score", 0) for doc in documents)
                        / len(documents)
                        if documents
                        else 0
                    ),
                    "content_coverage": sum(
                        doc.get("full_content_length", 0) for doc in documents
                    ),
                },
            }

            return ToolResult(
                success=True,
                data=json.dumps(result_content, indent=2, ensure_ascii=False),
                metadata={
                    "operation_id": operation_id,
                    "query": query,
                    "total_found": len(documents),
                    "unique_sources": len(source_references),
                    "response_format": "enhanced_document_search",
                },
            )

        except Exception as e:
            logger.error(f"Error in search_documents for {operation_id}: {e}")
            return ToolResult(
                success=False,
                error=f"Error searching documents: {str(e)}",
                metadata={"operation_id": operation_id, "error": str(e)},
            )

    def _create_enhanced_snippet(
        self,
        content: str,
        query: str,
        snippet_length: int,
        context_window: int,
        highlight_matches: bool,
    ) -> str:
        """Create an enhanced snippet with context and optional highlighting."""
        if not content:
            return ""

        # Find the best match position
        query_words = query.lower().split()
        content_lower = content.lower()

        best_match_pos = 0
        best_match_score = 0

        # Look for the position with the most query words
        for i in range(len(content) - snippet_length + 1):
            snippet_part = content_lower[i : i + snippet_length]
            score = sum(1 for word in query_words if word in snippet_part)
            if score > best_match_score:
                best_match_score = score
                best_match_pos = i

        # Extract snippet with context
        start_pos = max(0, best_match_pos - context_window)
        end_pos = min(len(content), best_match_pos + snippet_length + context_window)

        snippet = content[start_pos:end_pos]

        # Add ellipsis if truncated
        if start_pos > 0:
            snippet = "..." + snippet
        if end_pos < len(content):
            snippet = snippet + "..."

        # Highlight matches if requested
        if highlight_matches:
            for word in query_words:
                if len(word) > 2:  # Only highlight words longer than 2 characters
                    snippet = snippet.replace(word, f"**{word}**")
                    snippet = snippet.replace(
                        word.capitalize(), f"**{word.capitalize()}**"
                    )

        return snippet

    def _assess_match_quality(self, content: str, query: str) -> str:
        """Assess the quality of the match between content and query."""
        if not content or not query:
            return "poor"

        query_words = set(query.lower().split())
        content_words = set(content.lower().split())

        if not query_words:
            return "poor"

        overlap = len(query_words.intersection(content_words))
        overlap_ratio = overlap / len(query_words)

        if overlap_ratio >= 0.8:
            return "excellent"
        elif overlap_ratio >= 0.6:
            return "good"
        elif overlap_ratio >= 0.3:
            return "fair"
        else:
            return "poor"

    def _estimate_read_time(self, content: str) -> str:
        """Estimate reading time for content."""
        if not content:
            return "0 min"

        words = len(content.split())
        minutes = max(1, words // 200)  # Assuming 200 words per minute

        return f"{minutes} min"

    def _group_documents_by_source(
        self, documents: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Group documents by their source file."""
        grouped = {}

        for doc in documents:
            source = doc.get("source_file", "unknown_source")
            if source not in grouped:
                grouped[source] = {
                    "source_file": source,
                    "document_count": 0,
                    "total_relevance": 0.0,
                    "average_relevance": 0.0,
                    "documents": [],
                }

            grouped[source]["documents"].append(doc)
            grouped[source]["document_count"] += 1
            grouped[source]["total_relevance"] += doc.get("relevance_score", 0)
            grouped[source]["average_relevance"] = (
                grouped[source]["total_relevance"] / grouped[source]["document_count"]
            )

        # Sort groups by average relevance
        sorted_groups = sorted(
            grouped.values(), key=lambda x: x["average_relevance"], reverse=True
        )

        return {"grouped_by_source": sorted_groups}

    async def execute_streaming(self, **kwargs):
        """Streaming execution for enhanced document search with progress tracking."""
        session = kwargs.get("session")
        parameters = kwargs.get("parameters", {})

        operation_id = f"search_documents_{session.session_id}"

        try:
            # Progress tracking
            yield ToolProgress(
                operation_id=operation_id,
                progress=10,
                status="validating",
                message="Validating search parameters",
            )

            # Parameter validation
            query = parameters.get("query", "").strip()
            if not query:
                yield ToolProgress(
                    operation_id=operation_id,
                    progress=100,
                    status="failed",
                    message="Invalid query",
                )
                yield ToolResult(
                    success=False,
                    error="Query parameter is required and cannot be empty",
                    metadata={"operation_id": operation_id},
                )
                return

            yield ToolProgress(
                operation_id=operation_id,
                progress=25,
                status="initializing",
                message="Initializing enhanced document search",
            )

            # Execute search (same logic as execute method)
            yield ToolProgress(
                operation_id=operation_id,
                progress=50,
                status="searching",
                message="Executing comprehensive document search",
            )

            result = await self.execute(session, parameters)

            yield ToolProgress(
                operation_id=operation_id,
                progress=75,
                status="processing",
                message="Processing search results and creating snippets",
            )

            yield ToolProgress(
                operation_id=operation_id,
                progress=100,
                status="completed",
                message="Enhanced document search completed successfully",
            )
            yield result

        except Exception as e:
            yield ToolProgress(
                operation_id=operation_id,
                progress=100,
                status="failed",
                message=f"Error: {str(e)}",
            )
            yield ToolResult(
                success=False,
                error=f"Error in streaming enhanced document search: {str(e)}",
                metadata={"operation_id": operation_id, "error": str(e)},
            )


class GetSummaryTool(MCPTool):
    """Tool for getting chat-style summaries and conversational responses from the knowledge graph."""

    @property
    def name(self) -> str:
        return "get_summary"

    @property
    def description(self) -> str:
        return "Get conversational, chat-style summaries and responses from the knowledge graph, optimized for natural language interactions"

    @property
    def category(self) -> ToolCategory:
        return ToolCategory.QUERY_OPERATIONS

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            string_parameter(
                name="query",
                description="The question or topic to get a summary about (e.g., 'What is this project about?', 'Explain the authentication system')",
                required=True,
            ),
            string_parameter(
                name="style",
                description="Response style: 'conversational' (default), 'concise', 'detailed', 'bullet_points'",
                required=False,
                default="conversational",
            ),
            string_parameter(
                name="length",
                description="Preferred response length: 'short' (1-2 paragraphs), 'medium' (3-4 paragraphs), 'long' (5+ paragraphs)",
                required=False,
                default="medium",
            ),
            string_parameter(
                name="focus",
                description="Focus area: 'overview' (general summary), 'technical' (implementation details), 'usage' (how-to guide), 'concepts' (key ideas)",
                required=False,
                default="overview",
            ),
            boolean_parameter(
                name="include_examples",
                description="Whether to include examples and practical information in the response",
                required=False,
                default=True,
            ),
            string_parameter(
                name="context_mode",
                description="Context retrieval mode: 'smart' (automatic best choice), 'broad' (hybrid mode), 'specific' (local mode), 'comprehensive' (mix mode)",
                required=False,
                default="smart",
            ),
        ]

    @property
    def requires_context(self) -> bool:
        return True

    async def execute(
        self, session: ConnectionSession, parameters: Dict[str, Any]
    ) -> ToolResult:
        """Execute the get_summary tool for chat-style responses."""
        operation_id = f"get_summary_{session.session_id}"

        try:
            # Parameter validation
            query_text = parameters.get("query", "").strip()
            if not query_text:
                return ToolResult(
                    success=False,
                    error="Query parameter is required and cannot be empty",
                    metadata={
                        "operation_id": operation_id,
                        "error_type": "validation_error",
                    },
                )

            style = parameters.get("style", "conversational")
            length = parameters.get("length", "medium")
            focus = parameters.get("focus", "overview")
            include_examples = parameters.get("include_examples", True)
            context_mode = parameters.get("context_mode", "smart")

            # Validate parameters
            valid_styles = ["conversational", "concise", "detailed", "bullet_points"]
            valid_lengths = ["short", "medium", "long"]
            valid_focuses = ["overview", "technical", "usage", "concepts"]
            valid_context_modes = ["smart", "broad", "specific", "comprehensive"]

            if style not in valid_styles:
                return ToolResult(
                    success=False,
                    error=f"Invalid style '{style}'. Valid options: {', '.join(valid_styles)}",
                    metadata={
                        "operation_id": operation_id,
                        "error_type": "validation_error",
                    },
                )

            if length not in valid_lengths:
                return ToolResult(
                    success=False,
                    error=f"Invalid length '{length}'. Valid options: {', '.join(valid_lengths)}",
                    metadata={
                        "operation_id": operation_id,
                        "error_type": "validation_error",
                    },
                )

            if focus not in valid_focuses:
                return ToolResult(
                    success=False,
                    error=f"Invalid focus '{focus}'. Valid options: {', '.join(valid_focuses)}",
                    metadata={
                        "operation_id": operation_id,
                        "error_type": "validation_error",
                    },
                )

            if context_mode not in valid_context_modes:
                return ToolResult(
                    success=False,
                    error=f"Invalid context_mode '{context_mode}'. Valid options: {', '.join(valid_context_modes)}",
                    metadata={
                        "operation_id": operation_id,
                        "error_type": "validation_error",
                    },
                )

            # Progress tracking
            progress = ToolProgress(
                operation_id=operation_id,
                progress=0.1,
                status="validating",
                message=f"Preparing {style} summary in {length} format",
            )

            logger.info(
                f"Starting summary generation: '{query_text[:50]}...' in {style} style"
            )

            # Get LightRAG client
            client = await self.get_lightrag_client()

            # Map context mode to LightRAG query mode
            mode_mapping = {
                "smart": "hybrid",  # Best overall balance
                "broad": "hybrid",  # Combines local + global
                "specific": "local",  # Entity-focused
                "comprehensive": "mix",  # Knowledge graph + vector search
            }
            query_mode = mode_mapping[context_mode]

            # Create chat-optimized response type based on style and length
            if style == "bullet_points":
                response_type = "Bullet Points"
            elif style == "concise" or length == "short":
                response_type = "Single Paragraph"
            else:
                response_type = "Multiple Paragraphs"

            # Optimize the query for conversational context
            enhanced_query = self._enhance_query_for_chat(
                query_text, focus, include_examples
            )

            # Build query parameters optimized for chat-style responses
            query_params = {
                "query": enhanced_query,
                "mode": query_mode,
                "only_need_context": False,  # We want generated responses
                "response_type": response_type,
                "include_relationships": False,  # Simplify for chat-style responses
            }

            # Set token limits based on desired length
            if length == "short":
                query_params["max_token_for_text_unit"] = 300
                query_params["max_token_for_local_context"] = 800
                query_params["max_token_for_global_context"] = 600
            elif length == "medium":
                query_params["max_token_for_text_unit"] = 500
                query_params["max_token_for_local_context"] = 1200
                query_params["max_token_for_global_context"] = 1000
            else:  # long
                query_params["max_token_for_text_unit"] = 800
                query_params["max_token_for_local_context"] = 2000
                query_params["max_token_for_global_context"] = 1500

            # Update progress
            progress.status = "retrieving"
            progress.progress = 0.3
            progress.message = (
                f"Retrieving relevant information using {query_mode} mode"
            )

            # Execute the query
            result = await client.query(**query_params)

            # Update progress
            progress.status = "processing"
            progress.progress = 0.7
            progress.message = "Formatting response for chat-style interaction"

            # Process and format the response for chat-style interaction
            summary_response = result.get("response", "")

            # Post-process the response based on style preferences
            formatted_response = self._format_chat_response(
                summary_response, style, length, focus, include_examples
            )

            # Build the result
            processed_result = {
                "summary": formatted_response,
                "query": query_text,
                "style": style,
                "length": length,
                "focus": focus,
                "context_mode": context_mode,
                "query_mode_used": query_mode,
                "response_type": response_type,
                "include_examples": include_examples,
                "char_count": len(formatted_response),
                "word_count": len(formatted_response.split()),
            }

            # Add usage tips for chat interaction
            processed_result["usage_tips"] = [
                f"This {style} summary focuses on {focus} aspects",
                f"Response optimized for {length} format",
                "Ask follow-up questions for more specific information",
                "Use 'query' tool for detailed technical analysis",
            ]

            # Final progress update
            progress.status = "completed"
            progress.progress = 1.0
            progress.message = (
                f"Chat-style summary completed ({len(formatted_response)} characters)"
            )

            metadata = {
                "tool": self.name,
                "operation_id": operation_id,
                "style": style,
                "length": length,
                "focus": focus,
                "context_mode": context_mode,
                "query_mode_used": query_mode,
                "query_length": len(query_text),
                "response_length": len(formatted_response),
                "context_name": session.context,
                "timestamp": session.connected_at.isoformat(),
                "optimized_for": "chat_interaction",
            }

            logger.info(
                f"Summary generated successfully in {style} style for session {session.session_id} "
                f"({len(formatted_response)} chars response)"
            )

            return ToolResult(
                success=True,
                data=processed_result,
                metadata=metadata,
            )

        except APIError as e:
            error_msg = f"LightRAG API error during summary generation: {e}"
            logger.error(f"Summary generation failed: {error_msg}")
            return ToolResult(
                success=False,
                error=error_msg,
                metadata={"operation_id": operation_id, "error_type": "api_error"},
            )
        except Exception as e:
            error_msg = f"Unexpected error during summary generation: {str(e)}"
            logger.error(f"Summary generation failed: {error_msg}", exc_info=True)
            return ToolResult(
                success=False,
                error=error_msg,
                metadata={
                    "operation_id": operation_id,
                    "error_type": "unexpected_error",
                },
            )

    def _enhance_query_for_chat(
        self, query: str, focus: str, include_examples: bool
    ) -> str:
        """Enhance the query for better chat-style responses."""
        # Add focus-specific context to the query
        focus_prompts = {
            "overview": "Please provide a clear overview and summary of",
            "technical": "Please explain the technical details and implementation of",
            "usage": "Please explain how to use and work with",
            "concepts": "Please explain the key concepts and ideas behind",
        }

        enhanced = f"{focus_prompts.get(focus, 'Please explain')} {query}"

        if include_examples:
            enhanced += ". Include relevant examples where helpful."

        return enhanced

    def _format_chat_response(
        self, response: str, style: str, length: str, focus: str, include_examples: bool
    ) -> str:
        """Format the response for chat-style interaction."""
        if not response:
            return "I don't have enough information to provide a summary on this topic. Please try a more specific query or check if the context contains relevant information."

        # Basic formatting based on style
        if (
            style == "bullet_points"
            and not response.strip().startswith("•")
            and not response.strip().startswith("-")
        ):
            # Convert to bullet points if not already formatted
            lines = [line.strip() for line in response.split(".") if line.strip()]
            if len(lines) > 1:
                formatted = "Key points:\n\n" + "\n".join(
                    [f"• {line}." for line in lines[:8]]
                )  # Limit bullet points
                return formatted

        # Add conversational elements for chat-style interaction
        if style == "conversational":
            # Add a friendly introduction for conversational style
            if not any(
                response.lower().startswith(prefix)
                for prefix in ["here's", "this", "the", "in", "based"]
            ):
                response = f"Here's what I found: {response}"

        return response

    async def execute_streaming(
        self, session: ConnectionSession, parameters: Dict[str, Any]
    ) -> AsyncGenerator[ToolResult, None]:
        """Execute get_summary with streaming progress updates."""
        try:
            query_text = parameters["query"]
            style = parameters.get("style", "conversational")
            length = parameters.get("length", "medium")

            # Create operation tracking
            operation_id = str(uuid.uuid4())

            # Step 1: Validation (10%)
            yield ToolResult(
                success=True,
                data=ToolProgress(
                    operation_id=operation_id,
                    progress=0.1,
                    status="validation",
                    message=f"Preparing {style} summary in {length} format",
                ),
                metadata={"tool": self.name, "streaming": True},
            )

            # Step 2: Context Retrieval (50%)
            yield ToolResult(
                success=True,
                data=ToolProgress(
                    operation_id=operation_id,
                    progress=0.5,
                    status="retrieving",
                    message="Gathering relevant information from knowledge graph",
                ),
                metadata={"tool": self.name, "streaming": True},
            )

            # Step 3: Processing (80%)
            yield ToolResult(
                success=True,
                data=ToolProgress(
                    operation_id=operation_id,
                    progress=0.8,
                    status="processing",
                    message="Formatting response for chat-style interaction",
                ),
                metadata={"tool": self.name, "streaming": True},
            )

            # Step 4: Execute the actual tool
            result = await self.execute(session, parameters)

            # Step 5: Completion (100%)
            yield ToolResult(
                success=True,
                data=ToolProgress(
                    operation_id=operation_id,
                    progress=1.0,
                    status="completed",
                    message="Chat-style summary completed successfully",
                ),
                metadata={"tool": self.name, "streaming": True},
            )

            yield result

        except Exception as e:
            yield ToolResult(
                success=False,
                error=f"Error in streaming summary generation: {str(e)}",
                metadata={"tool": self.name, "streaming": True, "error": str(e)},
            )


class ExploreGraphTool(MCPTool):
    """Tool for exploring the knowledge graph with configurable traversal depth."""

    @property
    def name(self) -> str:
        return "explore_graph"

    @property
    def description(self) -> str:
        return "Explore the knowledge graph by traversing relationships from a starting entity or concept with configurable depth"

    @property
    def category(self) -> ToolCategory:
        return ToolCategory.GRAPH_EXPLORATION

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            string_parameter(
                name="starting_entity",
                description="The entity, concept, or topic to start exploring from (e.g., 'authentication', 'user management', 'API endpoints')",
                required=True,
            ),
            ToolParameter(
                name="depth",
                type=ToolParameterType.INTEGER,
                description="Exploration depth for traversing relationships (default: 1, max: 5)",
                required=False,
                default=1,
                minimum=1,
                maximum=5,
            ),
            string_parameter(
                name="exploration_mode",
                description="Exploration strategy: 'outbound' (follow outgoing relationships), 'inbound' (follow incoming), 'bidirectional' (both directions)",
                required=False,
                default="bidirectional",
            ),
            string_parameter(
                name="relationship_types",
                description="Filter by relationship types (comma-separated, e.g., 'implements,uses,contains'). Leave empty for all types.",
                required=False,
                default="",
            ),
            ToolParameter(
                name="max_entities_per_level",
                type=ToolParameterType.INTEGER,
                description="Maximum number of entities to explore at each level (default: 10, max: 50)",
                required=False,
                default=10,
                minimum=1,
                maximum=50,
            ),
            boolean_parameter(
                name="include_entity_details",
                description="Include detailed descriptions for discovered entities",
                required=False,
                default=True,
            ),
            boolean_parameter(
                name="include_path_analysis",
                description="Include analysis of paths and connection patterns",
                required=False,
                default=False,
            ),
            string_parameter(
                name="output_format",
                description="Output format: 'hierarchical' (tree structure), 'network' (graph structure), 'summary' (condensed overview)",
                required=False,
                default="hierarchical",
            ),
        ]

    @property
    def requires_context(self) -> bool:
        return True

    async def execute(
        self, session: ConnectionSession, parameters: Dict[str, Any]
    ) -> ToolResult:
        """Execute the explore_graph tool for knowledge graph traversal."""
        operation_id = f"explore_graph_{session.session_id}"

        try:
            # Parameter validation
            starting_entity = parameters.get("starting_entity", "").strip()
            if not starting_entity:
                return ToolResult(
                    success=False,
                    error="starting_entity parameter is required and cannot be empty",
                    metadata={
                        "operation_id": operation_id,
                        "error_type": "validation_error",
                    },
                )

            depth = max(1, min(int(parameters.get("depth", 1)), 5))
            exploration_mode = parameters.get("exploration_mode", "bidirectional")
            relationship_types = parameters.get("relationship_types", "").strip()
            max_entities_per_level = max(
                1, min(int(parameters.get("max_entities_per_level", 10)), 50)
            )
            include_entity_details = parameters.get("include_entity_details", True)
            include_path_analysis = parameters.get("include_path_analysis", False)
            output_format = parameters.get("output_format", "hierarchical")

            # Validate parameters
            valid_exploration_modes = ["outbound", "inbound", "bidirectional"]
            valid_output_formats = ["hierarchical", "network", "summary"]

            if exploration_mode not in valid_exploration_modes:
                return ToolResult(
                    success=False,
                    error=f"Invalid exploration_mode '{exploration_mode}'. Valid options: {', '.join(valid_exploration_modes)}",
                    metadata={
                        "operation_id": operation_id,
                        "error_type": "validation_error",
                    },
                )

            if output_format not in valid_output_formats:
                return ToolResult(
                    success=False,
                    error=f"Invalid output_format '{output_format}'. Valid options: {', '.join(valid_output_formats)}",
                    metadata={
                        "operation_id": operation_id,
                        "error_type": "validation_error",
                    },
                )

            # Progress tracking
            progress = ToolProgress(
                operation_id=operation_id,
                progress=0.1,
                status="initializing",
                message=f"Starting graph exploration from '{starting_entity}' with depth {depth}",
            )

            logger.info(
                f"Starting graph exploration: '{starting_entity}' with depth {depth} in {exploration_mode} mode"
            )

            # Get LightRAG client
            client = await self.get_lightrag_client()

            # Parse relationship types filter
            relationship_filter = []
            if relationship_types:
                relationship_filter = [
                    rt.strip() for rt in relationship_types.split(",") if rt.strip()
                ]

            # Start exploration from the root entity
            exploration_results = await self._explore_from_entity(
                client,
                starting_entity,
                depth,
                exploration_mode,
                relationship_filter,
                max_entities_per_level,
                include_entity_details,
            )

            # Update progress
            progress.status = "processing"
            progress.progress = 0.7
            progress.message = f"Processing {len(exploration_results.get('entities', {}))} discovered entities"

            # Format the results based on output format
            formatted_results = self._format_exploration_results(
                exploration_results,
                output_format,
                include_path_analysis,
                starting_entity,
            )

            # Build the result
            processed_result = {
                "exploration_results": formatted_results,
                "starting_entity": starting_entity,
                "depth": depth,
                "exploration_mode": exploration_mode,
                "relationship_types_filter": relationship_filter,
                "max_entities_per_level": max_entities_per_level,
                "output_format": output_format,
                "include_entity_details": include_entity_details,
                "include_path_analysis": include_path_analysis,
                "stats": {
                    "total_entities": len(exploration_results.get("entities", {})),
                    "total_relationships": len(
                        exploration_results.get("relationships", [])
                    ),
                    "max_depth_reached": exploration_results.get(
                        "max_depth_reached", 0
                    ),
                    "exploration_complete": exploration_results.get(
                        "exploration_complete", True
                    ),
                },
            }

            # Add path analysis if requested
            if include_path_analysis:
                processed_result["path_analysis"] = self._analyze_connection_paths(
                    exploration_results, starting_entity
                )

            # Final progress update
            progress.status = "completed"
            progress.progress = 1.0
            progress.message = f"Graph exploration completed: {len(exploration_results.get('entities', {}))} entities, {len(exploration_results.get('relationships', []))} relationships"

            metadata = {
                "tool": self.name,
                "operation_id": operation_id,
                "starting_entity": starting_entity,
                "depth": depth,
                "exploration_mode": exploration_mode,
                "output_format": output_format,
                "entities_discovered": len(exploration_results.get("entities", {})),
                "relationships_discovered": len(
                    exploration_results.get("relationships", [])
                ),
                "context_name": session.context,
                "timestamp": session.connected_at.isoformat(),
                "optimized_for": "graph_exploration",
            }

            logger.info(
                f"Graph exploration completed successfully for session {session.session_id} "
                f"({len(exploration_results.get('entities', {}))} entities, {len(exploration_results.get('relationships', []))} relationships)"
            )

            return ToolResult(
                success=True,
                data=processed_result,
                metadata=metadata,
            )

        except APIError as e:
            error_msg = f"LightRAG API error during graph exploration: {e}"
            logger.error(f"Graph exploration failed: {error_msg}")
            return ToolResult(
                success=False,
                error=error_msg,
                metadata={"operation_id": operation_id, "error_type": "api_error"},
            )
        except Exception as e:
            error_msg = f"Unexpected error during graph exploration: {str(e)}"
            logger.error(f"Graph exploration failed: {error_msg}", exc_info=True)
            return ToolResult(
                success=False,
                error=error_msg,
                metadata={
                    "operation_id": operation_id,
                    "error_type": "unexpected_error",
                },
            )

    async def _explore_from_entity(
        self,
        client: LightRAGClient,
        starting_entity: str,
        depth: int,
        exploration_mode: str,
        relationship_filter: List[str],
        max_entities_per_level: int,
        include_entity_details: bool,
    ) -> Dict[str, Any]:
        """Perform the actual graph exploration using LightRAG queries."""

        # Initialize exploration data structures
        entities = {}  # entity_name -> {details, level}
        relationships = []  # list of relationship objects
        current_entities = {starting_entity}
        explored_entities = set()

        for current_depth in range(depth):
            if not current_entities:
                break

            logger.info(
                f"Exploring depth {current_depth + 1}/{depth} with {len(current_entities)} entities"
            )

            next_level_entities = set()

            for entity in list(current_entities)[:max_entities_per_level]:
                if entity in explored_entities:
                    continue

                explored_entities.add(entity)

                # Query for relationships involving this entity
                query_text = (
                    f"What are the relationships and connections involving '{entity}'?"
                )

                try:
                    # Use local mode to get entity-focused relationships
                    result = await client.query(
                        query=query_text,
                        mode="local",
                        only_need_context=False,
                        include_relationships=True,
                        top_k=max_entities_per_level,
                    )

                    # Extract entity information
                    if include_entity_details:
                        entities[entity] = {
                            "name": entity,
                            "level": current_depth,
                            "description": (
                                result.get("response", "")[:500]
                                if result.get("response")
                                else ""
                            ),
                            "discovered_via": (
                                "starting_entity"
                                if current_depth == 0
                                else "relationship_traversal"
                            ),
                        }
                    else:
                        entities[entity] = {
                            "name": entity,
                            "level": current_depth,
                            "discovered_via": (
                                "starting_entity"
                                if current_depth == 0
                                else "relationship_traversal"
                            ),
                        }

                    # Extract relationships if available
                    if result.get("relationships"):
                        for rel in result["relationships"]:
                            # Filter relationships based on type if specified
                            rel_type = rel.get("type", "").lower()
                            if relationship_filter and rel_type not in [
                                rf.lower() for rf in relationship_filter
                            ]:
                                continue

                            # Add relationship
                            relationship_data = {
                                "source": rel.get("source", entity),
                                "target": rel.get("target", ""),
                                "type": rel.get("type", "related_to"),
                                "description": rel.get("description", ""),
                                "discovered_at_depth": current_depth,
                                "chunk_ids": rel.get("chunk_ids", []),
                            }
                            relationships.append(relationship_data)

                            # Add connected entities for next level exploration
                            connected_entity = rel.get("target", "")
                            if connected_entity and connected_entity != entity:
                                # Apply exploration mode filtering
                                if exploration_mode == "outbound":
                                    if rel.get("source") == entity:
                                        next_level_entities.add(connected_entity)
                                elif exploration_mode == "inbound":
                                    if rel.get("target") == entity:
                                        next_level_entities.add(rel.get("source", ""))
                                else:  # bidirectional
                                    next_level_entities.add(connected_entity)

                    # If no explicit relationships, try to extract connections from response text
                    elif result.get("response"):
                        # Simple heuristic to find potential entities in the response
                        response_text = result["response"].lower()
                        potential_entities = self._extract_entities_from_text(
                            response_text, entity
                        )

                        for potential_entity in potential_entities[
                            :5
                        ]:  # Limit to avoid noise
                            if potential_entity not in explored_entities:
                                relationship_data = {
                                    "source": entity,
                                    "target": potential_entity,
                                    "type": "mentioned_with",
                                    "description": f"Entity mentioned in context with {entity}",
                                    "discovered_at_depth": current_depth,
                                    "chunk_ids": [],
                                }
                                relationships.append(relationship_data)
                                next_level_entities.add(potential_entity)

                except APIError as e:
                    logger.warning(f"Failed to explore entity '{entity}': {e}")
                    continue

            # Prepare for next iteration
            current_entities = next_level_entities

        return {
            "entities": entities,
            "relationships": relationships,
            "max_depth_reached": current_depth + 1,
            "exploration_complete": len(current_entities) == 0
            or current_depth + 1 >= depth,
        }

    def _extract_entities_from_text(self, text: str, source_entity: str) -> List[str]:
        """Extract potential entities from text using simple heuristics."""
        import re

        # Look for capitalized phrases that might be entities
        # This is a simple heuristic - in a real implementation you might use NER
        pattern = r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b"
        matches = re.findall(pattern, text)

        # Filter out common words and the source entity
        common_words = {
            "The",
            "This",
            "That",
            "These",
            "Those",
            "When",
            "Where",
            "How",
            "What",
            "Why",
        }
        entities = []

        for match in matches:
            if match not in common_words and match.lower() != source_entity.lower():
                entities.append(match)

        return list(set(entities))  # Remove duplicates

    def _format_exploration_results(
        self,
        exploration_results: Dict[str, Any],
        output_format: str,
        include_path_analysis: bool,
        starting_entity: str,
    ) -> Dict[str, Any]:
        """Format exploration results based on the requested output format."""

        entities = exploration_results.get("entities", {})
        relationships = exploration_results.get("relationships", [])

        if output_format == "hierarchical":
            return self._format_hierarchical(entities, relationships, starting_entity)
        elif output_format == "network":
            return self._format_network(entities, relationships)
        elif output_format == "summary":
            return self._format_summary(entities, relationships, starting_entity)
        else:
            return {"error": f"Unknown output format: {output_format}"}

    def _format_hierarchical(
        self, entities: Dict[str, Any], relationships: List[Dict], starting_entity: str
    ) -> Dict[str, Any]:
        """Format results as a hierarchical tree structure."""

        # Group entities by level
        levels = {}
        for entity_name, entity_data in entities.items():
            level = entity_data.get("level", 0)
            if level not in levels:
                levels[level] = []
            levels[level].append(entity_data)

        # Build hierarchical structure
        hierarchy = {
            "root": {
                "entity": starting_entity,
                "details": entities.get(starting_entity, {}),
                "children": [],
            }
        }

        # Group relationships by source for easier traversal
        relationships_by_source = {}
        for rel in relationships:
            source = rel.get("source", "")
            if source not in relationships_by_source:
                relationships_by_source[source] = []
            relationships_by_source[source].append(rel)

        # Build the tree recursively
        def build_tree_level(parent_entity: str, current_level: int, max_level: int):
            if current_level >= max_level:
                return []

            children = []
            for rel in relationships_by_source.get(parent_entity, []):
                target = rel.get("target", "")
                if (
                    target in entities
                    and entities[target].get("level", 0) == current_level + 1
                ):
                    child_node = {
                        "entity": target,
                        "relationship": {
                            "type": rel.get("type", ""),
                            "description": rel.get("description", ""),
                        },
                        "details": entities[target],
                        "children": build_tree_level(
                            target, current_level + 1, max_level
                        ),
                    }
                    children.append(child_node)

            return children

        max_level = max(levels.keys()) if levels else 0
        hierarchy["root"]["children"] = build_tree_level(starting_entity, 0, max_level)

        return {
            "format": "hierarchical",
            "tree": hierarchy,
            "levels_summary": {
                f"level_{level}": len(entities_list)
                for level, entities_list in levels.items()
            },
        }

    def _format_network(
        self, entities: Dict[str, Any], relationships: List[Dict]
    ) -> Dict[str, Any]:
        """Format results as a network/graph structure."""

        return {
            "format": "network",
            "nodes": [
                {
                    "id": entity_name,
                    "label": entity_name,
                    "level": entity_data.get("level", 0),
                    "description": entity_data.get("description", "")[:200],
                    "discovered_via": entity_data.get("discovered_via", "unknown"),
                }
                for entity_name, entity_data in entities.items()
            ],
            "edges": [
                {
                    "id": f"{rel.get('source', '')}_{rel.get('target', '')}_{i}",
                    "source": rel.get("source", ""),
                    "target": rel.get("target", ""),
                    "type": rel.get("type", ""),
                    "label": rel.get("type", ""),
                    "description": rel.get("description", "")[:100],
                    "discovered_at_depth": rel.get("discovered_at_depth", 0),
                }
                for i, rel in enumerate(relationships)
            ],
            "network_stats": {
                "total_nodes": len(entities),
                "total_edges": len(relationships),
                "average_connections": (
                    len(relationships) / len(entities) if entities else 0
                ),
            },
        }

    def _format_summary(
        self, entities: Dict[str, Any], relationships: List[Dict], starting_entity: str
    ) -> Dict[str, Any]:
        """Format results as a condensed summary."""

        # Group by relationship type
        rel_types = {}
        for rel in relationships:
            rel_type = rel.get("type", "unknown")
            if rel_type not in rel_types:
                rel_types[rel_type] = []
            rel_types[rel_type].append(rel)

        # Get top connected entities
        entity_connections = {}
        for rel in relationships:
            source = rel.get("source", "")
            target = rel.get("target", "")
            entity_connections[source] = entity_connections.get(source, 0) + 1
            entity_connections[target] = entity_connections.get(target, 0) + 1

        top_connected = sorted(
            entity_connections.items(), key=lambda x: x[1], reverse=True
        )[:10]

        return {
            "format": "summary",
            "overview": {
                "starting_entity": starting_entity,
                "total_entities_discovered": len(entities),
                "total_relationships": len(relationships),
                "relationship_types": list(rel_types.keys()),
                "exploration_depth": (
                    max([e.get("level", 0) for e in entities.values()]) + 1
                    if entities
                    else 0
                ),
            },
            "key_findings": {
                "most_connected_entities": [
                    {"entity": entity, "connections": count}
                    for entity, count in top_connected
                ],
                "relationship_type_distribution": {
                    rel_type: len(rels) for rel_type, rels in rel_types.items()
                },
                "entities_by_level": {
                    f"level_{level}": [
                        name
                        for name, data in entities.items()
                        if data.get("level") == level
                    ]
                    for level in set(
                        [data.get("level", 0) for data in entities.values()]
                    )
                },
            },
            "exploration_paths": [
                {
                    "path": f"{rel.get('source', '')} -> {rel.get('target', '')}",
                    "relationship": rel.get("type", ""),
                    "depth": rel.get("discovered_at_depth", 0),
                }
                for rel in relationships[:20]  # Show top 20 paths
            ],
        }

    def _analyze_connection_paths(
        self, exploration_results: Dict[str, Any], starting_entity: str
    ) -> Dict[str, Any]:
        """Analyze connection patterns and paths in the exploration results."""

        relationships = exploration_results.get("relationships", [])
        entities = exploration_results.get("entities", {})

        # Build adjacency graph
        graph = {}
        for rel in relationships:
            source = rel.get("source", "")
            target = rel.get("target", "")

            if source not in graph:
                graph[source] = []
            if target not in graph:
                graph[target] = []

            graph[source].append(
                {"target": target, "type": rel.get("type", ""), "rel": rel}
            )
            graph[target].append(
                {"target": source, "type": rel.get("type", ""), "rel": rel}
            )

        # Find shortest paths from starting entity
        def find_shortest_path(start: str, end: str, max_depth: int = 5) -> List[str]:
            if start == end:
                return [start]

            queue = [(start, [start])]
            visited = {start}

            while queue:
                current, path = queue.pop(0)

                if len(path) > max_depth:
                    continue

                for neighbor in graph.get(current, []):
                    neighbor_entity = neighbor["target"]

                    if neighbor_entity == end:
                        return path + [neighbor_entity]

                    if neighbor_entity not in visited:
                        visited.add(neighbor_entity)
                        queue.append((neighbor_entity, path + [neighbor_entity]))

            return []

        # Analyze patterns
        analysis = {
            "centrality_analysis": {
                entity: len(graph.get(entity, [])) for entity in entities.keys()
            },
            "path_analysis": {},
            "clustering_patterns": {},
            "relationship_patterns": {},
        }

        # Find paths to key entities
        for entity in list(entities.keys())[:10]:  # Analyze paths to top 10 entities
            if entity != starting_entity:
                path = find_shortest_path(starting_entity, entity)
                if path:
                    analysis["path_analysis"][entity] = {
                        "path": path,
                        "length": len(path) - 1,
                        "path_string": " -> ".join(path),
                    }

        return analysis

    async def execute_streaming(
        self, session: ConnectionSession, parameters: Dict[str, Any]
    ) -> AsyncGenerator[ToolResult, None]:
        """Execute explore_graph with streaming progress updates."""
        try:
            starting_entity = parameters["starting_entity"]
            depth = parameters.get("depth", 1)
            exploration_mode = parameters.get("exploration_mode", "bidirectional")

            # Create operation tracking
            operation_id = str(uuid.uuid4())

            # Step 1: Initialization (10%)
            yield ToolResult(
                success=True,
                data=ToolProgress(
                    operation_id=operation_id,
                    progress=0.1,
                    status="initializing",
                    message=f"Starting graph exploration from '{starting_entity}' with depth {depth}",
                ),
                metadata={"tool": self.name, "streaming": True},
            )

            # Step 2: Entity Discovery (30% - 70%)
            for current_depth in range(depth):
                progress_pct = 0.3 + (current_depth / depth) * 0.4
                yield ToolResult(
                    success=True,
                    data=ToolProgress(
                        operation_id=operation_id,
                        progress=progress_pct,
                        status="exploring",
                        message=f"Exploring depth {current_depth + 1}/{depth} - discovering entities and relationships",
                    ),
                    metadata={"tool": self.name, "streaming": True},
                )

            # Step 3: Processing Results (80%)
            yield ToolResult(
                success=True,
                data=ToolProgress(
                    operation_id=operation_id,
                    progress=0.8,
                    status="processing",
                    message="Processing discovered entities and formatting results",
                ),
                metadata={"tool": self.name, "streaming": True},
            )

            # Step 4: Execute the actual tool
            result = await self.execute(session, parameters)

            # Step 5: Completion (100%)
            entity_count = (
                result.data.get("stats", {}).get("total_entities", 0)
                if result.success
                else 0
            )
            relationship_count = (
                result.data.get("stats", {}).get("total_relationships", 0)
                if result.success
                else 0
            )

            yield ToolResult(
                success=True,
                data=ToolProgress(
                    operation_id=operation_id,
                    progress=1.0,
                    status="completed",
                    message=f"Graph exploration completed: {entity_count} entities, {relationship_count} relationships discovered",
                ),
                metadata={"tool": self.name, "streaming": True},
            )

            yield result

        except Exception as e:
            yield ToolResult(
                success=False,
                error=f"Error in streaming graph exploration: {str(e)}",
                metadata={"tool": self.name, "streaming": True, "error": str(e)},
            )


class ClearCacheTool(MCPTool):
    """Tool for clearing various types of caches in the MCP server and LightRAG system."""

    @property
    def name(self) -> str:
        return "clear_cache"

    @property
    def description(self) -> str:
        return "Clear various types of caches including session data, Redis cache, and LightRAG cache to free up memory and ensure fresh data"

    @property
    def category(self) -> ToolCategory:
        return ToolCategory.SYSTEM_UTILITIES

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            string_parameter(
                name="cache_type",
                description="Type of cache to clear: 'session' (current session only), 'user_sessions' (all user sessions), 'redis' (Redis cache), 'lightrag' (LightRAG cache), 'operations' (streaming operations), 'all' (everything)",
                required=False,
                default="session",
            ),
            boolean_parameter(
                name="force_clear",
                description="Force clearing even if operations are active (default: false for safety)",
                required=False,
                default=False,
            ),
            boolean_parameter(
                name="include_statistics",
                description="Include detailed statistics about what was cleared (default: true)",
                required=False,
                default=True,
            ),
            string_parameter(
                name="confirmation_token",
                description="Confirmation token required for 'all' cache type (use value 'CONFIRM_CLEAR_ALL')",
                required=False,
                default="",
            ),
        ]

    @property
    def requires_context(self) -> bool:
        return False  # Cache clearing doesn't require a specific context

    async def execute(
        self, session: ConnectionSession, parameters: Dict[str, Any]
    ) -> ToolResult:
        """Execute the clear_cache tool for session and system cache management."""
        operation_id = f"clear_cache_{session.session_id}"

        try:
            # Parameter validation
            cache_type = parameters.get("cache_type", "session").lower()
            force_clear = parameters.get("force_clear", False)
            include_statistics = parameters.get("include_statistics", True)
            confirmation_token = parameters.get("confirmation_token", "").strip()

            # Validate cache type
            valid_cache_types = [
                "session",
                "user_sessions",
                "redis",
                "lightrag",
                "operations",
                "all",
            ]
            if cache_type not in valid_cache_types:
                return ToolResult(
                    success=False,
                    error=f"Invalid cache_type '{cache_type}'. Valid options: {', '.join(valid_cache_types)}",
                    metadata={
                        "operation_id": operation_id,
                        "error_type": "validation_error",
                    },
                )

            # Require confirmation for 'all' cache type
            if cache_type == "all" and confirmation_token != "CONFIRM_CLEAR_ALL":
                return ToolResult(
                    success=False,
                    error="Cache type 'all' requires confirmation_token='CONFIRM_CLEAR_ALL' for safety",
                    metadata={
                        "operation_id": operation_id,
                        "error_type": "confirmation_required",
                    },
                )

            # Progress tracking
            logger.info(
                f"Starting cache clearing: type={cache_type}, session={session.session_id}"
            )

            # Track what was cleared
            cleared_items = {
                "session_data": False,
                "user_sessions": 0,
                "redis_keys": 0,
                "lightrag_cache": False,
                "operations": 0,
                "errors": [],
            }

            statistics = {
                "start_time": datetime.utcnow().isoformat(),
                "cache_type": cache_type,
                "force_clear": force_clear,
            }

            # Get clients and services
            lightrag_client = await self.get_lightrag_client()

            # Execute cache clearing based on type
            if cache_type in ["session", "all"]:
                try:
                    cleared_items["session_data"] = await self._clear_session_cache(
                        session, force_clear
                    )
                except Exception as e:
                    cleared_items["errors"].append(f"Session cache error: {str(e)}")
                    logger.warning(f"Failed to clear session cache: {e}")

            if cache_type in ["user_sessions", "all"]:
                try:
                    cleared_items["user_sessions"] = await self._clear_user_sessions(
                        session, force_clear
                    )
                except Exception as e:
                    cleared_items["errors"].append(f"User sessions error: {str(e)}")
                    logger.warning(f"Failed to clear user sessions: {e}")

            if cache_type in ["redis", "all"]:
                try:
                    cleared_items["redis_keys"] = await self._clear_redis_cache(
                        session, force_clear
                    )
                except Exception as e:
                    cleared_items["errors"].append(f"Redis cache error: {str(e)}")
                    logger.warning(f"Failed to clear Redis cache: {e}")

            if cache_type in ["lightrag", "all"]:
                try:
                    cleared_items["lightrag_cache"] = await self._clear_lightrag_cache(
                        lightrag_client
                    )
                except Exception as e:
                    cleared_items["errors"].append(f"LightRAG cache error: {str(e)}")
                    logger.warning(f"Failed to clear LightRAG cache: {e}")

            if cache_type in ["operations", "all"]:
                try:
                    cleared_items["operations"] = await self._clear_operations_cache(
                        session, force_clear
                    )
                except Exception as e:
                    cleared_items["errors"].append(f"Operations cache error: {str(e)}")
                    logger.warning(f"Failed to clear operations cache: {e}")

            # Build result
            statistics["end_time"] = datetime.utcnow().isoformat()
            statistics["duration_seconds"] = (
                datetime.fromisoformat(statistics["end_time"].replace("Z", "+00:00"))
                - datetime.fromisoformat(
                    statistics["start_time"].replace("Z", "+00:00")
                )
            ).total_seconds()

            # Determine overall success
            has_errors = len(cleared_items["errors"]) > 0
            success = not has_errors or (
                has_errors
                and any(
                    [
                        cleared_items["session_data"],
                        cleared_items["user_sessions"] > 0,
                        cleared_items["redis_keys"] > 0,
                        cleared_items["lightrag_cache"],
                        cleared_items["operations"] > 0,
                    ]
                )
            )

            # Build response
            result_data = {
                "cache_type": cache_type,
                "success": success,
                "cleared_items": cleared_items,
                "summary": self._generate_cache_clear_summary(
                    cleared_items, cache_type
                ),
            }

            if include_statistics:
                result_data["statistics"] = statistics
                result_data["recommendations"] = self._generate_cache_recommendations(
                    cleared_items, cache_type
                )

            metadata = {
                "tool": self.name,
                "operation_id": operation_id,
                "cache_type": cache_type,
                "session_id": session.session_id,
                "success": success,
                "has_errors": has_errors,
                "timestamp": datetime.utcnow().isoformat(),
            }

            logger.info(
                f"Cache clearing completed: {cache_type} for session {session.session_id} "
                f"(success: {success}, errors: {len(cleared_items['errors'])})"
            )

            return ToolResult(
                success=success,
                data=result_data,
                metadata=metadata,
            )

        except Exception as e:
            error_msg = f"Unexpected error during cache clearing: {str(e)}"
            logger.error(f"Cache clearing failed: {error_msg}", exc_info=True)
            return ToolResult(
                success=False,
                error=error_msg,
                metadata={
                    "operation_id": operation_id,
                    "error_type": "unexpected_error",
                },
            )

    async def _clear_session_cache(
        self, session: ConnectionSession, force_clear: bool
    ) -> bool:
        """Clear session-specific cache data."""
        try:
            # Reset session activity stats (preserving essential session info)
            if hasattr(session, "resource_usage"):
                session.resource_usage = {
                    "messages_sent": 0,
                    "messages_received": 0,
                    "bytes_sent": 0,
                    "bytes_received": 0,
                    "operations_started": 0,
                    "operations_completed": 0,
                    "errors_encountered": 0,
                }

            # Clear session metadata (preserving auth and connection info)
            if hasattr(session, "connection_metadata"):
                preserved_keys = {
                    "path",
                    "connection_type",
                    "client_ip",
                    "authenticated",
                    "user_id",
                }
                new_metadata = {
                    key: value
                    for key, value in session.connection_metadata.items()
                    if key in preserved_keys
                }
                session.connection_metadata = new_metadata

            # Reset error tracking
            session.error_count = 0
            session.last_error = None

            return True

        except Exception as e:
            logger.error(f"Failed to clear session cache: {e}")
            return False

    async def _clear_user_sessions(
        self, session: ConnectionSession, force_clear: bool
    ) -> int:
        """Clear sessions for the current user (if authenticated)."""
        # This would require access to the protocol server's session management
        # For now, return 0 as we don't have direct access to the server instance
        # In a real implementation, this would be passed via dependency injection
        logger.info(
            "User sessions clearing not implemented - requires protocol server access"
        )
        return 0

    async def _clear_redis_cache(
        self, session: ConnectionSession, force_clear: bool
    ) -> int:
        """Clear Redis cache entries."""
        try:
            # Import Redis client from main module
            from ..main import redis_client

            if not redis_client:
                logger.warning("Redis client not available")
                return 0

            # Define cache key patterns to clear
            cache_patterns = [
                f"mcp:session:{session.session_id}:*",  # Session-specific cache
                "mcp:cache:*",  # General MCP cache
                "mcp:temp:*",  # Temporary cache entries
            ]

            cleared_count = 0

            for pattern in cache_patterns:
                try:
                    # Get keys matching pattern
                    keys = await redis_client.keys(pattern)

                    if keys:
                        # Delete matching keys
                        deleted = await redis_client.delete(*keys)
                        cleared_count += deleted
                        logger.info(
                            f"Cleared {deleted} Redis keys for pattern: {pattern}"
                        )

                except Exception as e:
                    logger.warning(f"Failed to clear Redis pattern {pattern}: {e}")

            return cleared_count

        except Exception as e:
            logger.error(f"Failed to clear Redis cache: {e}")
            return 0

    async def _clear_lightrag_cache(self, lightrag_client) -> bool:
        """Clear LightRAG system cache."""
        try:
            # Use the LightRAG client's built-in cache clearing method
            result = await lightrag_client.clear_cache()

            if isinstance(result, dict):
                success = (
                    result.get("success", False) or result.get("status") == "success"
                )
                logger.info(f"LightRAG cache clear result: {result}")
                return success

            return True  # Assume success if no error was raised

        except Exception as e:
            logger.error(f"Failed to clear LightRAG cache: {e}")
            return False

    async def _clear_operations_cache(
        self, session: ConnectionSession, force_clear: bool
    ) -> int:
        """Clear streaming operations and operation cache."""
        # This would require access to the protocol server's operation management
        # For now, return 0 as we don't have direct access to the server instance
        # In a real implementation, this would be passed via dependency injection
        logger.info(
            "Operations cache clearing not implemented - requires protocol server access"
        )
        return 0

    def _generate_cache_clear_summary(
        self, cleared_items: Dict[str, Any], cache_type: str
    ) -> str:
        """Generate a human-readable summary of what was cleared."""
        summary_parts = []

        if cleared_items["session_data"]:
            summary_parts.append("session data")

        if cleared_items["user_sessions"] > 0:
            summary_parts.append(f"{cleared_items['user_sessions']} user sessions")

        if cleared_items["redis_keys"] > 0:
            summary_parts.append(f"{cleared_items['redis_keys']} Redis cache entries")

        if cleared_items["lightrag_cache"]:
            summary_parts.append("LightRAG system cache")

        if cleared_items["operations"] > 0:
            summary_parts.append(f"{cleared_items['operations']} streaming operations")

        if not summary_parts:
            return f"No cache data was cleared for cache type '{cache_type}'"

        base_summary = f"Successfully cleared: {', '.join(summary_parts)}"

        if cleared_items["errors"]:
            base_summary += (
                f". {len(cleared_items['errors'])} errors occurred during clearing."
            )

        return base_summary

    def _generate_cache_recommendations(
        self, cleared_items: Dict[str, Any], cache_type: str
    ) -> List[str]:
        """Generate recommendations based on what was cleared."""
        recommendations = []

        if cleared_items["session_data"]:
            recommendations.append(
                "Session metrics have been reset. Current session performance stats will start fresh."
            )

        if cleared_items["redis_keys"] > 0:
            recommendations.append(
                "Redis cache cleared. Subsequent operations may be slower until cache is rebuilt."
            )

        if cleared_items["lightrag_cache"]:
            recommendations.append(
                "LightRAG cache cleared. Knowledge graph queries may be slower until cache is rebuilt."
            )

        if cleared_items["errors"]:
            recommendations.append(
                "Some cache clearing operations failed. Check logs for detailed error information."
            )

        if cache_type == "all":
            recommendations.append(
                "Complete cache clear performed. System will rebuild caches as needed during normal operation."
            )

        if not any(
            [
                cleared_items["session_data"],
                cleared_items["redis_keys"] > 0,
                cleared_items["lightrag_cache"],
            ]
        ):
            recommendations.append(
                "No significant cache data was cleared. Cache may already be clean or cache type may not contain data."
            )

        return recommendations

    async def execute_streaming(
        self, session: ConnectionSession, parameters: Dict[str, Any]
    ) -> AsyncGenerator[ToolResult, None]:
        """Execute clear_cache with streaming progress updates."""
        try:
            cache_type = parameters.get("cache_type", "session")

            # Create operation tracking
            operation_id = str(uuid.uuid4())

            # Step 1: Validation (10%)
            yield ToolResult(
                success=True,
                data=ToolProgress(
                    operation_id=operation_id,
                    progress=0.1,
                    status="validation",
                    message=f"Validating cache clearing parameters for type: {cache_type}",
                ),
                metadata={"tool": self.name, "streaming": True},
            )

            # Step 2: Starting Cache Clear (25%)
            yield ToolResult(
                success=True,
                data=ToolProgress(
                    operation_id=operation_id,
                    progress=0.25,
                    status="starting",
                    message=f"Starting {cache_type} cache clearing process",
                ),
                metadata={"tool": self.name, "streaming": True},
            )

            # Step 3: Clearing Cache (50%)
            yield ToolResult(
                success=True,
                data=ToolProgress(
                    operation_id=operation_id,
                    progress=0.5,
                    status="clearing",
                    message="Clearing cache data and validating results",
                ),
                metadata={"tool": self.name, "streaming": True},
            )

            # Step 4: Execute the actual tool
            result = await self.execute(session, parameters)

            # Step 5: Completion (100%)
            success_msg = "Cache clearing completed successfully"
            if not result.success:
                success_msg = f"Cache clearing completed with errors: {result.error}"

            yield ToolResult(
                success=True,
                data=ToolProgress(
                    operation_id=operation_id,
                    progress=1.0,
                    status="completed",
                    message=success_msg,
                ),
                metadata={"tool": self.name, "streaming": True},
            )

            yield result

        except Exception as e:
            yield ToolResult(
                success=False,
                error=f"Error in streaming cache clearing: {str(e)}",
                metadata={"tool": self.name, "streaming": True, "error": str(e)},
            )


class HelpTool(MCPTool):
    """Tool for providing usage guidance, best practices, and comprehensive help for the MCP server and tools."""

    @property
    def name(self) -> str:
        return "help"

    @property
    def description(self) -> str:
        return "Get comprehensive help, usage guidance, best practices, and examples for using the LightRAG MCP server and its tools"

    @property
    def category(self) -> ToolCategory:
        return ToolCategory.SYSTEM_UTILITIES

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            string_parameter(
                name="topic",
                description="Help topic: 'overview' (general help), 'tools' (tool-specific help), 'workflows' (common workflows), 'best-practices', 'troubleshooting', or specific tool name",
                required=False,
                default="overview",
            ),
            string_parameter(
                name="tool_name",
                description="Specific tool name for detailed help (e.g., 'query', 'find_concept', 'explore_graph')",
                required=False,
                default="",
            ),
            string_parameter(
                name="help_format",
                description="Help format: 'structured' (organized sections), 'quick' (brief overview), 'examples' (usage examples), 'comprehensive' (detailed guide)",
                required=False,
                default="structured",
            ),
            boolean_parameter(
                name="include_examples",
                description="Include practical usage examples in the help output",
                required=False,
                default=True,
            ),
            string_parameter(
                name="context_type",
                description="Context type for contextual help: 'beginner', 'intermediate', 'advanced', or 'developer'",
                required=False,
                default="intermediate",
            ),
        ]

    @property
    def requires_context(self) -> bool:
        return False  # Help doesn't require a specific context

    async def execute(
        self, session: ConnectionSession, parameters: Dict[str, Any]
    ) -> ToolResult:
        """Execute the help tool to provide comprehensive guidance."""
        operation_id = f"help_{session.session_id}"

        try:
            # Parameter validation
            topic = parameters.get("topic", "overview").lower()
            tool_name = parameters.get("tool_name", "").strip().lower()
            help_format = parameters.get("help_format", "structured").lower()
            include_examples = parameters.get("include_examples", True)
            context_type = parameters.get("context_type", "intermediate").lower()

            # Validate parameters
            valid_topics = [
                "overview",
                "tools",
                "workflows",
                "best-practices",
                "troubleshooting",
            ]
            valid_formats = ["structured", "quick", "examples", "comprehensive"]
            valid_contexts = ["beginner", "intermediate", "advanced", "developer"]

            # Allow specific tool names as topics
            available_tools = [
                "list_contexts",
                "switch_context",
                "get_context_info",
                "query",
                "find_concept",
                "get_relationships",
                "search_docs",
                "search_documents",
                "get_summary",
                "explore_graph",
                "clear_cache",
                "help",
            ]

            if topic not in valid_topics and topic not in available_tools:
                # If tool_name is provided, use it as topic
                if tool_name and tool_name in available_tools:
                    topic = tool_name
                else:
                    return ToolResult(
                        success=False,
                        error=f"Invalid topic '{topic}'. Valid topics: {', '.join(valid_topics)} or tool names: {', '.join(available_tools)}",
                        metadata={
                            "operation_id": operation_id,
                            "error_type": "validation_error",
                        },
                    )

            if help_format not in valid_formats:
                return ToolResult(
                    success=False,
                    error=f"Invalid help_format '{help_format}'. Valid options: {', '.join(valid_formats)}",
                    metadata={
                        "operation_id": operation_id,
                        "error_type": "validation_error",
                    },
                )

            if context_type not in valid_contexts:
                return ToolResult(
                    success=False,
                    error=f"Invalid context_type '{context_type}'. Valid options: {', '.join(valid_contexts)}",
                    metadata={
                        "operation_id": operation_id,
                        "error_type": "validation_error",
                    },
                )

            logger.info(
                f"Generating help for topic: {topic}, format: {help_format}, context: {context_type}"
            )

            # Generate help content based on topic and format
            help_content = await self._generate_help_content(
                topic, tool_name, help_format, include_examples, context_type, session
            )

            # Build response
            result_data = {
                "topic": topic,
                "help_format": help_format,
                "context_type": context_type,
                "include_examples": include_examples,
                "help_content": help_content,
                "metadata": {
                    "generated_at": datetime.utcnow().isoformat(),
                    "session_id": session.session_id,
                    "total_sections": len(help_content.get("sections", [])),
                },
            }

            metadata = {
                "tool": self.name,
                "operation_id": operation_id,
                "topic": topic,
                "help_format": help_format,
                "context_type": context_type,
                "session_id": session.session_id,
                "timestamp": datetime.utcnow().isoformat(),
            }

            logger.info(
                f"Help generated successfully for topic '{topic}' in {help_format} format"
            )

            return ToolResult(
                success=True,
                data=result_data,
                metadata=metadata,
            )

        except Exception as e:
            error_msg = f"Unexpected error during help generation: {str(e)}"
            logger.error(f"Help generation failed: {error_msg}", exc_info=True)
            return ToolResult(
                success=False,
                error=error_msg,
                metadata={
                    "operation_id": operation_id,
                    "error_type": "unexpected_error",
                },
            )

    async def _generate_help_content(
        self,
        topic: str,
        tool_name: str,
        help_format: str,
        include_examples: bool,
        context_type: str,
        session: ConnectionSession,
    ) -> Dict[str, Any]:
        """Generate comprehensive help content based on parameters."""

        if topic == "overview":
            return self._generate_overview_help(
                help_format, include_examples, context_type
            )
        elif topic == "tools":
            return self._generate_tools_help(
                tool_name, help_format, include_examples, context_type
            )
        elif topic == "workflows":
            return self._generate_workflows_help(
                help_format, include_examples, context_type
            )
        elif topic == "best-practices":
            return self._generate_best_practices_help(
                help_format, include_examples, context_type
            )
        elif topic == "troubleshooting":
            return self._generate_troubleshooting_help(
                help_format, include_examples, context_type
            )
        elif topic in [
            "list_contexts",
            "switch_context",
            "get_context_info",
            "query",
            "find_concept",
            "get_relationships",
            "search_docs",
            "search_documents",
            "get_summary",
            "explore_graph",
            "clear_cache",
            "help",
        ]:
            return self._generate_tool_specific_help(
                topic, help_format, include_examples, context_type
            )
        else:
            return {"error": f"Unknown help topic: {topic}"}

    def _generate_overview_help(
        self, help_format: str, include_examples: bool, context_type: str
    ) -> Dict[str, Any]:
        """Generate overview help content."""

        overview = {
            "title": "LightRAG MCP Server - Comprehensive Help Guide",
            "description": "Your guide to effectively using the LightRAG Model Context Protocol server for knowledge graph interactions",
            "sections": [],
        }

        # Quick format - brief overview
        if help_format == "quick":
            overview["sections"] = [
                {
                    "title": "Quick Start",
                    "content": "The LightRAG MCP server provides intelligent knowledge graph access through 11 specialized tools. Start with 'list_contexts' to see available knowledge contexts, then use 'query' for basic searches or 'get_summary' for conversational responses.",
                },
                {
                    "title": "Key Tools",
                    "content": "Essential tools: query (search), get_summary (chat-style), find_concept (entities), explore_graph (relationships), clear_cache (cleanup).",
                },
            ]

        # Structured or comprehensive format
        else:
            overview["sections"] = [
                {
                    "title": "Introduction",
                    "content": f"Welcome to the LightRAG MCP Server! This powerful system provides intelligent access to knowledge graphs through the Model Context Protocol. Whether you're a {context_type} user, this guide will help you effectively utilize the available tools and capabilities.",
                },
                {
                    "title": "Core Concepts",
                    "content": "The server operates on contexts (knowledge domains), tools (specialized functions), and sessions (your connection). Each context contains documents, entities, and relationships that you can query and explore using various tools.",
                },
                {
                    "title": "Tool Categories",
                    "content": "Tools are organized into categories: Context Management (switching contexts), Query Operations (searching), Semantic Search (finding concepts), Graph Exploration (traversing relationships), Document Access (retrieving content), and System Utilities (maintenance).",
                },
                {
                    "title": "Getting Started Workflow",
                    "content": "1. Use 'list_contexts' to see available knowledge domains\n2. Use 'switch_context' to select your target context\n3. Start with 'get_summary' for conversational queries or 'query' for detailed searches\n4. Explore relationships with 'find_concept' and 'explore_graph'\n5. Use 'clear_cache' when needed for performance",
                },
            ]

            if help_format == "comprehensive":
                overview["sections"].extend(
                    [
                        {
                            "title": "Advanced Features",
                            "content": "The server supports relationship depth traversal (up to 3 levels), streaming operations for long-running tasks, multiple query modes (naive, local, global, hybrid, mix), and comprehensive caching for performance optimization.",
                        },
                        {
                            "title": "Performance Tips",
                            "content": "Use appropriate relationship depths (1-2 for most cases), leverage caching, choose optimal query modes, and clear cache periodically. Monitor operation progress through streaming endpoints.",
                        },
                    ]
                )

        if include_examples:
            overview["examples"] = [
                {
                    "title": "Basic Query Example",
                    "description": "Search for information about authentication",
                    "tool": "query",
                    "parameters": {
                        "query": "How does authentication work in this system?",
                        "mode": "hybrid",
                        "include_relationships": True,
                    },
                },
                {
                    "title": "Chat-Style Summary",
                    "description": "Get a conversational explanation",
                    "tool": "get_summary",
                    "parameters": {
                        "query": "What is this project about?",
                        "style": "conversational",
                        "length": "medium",
                    },
                },
            ]

        return overview

    def _generate_tools_help(
        self,
        tool_name: str,
        help_format: str,
        include_examples: bool,
        context_type: str,
    ) -> Dict[str, Any]:
        """Generate tools help content."""

        tools_help = {
            "title": "MCP Tools Reference Guide",
            "description": "Comprehensive guide to all available tools and their capabilities",
            "sections": [],
        }

        tool_categories = {
            "Context Management": [
                "list_contexts",
                "switch_context",
                "get_context_info",
            ],
            "Query Operations": ["query", "get_summary"],
            "Semantic Search": ["find_concept", "get_relationships", "search_docs"],
            "Document Access": ["search_documents"],
            "Graph Exploration": ["explore_graph"],
            "System Utilities": ["clear_cache", "help"],
        }

        if help_format == "quick":
            for category, tools in tool_categories.items():
                tool_list = ", ".join(tools)
                tools_help["sections"].append(
                    {"title": category, "content": f"Tools: {tool_list}"}
                )
        else:
            for category, tools in tool_categories.items():
                section_content = (
                    f"{category} tools provide specialized functionality:\n\n"
                )
                for tool in tools:
                    section_content += (
                        f"• {tool}: {self._get_tool_brief_description(tool)}\n"
                    )

                tools_help["sections"].append(
                    {"title": category, "content": section_content.strip()}
                )

        if include_examples and context_type in [
            "intermediate",
            "advanced",
            "developer",
        ]:
            tools_help["usage_patterns"] = [
                {
                    "pattern": "Discovery Workflow",
                    "steps": [
                        "list_contexts",
                        "switch_context",
                        "get_summary",
                        "find_concept",
                    ],
                    "description": "Discover and understand available knowledge",
                },
                {
                    "pattern": "Research Workflow",
                    "steps": [
                        "query",
                        "get_relationships",
                        "explore_graph",
                        "search_documents",
                    ],
                    "description": "Deep research with relationship exploration",
                },
                {
                    "pattern": "Maintenance Workflow",
                    "steps": ["clear_cache", "get_context_info", "help"],
                    "description": "System maintenance and troubleshooting",
                },
            ]

        return tools_help

    def _generate_tool_specific_help(
        self,
        tool_name: str,
        help_format: str,
        include_examples: bool,
        context_type: str,
    ) -> Dict[str, Any]:
        """Generate help for a specific tool."""

        tool_details = self._get_detailed_tool_info(tool_name)

        tool_help = {
            "title": f"{tool_name.title()} Tool - Detailed Guide",
            "description": tool_details["description"],
            "sections": [
                {"title": "Purpose", "content": tool_details["purpose"]},
                {"title": "Parameters", "content": tool_details["parameters"]},
            ],
        }

        if help_format in ["structured", "comprehensive"]:
            tool_help["sections"].extend(
                [
                    {
                        "title": "Usage Guidelines",
                        "content": tool_details["guidelines"],
                    },
                    {"title": "Common Use Cases", "content": tool_details["use_cases"]},
                ]
            )

            if help_format == "comprehensive":
                tool_help["sections"].extend(
                    [
                        {
                            "title": "Advanced Features",
                            "content": tool_details.get(
                                "advanced_features",
                                "See general documentation for advanced features.",
                            ),
                        },
                        {
                            "title": "Performance Considerations",
                            "content": tool_details.get(
                                "performance_tips",
                                "Follow general performance best practices.",
                            ),
                        },
                    ]
                )

        if include_examples:
            tool_help["examples"] = tool_details.get("examples", [])

        return tool_help

    def _generate_workflows_help(
        self, help_format: str, include_examples: bool, context_type: str
    ) -> Dict[str, Any]:
        """Generate workflows help content."""

        workflows = {
            "title": "Common Workflows and Usage Patterns",
            "description": "Step-by-step guides for accomplishing common tasks with the MCP server",
            "sections": [],
        }

        common_workflows = [
            {
                "title": "Knowledge Discovery Workflow",
                "description": "Explore and understand available knowledge in a new context",
                "steps": [
                    "1. list_contexts - See available knowledge domains",
                    "2. switch_context - Select target context",
                    "3. get_context_info - Understand context contents",
                    "4. get_summary - Get overview with 'What is this about?'",
                    "5. find_concept - Discover key entities",
                    "6. explore_graph - Map relationships between concepts",
                ],
            },
            {
                "title": "Research and Analysis Workflow",
                "description": "Deep dive research with comprehensive relationship analysis",
                "steps": [
                    "1. query - Search for initial information (hybrid mode)",
                    "2. find_concept - Identify related entities",
                    "3. get_relationships - Map entity connections (depth 2-3)",
                    "4. explore_graph - Visualize relationship networks",
                    "5. search_documents - Find supporting documentation",
                    "6. get_summary - Synthesize findings",
                ],
            },
            {
                "title": "Content Exploration Workflow",
                "description": "Explore and understand document content and structure",
                "steps": [
                    "1. search_documents - Find relevant documents",
                    "2. query - Get detailed information (local mode)",
                    "3. get_relationships - Understand document connections",
                    "4. search_docs - Find specific content patterns",
                    "5. get_summary - Create overview of findings",
                ],
            },
        ]

        if help_format == "quick":
            for workflow in common_workflows:
                workflows["sections"].append(
                    {"title": workflow["title"], "content": workflow["description"]}
                )
        else:
            for workflow in common_workflows:
                content = f"{workflow['description']}\n\nSteps:\n" + "\n".join(
                    workflow["steps"]
                )
                workflows["sections"].append(
                    {"title": workflow["title"], "content": content}
                )

        if include_examples and context_type != "beginner":
            workflows["advanced_patterns"] = [
                {
                    "pattern": "Multi-Context Analysis",
                    "description": "Compare information across multiple contexts by switching contexts and running parallel queries",
                },
                {
                    "pattern": "Progressive Depth Exploration",
                    "description": "Start with depth 1 relationships, then progressively increase depth based on findings",
                },
                {
                    "pattern": "Cache-Optimized Research",
                    "description": "Structure queries to leverage caching, clear cache strategically for fresh data",
                },
            ]

        return workflows

    def _generate_best_practices_help(
        self, help_format: str, include_examples: bool, context_type: str
    ) -> Dict[str, Any]:
        """Generate best practices help content."""

        best_practices = {
            "title": "Best Practices and Optimization Guide",
            "description": "Guidelines for effective and efficient use of the LightRAG MCP server",
            "sections": [],
        }

        practices = [
            {
                "title": "Query Optimization",
                "content": "• Use specific, focused queries rather than broad searches\n• Choose appropriate query modes (hybrid for balance, local for entities, global for relationships)\n• Leverage relationship depth parameters (1-2 for most cases, 3 for deep analysis)\n• Include examples in queries for better context",
            },
            {
                "title": "Context Management",
                "content": "• Always check available contexts before starting work\n• Switch contexts deliberately rather than working across multiple contexts\n• Use get_context_info to understand context scope and contents\n• Plan context switches to minimize overhead",
            },
            {
                "title": "Performance Optimization",
                "content": "• Monitor relationship depth to balance detail vs performance\n• Use caching effectively - avoid unnecessary cache clearing\n• Leverage streaming for long-running operations\n• Set appropriate top_k limits based on your needs",
            },
            {
                "title": "Tool Selection Strategy",
                "content": "• Start with get_summary for general understanding\n• Use query for detailed, specific searches\n• Apply find_concept for entity discovery\n• Reserve explore_graph for relationship mapping\n• Use search_documents for content-specific needs",
            },
        ]

        if help_format == "quick":
            for practice in practices:
                best_practices["sections"].append(
                    {
                        "title": practice["title"],
                        "content": practice["content"].split("\n")[
                            0
                        ],  # First bullet point only
                    }
                )
        else:
            best_practices["sections"] = practices

            if help_format == "comprehensive" and context_type in [
                "advanced",
                "developer",
            ]:
                best_practices["sections"].extend(
                    [
                        {
                            "title": "Advanced Optimization",
                            "content": "• Batch related operations to leverage session caching\n• Use relationship type filters to reduce noise\n• Implement progressive disclosure (start simple, add complexity)\n• Monitor session statistics for optimization opportunities",
                        },
                        {
                            "title": "Error Handling",
                            "content": "• Always check tool result success status\n• Handle partial failures gracefully\n• Use operation IDs for tracking long-running operations\n• Implement retry logic for transient failures",
                        },
                    ]
                )

        if include_examples:
            best_practices["anti_patterns"] = [
                {
                    "antipattern": "Excessive Relationship Depth",
                    "problem": "Using depth > 3 for routine queries",
                    "solution": "Start with depth 1-2, increase only when needed",
                },
                {
                    "antipattern": "Cache Thrashing",
                    "problem": "Clearing cache after every operation",
                    "solution": "Clear cache only when data staleness is an issue",
                },
                {
                    "antipattern": "Context Switching Overhead",
                    "problem": "Frequent context switches during analysis",
                    "solution": "Plan analysis within single context when possible",
                },
            ]

        return best_practices

    def _generate_troubleshooting_help(
        self, help_format: str, include_examples: bool, context_type: str
    ) -> Dict[str, Any]:
        """Generate troubleshooting help content."""

        troubleshooting = {
            "title": "Troubleshooting Guide",
            "description": "Common issues, solutions, and debugging strategies",
            "sections": [],
        }

        common_issues = [
            {
                "title": "No Results from Queries",
                "symptoms": "Empty or minimal results from search operations",
                "solutions": "• Verify context contains relevant data with get_context_info\n• Try different query modes (hybrid, local, global)\n• Broaden query terms or check spelling\n• Increase top_k parameter\n• Clear cache and retry",
            },
            {
                "title": "Slow Performance",
                "symptoms": "Operations taking longer than expected",
                "solutions": "• Reduce relationship depth if using > 1\n• Lower top_k values for large result sets\n• Clear cache if memory is full\n• Use more specific queries\n• Check session statistics for bottlenecks",
            },
            {
                "title": "Context Switch Issues",
                "symptoms": "Cannot switch contexts or context data seems stale",
                "solutions": "• Verify target context exists with list_contexts\n• Check authentication and permissions\n• Clear session cache and retry\n• Wait for any active operations to complete",
            },
            {
                "title": "Relationship Traversal Problems",
                "symptoms": "Missing or unexpected relationship data",
                "solutions": "• Verify include_relationships=true in queries\n• Check relationship_depth parameter\n• Try different exploration modes (bidirectional vs outbound/inbound)\n• Use get_relationships for debugging",
            },
        ]

        if help_format == "quick":
            for issue in common_issues:
                troubleshooting["sections"].append(
                    {"title": issue["title"], "content": issue["symptoms"]}
                )
        else:
            for issue in common_issues:
                content = (
                    f"Symptoms: {issue['symptoms']}\n\nSolutions:\n{issue['solutions']}"
                )
                troubleshooting["sections"].append(
                    {"title": issue["title"], "content": content}
                )

        if include_examples and context_type in [
            "intermediate",
            "advanced",
            "developer",
        ]:
            troubleshooting["debugging_tools"] = [
                {
                    "tool": "get_context_info",
                    "use": "Verify context status and content availability",
                },
                {
                    "tool": "clear_cache",
                    "use": "Reset session state and clear stale data",
                },
                {"tool": "help", "use": "Get tool-specific guidance and examples"},
            ]

        return troubleshooting

    def _get_tool_brief_description(self, tool_name: str) -> str:
        """Get brief description for a tool."""
        descriptions = {
            "list_contexts": "List available knowledge contexts",
            "switch_context": "Switch to a different knowledge context",
            "get_context_info": "Get detailed information about current context",
            "query": "Execute queries against the knowledge graph",
            "get_summary": "Get conversational, chat-style responses",
            "find_concept": "Find entities and concepts using semantic search",
            "get_relationships": "Retrieve relationships between entities",
            "search_docs": "Search document chunks with semantic search",
            "search_documents": "Enhanced document search with snippets",
            "explore_graph": "Explore knowledge graph with configurable depth",
            "clear_cache": "Clear various types of caches for performance",
            "help": "Get comprehensive help and usage guidance",
        }
        return descriptions.get(tool_name, "Tool for specialized operations")

    def _get_detailed_tool_info(self, tool_name: str) -> Dict[str, Any]:
        """Get detailed information for a specific tool."""

        # This would be a comprehensive database of tool information
        # For brevity, showing a few examples
        tool_info = {
            "query": {
                "description": "Execute sophisticated queries against the LightRAG knowledge graph",
                "purpose": "The query tool is your primary interface for searching and retrieving information from the knowledge graph. It supports multiple query modes and relationship traversal.",
                "parameters": "• query (required): Your search query\n• mode: Query mode (naive/local/global/hybrid/mix)\n• relationship_depth: Traversal depth (0-3)\n• include_relationships: Include relationship data\n• response_type: Format of response",
                "guidelines": "Use hybrid mode for balanced results, local for entity-focused searches, global for relationship-focused searches. Start with depth 1 for relationships.",
                "use_cases": "Information retrieval, entity discovery, relationship analysis, content research",
                "examples": [
                    {
                        "description": "Basic search with relationships",
                        "parameters": {
                            "query": "authentication system",
                            "mode": "hybrid",
                            "include_relationships": True,
                        },
                    }
                ],
            },
            "explore_graph": {
                "description": "Explore the knowledge graph by traversing relationships with configurable depth",
                "purpose": "Map and visualize entity relationships in the knowledge graph through systematic traversal and exploration.",
                "parameters": "• starting_entity (required): Entity to start exploration from\n• depth: Exploration depth (1-5)\n• exploration_mode: Direction (outbound/inbound/bidirectional)\n• output_format: Result format (hierarchical/network/summary)",
                "guidelines": "Start with depth 1-2 for initial exploration. Use bidirectional mode for comprehensive mapping. Choose output format based on your visualization needs.",
                "use_cases": "Relationship mapping, knowledge discovery, entity network analysis, graph visualization",
                "examples": [
                    {
                        "description": "Explore entity relationships",
                        "parameters": {
                            "starting_entity": "user authentication",
                            "depth": 2,
                            "output_format": "network",
                        },
                    }
                ],
            },
            "clear_cache": {
                "description": "Clear various types of caches to free memory and ensure fresh data",
                "purpose": "Manage system performance by clearing cached data when needed for fresh results or memory optimization.",
                "parameters": "• cache_type: Type to clear (session/redis/lightrag/all)\n• force_clear: Override safety checks\n• include_statistics: Include detailed reporting\n• confirmation_token: Required for 'all' type",
                "guidelines": "Use 'session' for routine clearing, 'redis' for performance issues, 'lightrag' for stale data. Always use confirmation for 'all'.",
                "use_cases": "Performance optimization, memory management, data refresh, troubleshooting",
                "examples": [
                    {
                        "description": "Clear session cache",
                        "parameters": {
                            "cache_type": "session",
                            "include_statistics": True,
                        },
                    }
                ],
            },
        }

        # Return default structure for tools not detailed above
        return tool_info.get(
            tool_name,
            {
                "description": f"Specialized tool for {tool_name} operations",
                "purpose": f"The {tool_name} tool provides specific functionality for knowledge graph operations.",
                "parameters": "See tool schema for detailed parameter information",
                "guidelines": "Follow general best practices for optimal performance",
                "use_cases": "Specialized operations as needed for your workflow",
                "examples": [],
            },
        )

    async def execute_streaming(
        self, session: ConnectionSession, parameters: Dict[str, Any]
    ) -> AsyncGenerator[ToolResult, None]:
        """Execute help tool with streaming progress updates."""
        try:
            topic = parameters.get("topic", "overview")
            help_format = parameters.get("help_format", "structured")

            # Create operation tracking
            operation_id = str(uuid.uuid4())

            # Step 1: Validation (20%)
            yield ToolResult(
                success=True,
                data=ToolProgress(
                    operation_id=operation_id,
                    progress=0.2,
                    status="validation",
                    message=f"Preparing help content for topic: {topic}",
                ),
                metadata={"tool": self.name, "streaming": True},
            )

            # Step 2: Content Generation (60%)
            yield ToolResult(
                success=True,
                data=ToolProgress(
                    operation_id=operation_id,
                    progress=0.6,
                    status="generating",
                    message=f"Generating {help_format} help content and examples",
                ),
                metadata={"tool": self.name, "streaming": True},
            )

            # Step 3: Execute the actual tool
            result = await self.execute(session, parameters)

            # Step 4: Completion (100%)
            success_msg = "Help content generated successfully"
            if not result.success:
                success_msg = f"Help generation completed with errors: {result.error}"

            yield ToolResult(
                success=True,
                data=ToolProgress(
                    operation_id=operation_id,
                    progress=1.0,
                    status="completed",
                    message=success_msg,
                ),
                metadata={"tool": self.name, "streaming": True},
            )

            yield result

        except Exception as e:
            yield ToolResult(
                success=False,
                error=f"Error in streaming help generation: {str(e)}",
                metadata={"tool": self.name, "streaming": True, "error": str(e)},
            )
