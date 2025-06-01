"""
FastAPI main application with integrated WebUI static file serving.
This module extends the existing lightrag_server.py with static file capabilities.
"""

import os
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from lightrag.api.lightrag_server import create_app
from lightrag.api.config import global_args


class SPAStaticFiles(StaticFiles):
    """Custom StaticFiles that serves index.html for SPA routing."""
    
    async def get_response(self, path: str, scope):
        """Override to serve index.html for SPA routes that don't match files."""
        try:
            # Try to get the file normally
            response = await super().get_response(path, scope)
            return response
        except Exception:
            # If file not found and it's not an API route, serve index.html
            if not path.startswith('api/') and not path.endswith('.js') and not path.endswith('.css') and not path.endswith('.ico'):
                # Serve index.html for SPA routing
                index_path = str(Path(self.directory) / "index.html")
                if Path(index_path).exists():
                    return FileResponse(index_path)
            raise


def create_main_app():
    """Create the main FastAPI application with static file serving."""
    
    # Create the base application from lightrag_server using global_args
    app = create_app(global_args)
    
    # Static files directory (matches the Docker COPY location)
    static_dir = Path("/app/static")
    
    # Health check endpoint (required for Docker health checks)
    @app.get("/health")
    async def health_check():
        """Health check endpoint for container monitoring."""
        return {
            "status": "healthy", 
            "timestamp": datetime.utcnow().isoformat(),
            "webui_available": static_dir.exists() and static_dir.is_dir(),
            "static_files_count": len(list(static_dir.glob("**/*"))) if static_dir.exists() else 0
        }
    
    # Only mount static files if the directory exists (production mode)
    if static_dir.exists() and static_dir.is_dir():
        # Mount static files for WebUI with SPA support
        app.mount("/webui", SPAStaticFiles(directory=str(static_dir), html=True), name="webui")
    
    return app


# Create the app instance
app = create_main_app() 