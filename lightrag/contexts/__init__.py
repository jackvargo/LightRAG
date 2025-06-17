"""
LightRAG Multi-Context Support Module.

This module provides functionality for managing multiple knowledge base contexts
within LightRAG, allowing for isolation between different user contexts and
knowledge bases.
"""

from .context_manager import ContextManager

__all__ = ['ContextManager'] 