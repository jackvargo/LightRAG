"""
Context management routes for LightRAG API.
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Optional, List
from pydantic import BaseModel
from lightrag.contexts.context_manager import ContextManager
from lightrag.utils import logger
from lightrag.api.utils_api import get_combined_auth_dependency
import os
from pathlib import Path
import json
import asyncio

router = APIRouter(prefix="/contexts", tags=["contexts"])

# Get the auth dependency - we'll apply it to individual routes
def get_auth_dependency():
    """Get the authentication dependency for context routes"""
    api_key = os.getenv("LIGHTRAG_API_KEY")
    return get_combined_auth_dependency(api_key)

class ContextCreate(BaseModel):
    name: str
    description: str = ""

class ContextRename(BaseModel):
    new_name: str

class ContextStats(BaseModel):
    documents_count: int = 0
    entities_count: int = 0
    relationships_count: int = 0
    disk_usage_mb: float = 0

class ContextInfo(BaseModel):
    description: str
    path: str
    created_at: str
    is_default: bool = False
    is_current: bool = False
    stats: Optional[ContextStats] = None

class ContextsResponse(BaseModel):
    contexts: Dict[str, Dict]
    current_context: Optional[str]

def get_context_stats(context_path: str) -> ContextStats:
    """
    Get statistics for a specific context.
    
    Args:
        context_path: Path to the context directory
        
    Returns:
        ContextStats: Statistics about the context
    """
    try:
        path = Path(context_path)
        stats = ContextStats()
        
        # Calculate total size
        total_size = 0
        for item in path.glob('**/*'):
            if item.is_file():
                total_size += item.stat().st_size
        
        stats.disk_usage_mb = round(total_size / (1024 * 1024), 2)  # Convert to MB
        
        # Count documents
        doc_status_file = path / "doc_status.json"
        if doc_status_file.exists():
            with open(doc_status_file, 'r') as f:
                try:
                    doc_data = json.load(f)
                    # Count documents in all statuses
                    stats.documents_count = len(doc_data) if isinstance(doc_data, dict) else 0
                except json.JSONDecodeError:
                    pass
        
        # Count entities and relationships
        entities_file = path / "entities.json"
        relationships_file = path / "relationships.json"
        
        if entities_file.exists():
            with open(entities_file, 'r') as f:
                try:
                    entities_data = json.load(f)
                    stats.entities_count = len(entities_data) if isinstance(entities_data, dict) else 0
                except json.JSONDecodeError:
                    pass
                    
        if relationships_file.exists():
            with open(relationships_file, 'r') as f:
                try:
                    relationships_data = json.load(f)
                    stats.relationships_count = len(relationships_data) if isinstance(relationships_data, dict) else 0
                except json.JSONDecodeError:
                    pass
                    
        return stats
    except Exception as e:
        # Return empty stats on error
        return ContextStats()

@router.get("/", response_model=ContextsResponse, dependencies=[Depends(get_auth_dependency())])
@router.get("", response_model=ContextsResponse, dependencies=[Depends(get_auth_dependency())])
async def list_contexts():
    """List all available contexts and the current active context."""
    context_manager = ContextManager.get_instance()
    contexts = context_manager.list_contexts()
    current_context = context_manager.get_current_context()
    return {"contexts": contexts, "current_context": current_context}

@router.get("/{context_name}/stats", response_model=ContextStats, dependencies=[Depends(get_auth_dependency())])
async def get_context_statistics(context_name: str):
    """Get statistics for a specific context."""
    context_manager = ContextManager.get_instance()
    context_path = context_manager.get_context_path(context_name)
    
    if not context_path:
        raise HTTPException(status_code=404, detail="Context not found")
        
    # Get statistics for the context
    stats = get_context_stats(str(context_path))
    return stats

@router.post("/", response_model=bool, dependencies=[Depends(get_auth_dependency())])
async def create_context(context: ContextCreate):
    """Create a new context."""
    context_manager = ContextManager.get_instance()
    success = context_manager.create_context(context.name, context.description)
    if not success:
        raise HTTPException(status_code=400, detail="Context already exists")
    return success

@router.post("/{context_name}/switch", response_model=Dict, dependencies=[Depends(get_auth_dependency())])
async def switch_context(context_name: str):
    """Switch to a different context."""
    logger.info(f"API request to switch to context: {context_name}")
    context_manager = ContextManager.get_instance()

    # Get current context for logging
    current = context_manager.get_current_context()
    logger.info(f"Current context before switch: {current}")

    # Attempt to switch context
    success = await context_manager.switch_context(context_name)

    if not success:
        logger.error(f"Failed to switch to context: {context_name}")
        raise HTTPException(
            status_code=404,
            detail={
                "message": "Context not found or switch failed",
                "previous_context": current,
                "requested_context": context_name
            }
        )

    # Verify switch was successful
    new_current = context_manager.get_current_context()
    logger.info(f"Context after switch: {new_current}")

    # Get context path to verify it's correct
    context_path = context_manager.get_context_path(context_name)

    # Add a small delay to ensure async operations have time to start
    await asyncio.sleep(0.5)

    # Return detailed information for debugging
    return {
        "success": success,
        "previous_context": current,
        "current_context": new_current,
        "context_path": str(context_path) if context_path else None,
        "message": f"Successfully switched to context: {context_name}"
    }

@router.delete("/{context_name}", response_model=bool, dependencies=[Depends(get_auth_dependency())])
async def delete_context(context_name: str):
    """Delete a context."""
    context_manager = ContextManager.get_instance()
    success = context_manager.delete_context(context_name)
    if not success:
        raise HTTPException(status_code=404, detail="Context not found or it's the last remaining context")
    return success

@router.put("/{context_name}/rename", response_model=bool, dependencies=[Depends(get_auth_dependency())])
async def rename_context(context_name: str, rename: ContextRename):
    """Rename a context."""
    context_manager = ContextManager.get_instance()
    success = context_manager.rename_context(context_name, rename.new_name)
    if not success:
        raise HTTPException(status_code=400, detail="Invalid rename operation")
    return success 