"""
Context Manager for LightRAG multi-context support.
Handles creation, switching, and management of different knowledge base contexts.
"""

from typing import Dict, Optional, Callable, Tuple
import os
import json
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("lightrag")

class ContextManager:
    _instance = None
    _initialized = False
    
    # Callback when context is switched to update LightRAG instance
    _on_context_switch_callback = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(ContextManager, cls).__new__(cls)
        return cls._instance

    def __init__(self, base_storage_path: str = None):
        """
        Initialize the context manager.
        
        Args:
            base_storage_path: Base path where all contexts will be stored
        """
        if not self._initialized:
            if base_storage_path is None:
                base_storage_path = os.getenv('CONTEXTS_DIR', './data/contexts')
            self.base_storage_path = Path(base_storage_path)
            self.base_storage_path.mkdir(parents=True, exist_ok=True)
            
            # Initialize with empty context information
            self.contexts: Dict[str, Dict] = {}
            self.current_context: Optional[str] = None
            
            # Get default context name from environment or use 'default'
            self.default_context_name = os.getenv('DEFAULT_CONTEXT', 'default')
            
            # Load existing contexts or create default
            self._load_contexts()
            self._ensure_default_context()
            self._initialized = True

    @classmethod
    def get_instance(cls) -> 'ContextManager':
        """Get the singleton instance of the context manager."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def register_context_switch_callback(cls, callback):
        """
        Register a callback function to be called when context is switched.

        Args:
            callback: Function to be called with context_name and context_path
        """
        # Remove type annotation to be more flexible with callback signatures
        cls._on_context_switch_callback = callback
        logger.info(f"Registered context switch callback: {callback}")
        
    def _load_contexts(self):
        """Load existing contexts from storage."""
        contexts_file = self.base_storage_path / "contexts.json"
        
        # Check current_context.txt file first to establish priority
        persistence_file = self.base_storage_path / "current_context.txt"
        current_from_file = None
        if persistence_file.exists():
            try:
                with open(persistence_file, 'r') as f:
                    current_from_file = f.read().strip()
                    logger.info(f"Found context name in current_context.txt: {current_from_file}")
            except Exception as e:
                logger.error(f"Error reading current_context.txt: {str(e)}")
                # Fall back to default context on error
                current_from_file = self.default_context_name
        
        # Load the contexts from JSON
        if contexts_file.exists():
            try:
                with open(contexts_file, 'r') as f:
                    self.contexts = json.load(f)

                # Log all loaded contexts
                logger.info(f"Loaded contexts: {list(self.contexts.keys())}")

                # Process all contexts to ensure they have the required attributes
                for name, info in self.contexts.items():
                    # Ensure working_path is set
                    if "working_path" not in info:
                        info["working_path"] = info.get("path", str(self.base_storage_path / name))
                        logger.info(f"Added working_path for context '{name}': {info['working_path']}")
                    
                    # Ensure path is set (backwards compatibility)
                    if "path" not in info:
                        info["path"] = info["working_path"]
                        logger.info(f"Added path for context '{name}': {info['path']}")
                    
                    # Ensure input_path is set
                    if "input_path" not in info:
                        # Derive input path from working path by adding "_inputs" suffix
                        working_path = Path(info["working_path"])
                        if working_path.name.endswith("_data"):
                            # For context folders with "_data" suffix, use the corresponding "_data_inputs" folder
                            input_path = working_path.with_name(f"{working_path.name}_inputs")
                        else:
                            # For other context folders, append "_inputs" to the folder name
                            input_path = working_path.with_name(f"{working_path.name}_inputs")
                        
                        info["input_path"] = str(input_path)
                        logger.info(f"Added derived input_path for context '{name}': {input_path}")

                # Priority for setting current context:
                # 1. Value from current_context.txt if valid
                # 2. Context marked as "is_current" in contexts.json
                # 3. Default context name if available
                # 4. First available context
                # 5. None (if no contexts available)
                
                # First check if the context from current_context.txt exists
                if current_from_file and current_from_file in self.contexts:
                    self.current_context = current_from_file
                    logger.info(f"Setting current context from current_context.txt: {current_from_file}")
                else:
                    # Try to find a context marked as current in contexts.json
                    current_from_json = None
                    for name, info in self.contexts.items():
                        if info.get("is_current", False):
                            current_from_json = name
                            logger.info(f"Found context marked as current in JSON: {name}")
                            break
                    
                    if current_from_json:
                        # Use the current context from contexts.json
                        self.current_context = current_from_json
                        logger.info(f"Setting current context from contexts.json: {current_from_json}")
                    elif self.contexts:
                        # If no current context is specified, use the default context or first available
                        if self.default_context_name in self.contexts:
                            self.current_context = self.default_context_name
                            logger.info(f"No current context specified, using default: {self.default_context_name}")
                        else:
                            first_context = next(iter(self.contexts.keys()))
                            self.current_context = first_context
                            logger.info(f"No current context specified, using first available: {first_context}")
                    else:
                        logger.warning("No contexts found in contexts.json")
                        self.current_context = None
                
                # Update is_current flags to match self.current_context
                if self.current_context:
                    for name, info in self.contexts.items():
                        info["is_current"] = (name == self.current_context)

                # Force save to ensure consistency between files
                self._save_contexts()
                logger.info(f"Context environment initialized. Current context: {self.current_context}")

                # DO NOT attempt async initialization here - we'll let the server handle this after startup
                # Just log that initialization is complete
                if self.current_context:
                    context_info = self.contexts[self.current_context]
                    context_working_path = Path(context_info.get("working_path", context_info["path"]))
                    context_input_path = Path(context_info.get("input_path", 
                                      context_working_path.with_name(f"{context_working_path.name}_inputs")))
                    
                    logger.info(f"Context initialized with: name='{self.current_context}', working_path='{context_working_path}', input_path='{context_input_path}'")
                    # The server will need to call switch_context explicitly or use the working_dir directly

            except Exception as e:
                logger.error(f"Error loading contexts: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                self.contexts = {}
                # Fall back to the default context if there's an error
                if self.current_context is None and self.default_context_name:
                    # This will create the default context if needed
                    self._ensure_default_context()

    def _save_contexts(self):
        """Save contexts to storage."""
        try:
            self.base_storage_path.mkdir(parents=True, exist_ok=True)

            # Update is_current flags first to ensure consistency
            if self.current_context:
                for name, info in self.contexts.items():
                    info["is_current"] = (name == self.current_context)

            # Save contexts.json
            contexts_file = self.base_storage_path / "contexts.json"
            with open(contexts_file, 'w') as f:
                json.dump(self.contexts, f, indent=2)

            # Persist the current context in text file
            persistence_file = self.base_storage_path / "current_context.txt"
            if self.current_context:
                with open(persistence_file, 'w') as f:
                    f.write(self.current_context)
                logger.info(f"Saved current context to file: {self.current_context}")
            else:
                # Write default context if current is not set
                if self.default_context_name in self.contexts:
                    with open(persistence_file, 'w') as f:
                        f.write(self.default_context_name)
                    logger.info(f"Saved default context to file: {self.default_context_name}")
                # Remove the file if no current or default context
                elif persistence_file.exists():
                    persistence_file.unlink()
                    logger.warning("No current or default context to save")

        except Exception as e:
            logger.error(f"Error saving contexts: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())

    def _ensure_default_context(self):
        """Create default context if no contexts exist."""
        if not self.contexts:
            default_created = self.create_context(
                self.default_context_name, 
                "Default knowledge repository"
            )
            if default_created:
                logger.info(f"Created default context: {self.default_context_name}")
                self.current_context = self.default_context_name
                self._save_contexts()
        elif not self.current_context:
            # If contexts exist but none is selected, use the default or first available
            if self.default_context_name in self.contexts:
                self.current_context = self.default_context_name
                logger.info(f"Setting current context to default: {self.default_context_name}")
                self._save_contexts()
            else:
                first_context = next(iter(self.contexts.keys()))
                self.current_context = first_context
                logger.info(f"Setting current context to first available: {first_context}")
                self._save_contexts()

    def reset_to_default_context(self):
        """Reset to the default context."""
        if self.default_context_name in self.contexts:
            logger.info(f"Resetting to default context: {self.default_context_name}")
            return self.switch_context(self.default_context_name)
        elif self.contexts:
            first_context = next(iter(self.contexts.keys()))
            logger.info(f"Default context not found, switching to first available: {first_context}")
            return self.switch_context(first_context)
        else:
            logger.error("No contexts available to switch to")
            return False

    def create_context(self, context_name: str, description: str = "", 
                       working_path: str = None, input_path: str = None) -> bool:
        """
        Create a new context.
        
        Args:
            context_name: Name of the context
            description: Optional description of the context
            working_path: Optional custom working directory path
            input_path: Optional custom input directory path
            
        Returns:
            bool: True if context was created successfully
        """
        if context_name in self.contexts:
            return False

        try:
            # Set up working directory path
            if working_path:
                context_working_path = Path(working_path)
            else:
                context_working_path = self.base_storage_path / context_name
            
            # Set up input directory path
            if input_path:
                context_input_path = Path(input_path)
            else:
                # Default: append "_inputs" to the working path name
                working_name = context_working_path.name
                if working_name.endswith("_data"):
                    # For working dirs with "_data" suffix, use corresponding "_data_inputs"
                    context_input_path = context_working_path.with_name(f"{working_name}_inputs")
                else:
                    # For other working dirs, just append "_inputs"
                    context_input_path = context_working_path.with_name(f"{working_name}_inputs")
            
            # Create directories
            context_working_path.mkdir(parents=True, exist_ok=True)
            context_input_path.mkdir(parents=True, exist_ok=True)

            # Store context information
            self.contexts[context_name] = {
                "description": description,
                "path": str(context_working_path),  # Keep for backward compatibility
                "working_path": str(context_working_path),
                "input_path": str(context_input_path),
                "created_at": str(datetime.now())
            }
            
            self._save_contexts()
            
            # If this is the first context, switch to it
            if len(self.contexts) == 1:
                self.current_context = context_name
                self._save_contexts()
            
            return True
        except Exception as e:
            logger.error(f"Error creating context {context_name}: {str(e)}")
            return False

    async def switch_context(self, context_name: str) -> bool:
        """
        Switch to a different context.

        Args:
            context_name: Name of the context to switch to

        Returns:
            bool: True if context switch was successful
        """
        logger.info(f"API request to switch to context: {context_name}")
        if not self.contexts:
            logger.error("No contexts loaded.")
            return False
        previous_context = self.current_context
        logger.info(f"Current context before switch: {previous_context}")

        if context_name not in self.contexts:
            logger.error(f"Context '{context_name}' not found.")
            return False

        try:
            # Check if we're already in this context to avoid unnecessary operations
            if self.current_context == context_name:
                logger.info(f"Already in context: {context_name}, no switch needed")
                return True

            # Update current context flags in contexts dictionary
            if self.current_context and self.current_context in self.contexts:
                self.contexts[self.current_context]["is_current"] = False

            # Set new context as current
            self.contexts[context_name]["is_current"] = True
            self.current_context = context_name
            self._save_contexts()

            # Get the context paths
            context_info = self.contexts[context_name]
            # Use working_path if available, fall back to path for backward compatibility
            context_working_path = Path(context_info.get("working_path", context_info["path"]))
            # Use input_path if available, or derive from working_path
            context_input_path = Path(context_info.get("input_path", 
                                      context_working_path.with_name(f"{context_working_path.name}_inputs")))
            
            logger.info(f"Context working path for '{context_name}': {context_working_path}")
            logger.info(f"Context input path for '{context_name}': {context_input_path}")

            # Ensure the context directories exist
            if not context_working_path.exists():
                logger.warning(f"Context working directory does not exist at {context_working_path}, creating it")
                context_working_path.mkdir(parents=True, exist_ok=True)
            
            if not context_input_path.exists():
                logger.warning(f"Context input directory does not exist at {context_input_path}, creating it")
                context_input_path.mkdir(parents=True, exist_ok=True)

            # Call the registered callback if available
            if ContextManager._on_context_switch_callback:
                logger.info(f"Calling context switch callback for '{context_name}'")
                import inspect
                logger.info(f"Callback function (via class): {ContextManager._on_context_switch_callback}")
                logger.info(f"Callback signature (via class): {inspect.signature(ContextManager._on_context_switch_callback)}")
                try:
                    # Call the registered callback with the new context name and paths
                    # The callback is expected to be an async function now
                    await ContextManager._on_context_switch_callback(
                        context_name,
                        context_working_path,
                        previous_context_name=previous_context,
                        requested_context_name=context_name,
                        context_input_path=context_input_path  # Pass input path to callback
                    )
                    logger.info(f"Context switch callback successfully called for {context_name}")
                except Exception as e:
                    logger.error(f"Error during context switch callback for {context_name}: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    return False  # Indicate failure if callback fails
            else:
                logger.warning("No context switch callback registered.")

            logger.info(f"Successfully switched to context: {self.current_context}")
            logger.info(f"Context after switch: {self.current_context}")
            return True
        except Exception as e:
            logger.error(f"Error switching context: {e}")
            self.current_context = previous_context # Revert to previous context on error
            self._save_contexts()
            return False

    def delete_context(self, context_name: str) -> bool:
        """
        Delete a context.
        
        Args:
            context_name: Name of the context to delete
            
        Returns:
            bool: True if context was deleted successfully
        """
        if context_name not in self.contexts:
            return False

        # Don't allow deleting the last context
        if len(self.contexts) <= 1:
            logger.error("Cannot delete the last remaining context")
            return False

        try:
            context_info = self.contexts[context_name]
            working_path = Path(context_info.get("working_path", context_info["path"]))
            input_path = Path(context_info.get("input_path", 
                             working_path.with_name(f"{working_path.name}_inputs")))
            
            import shutil
            # Delete working directory if it exists
            if working_path.exists():
                shutil.rmtree(working_path)
                
            # Delete input directory if it exists
            if input_path.exists():
                shutil.rmtree(input_path)

            del self.contexts[context_name]
            
            # If we delete the current context, switch to another one
            if self.current_context == context_name:
                self.current_context = None
                # Switch to default if it exists, otherwise the first available
                if self.default_context_name in self.contexts:
                    self.current_context = self.default_context_name
                else:
                    first_context = next(iter(self.contexts.keys()))
                    self.current_context = first_context
                
            self._save_contexts()
            return True
        except Exception as e:
            logger.error(f"Error deleting context {context_name}: {str(e)}")
            return False

    def get_context_paths(self, context_name: Optional[str] = None) -> Tuple[Optional[Path], Optional[Path]]:
        """
        Get the working and input paths for a context.
        
        Args:
            context_name: Name of the context (uses current context if None)
            
        Returns:
            Tuple[Optional[Path], Optional[Path]]: Tuple of (working_path, input_path)
        """
        context = context_name or self.current_context
        if not context or context not in self.contexts:
            # Return default paths if context not found
            if self.default_context_name in self.contexts:
                context = self.default_context_name
            else:
                return None, None
            
        context_info = self.contexts[context]
        working_path = Path(context_info.get("working_path", context_info["path"]))
        input_path = Path(context_info.get("input_path", 
                         working_path.with_name(f"{working_path.name}_inputs")))
        
        return working_path, input_path
    
    def get_context_path(self, context_name: Optional[str] = None) -> Optional[Path]:
        """
        Get the storage path for a context (backward compatibility method).
        
        Args:
            context_name: Name of the context (uses current context if None)
            
        Returns:
            Optional[Path]: Path to the context working directory
        """
        working_path, _ = self.get_context_paths(context_name)
        return working_path
    
    def get_current_context(self) -> Optional[str]:
        """
        Get the name of the current context.
        
        Returns:
            Optional[str]: Name of the current context
        """
        # Return the default if no current context is set
        if not self.current_context and self.default_context_name in self.contexts:
            return self.default_context_name
        return self.current_context

    def list_contexts(self) -> Dict[str, Dict]:
        """
        List all available contexts.
        
        Returns:
            Dict[str, Dict]: Dictionary of context information
        """
        contexts_info = self.contexts.copy()
        
        # Add indicators for default and current contexts
        for name, info in contexts_info.items():
            info["is_default"] = name == self.default_context_name
            info["is_current"] = name == self.current_context
            
        return contexts_info

    def rename_context(self, old_name: str, new_name: str) -> bool:
        """
        Rename a context.
        
        Args:
            old_name: Current name of the context
            new_name: New name for the context
            
        Returns:
            bool: True if context was renamed successfully
        """
        if old_name not in self.contexts or new_name in self.contexts:
            return False

        try:
            # Get the old context info
            context_info = self.contexts[old_name].copy()
            
            # Get the old paths
            old_working_path = Path(context_info.get("working_path", context_info["path"]))
            old_input_path = Path(context_info.get("input_path", 
                                 old_working_path.with_name(f"{old_working_path.name}_inputs")))
            
            # Calculate new paths
            if "working_path" in context_info:
                # If custom working path, keep custom pattern but update name
                new_working_path = self.base_storage_path / new_name
                
                # For custom input path, keep the pattern but update name
                if "input_path" in context_info:
                    new_input_path = old_input_path.with_name(old_input_path.name.replace(old_name, new_name))
                else:
                    new_input_path = new_working_path.with_name(f"{new_working_path.name}_inputs")
            else:
                # Use default paths based on the base storage path
                new_working_path = self.base_storage_path / new_name
                new_input_path = new_working_path.with_name(f"{new_working_path.name}_inputs")

            # Rename the directories
            if old_working_path.exists():
                old_working_path.rename(new_working_path)
            
            if old_input_path.exists():
                old_input_path.rename(new_input_path)

            # Update the context info
            context_info["path"] = str(new_working_path)  # Update for backward compatibility
            context_info["working_path"] = str(new_working_path)
            context_info["input_path"] = str(new_input_path)
            
            self.contexts[new_name] = context_info
            del self.contexts[old_name]

            # Update current context if needed
            if self.current_context == old_name:
                self.current_context = new_name
                
            # Update default context if needed
            if self.default_context_name == old_name:
                self.default_context_name = new_name

            self._save_contexts()
            return True
        except Exception as e:
            logger.error(f"Error renaming context {old_name} to {new_name}: {str(e)}")
            return False 