---
description: 
globs: 
alwaysApply: true
---
# LightRAG Development Rules for Cursor

## Project Structure
This is a LightRAG development environment with:
- **Backend**: Python FastAPI service (port 9621)
- **Frontend**: Vue.js WebUI (port 5173) 
- **Data**: Context-based storage in `./data/contexts/`
- **Docker**: Containerized backend service
- **Development Tools**: Optimized scripts for fast iteration

## Development Workflow Scripts

### Quick Development Commands
```bash
# FASTEST: Code changes only (~10s)
../LightRAG/reload_server.sh

# SLOWEST: Full rebuild (~2-5min)
../LightRAG/reload_server.sh --build

# Refresh and reload active context (~10-20s)
../LightRAG/reload_server.sh --restart

# Optional command flag to skip the logs report so the command doesn't hang for agent use
# This can be added to any other command flags
../LightRAG/reload_server.sh --no-follow-logs

### Development Tools
```bash

# Start WebUI development
./lightrag_webui/npm run dev-no-bun

## Service Management Rules

### When to Use Each Reload Mode:

1. **QUICK MODE** - Use for:
   - Code changes in Python files
   - Configuration updates
   - Bug fixes
   - Most development iterations

2. **BUILD MODE** - Use for:
   - Docker configuration changes
   - Dockerfile modifications
   - Major dependency updates
   - Complete environment reset

3. **RESTART MODE** - Use for:
   - Resetting data context from backup
   - Load documents from active repository properly

### Context Switching Debugging

When context switching fails:
1. Check backend logs: `../lightrag-test/docker compose logs`
2. Document paths are defined for each context in ../lightrag-test/data/context/contexts.json
3. Check storage reset: Storage namespaces should reset initialization flags only
4. Do not start individual server processes.  Use @reload_server.sh to reset the docker container.  Then use the endpoints from that docker instance served at localhost:9621.
5. The solution has authentication enabled with credentials admin:admin123

### Development Best Practices

1. **Always use quick mode first** - It's 10x faster than full rebuild

### Common Issues & Solutions

#### Document Reprocessing
- **Problem**: Documents reprocess on context switch
- **Cause**: Incorrect document ID generation in scan
- **Solution**: Fixed to use content-based MD5 hash like main system

#### Context Switch Failures  
- **Problem**: Context switch doesn't work
- **Cause**: Storage instances keep old file paths
- **Solution**: Reset initialization flags, update global_config in storage instances

#### Container Issues
- **Problem**: Backend service won't start
- **Solutions**: 
  1. Check port conflicts: `./dev-tools.sh status`
  2. Clean environment: `./dev-tools.sh cleanup`
  3. Full rebuild: `./reload_server.sh --build`

#### WebUI Issues
- **Problem**: Frontend doesn't connect to backend
- **Cause**: Wrong backend URL in constants
- **Solution**: Ensure `backendBaseUrl = 'http://localhost:9621'`
- Use BrowserTools MCP server to test and verify responses.  Be aware that attempts to reprocess files are creating the doc status json file to be overwritten and must be refreshed from the backup.

### Performance Optimization

- Use `rsync` instead of `cp` for faster file copying
- Exclude unnecessary files (node_modules, __pycache__, etc.)
- Only restart service, don't rebuild unless necessary

### File Watching & Auto-Reload

For fastest development:
1. Keep WebUI running: `./lightrag-webui/npm run dev-no-bun`
2. Use quick reload for backend changes which starts the logs, as well: `./reload_server.sh`

### Debugging Context Issues

Key files to check:
- `lightrag/kg/shared_storage.py` - Storage reset logic
- `lightrag/lightrag.py` - Working directory updates  
- `lightrag/api/routers/document_routes.py` - Document scanning
- `lightrag_webui/src/lib/constants.ts` - Frontend API config

### Environment Variables

Critical environment variables:
- `WORKING_DIR` - Base data directory
- `API_PORT` - Backend port (default: 9621)
- `WEB_PORT` - Frontend port (default: 5173)
- `OPENAI_API_KEY` - This is intentionally wrong right now to avoid costly reprocessing until the errors with mutli context are resolved.

Remember: This development environment is optimized for fast iteration. Use the appropriate reload mode for your changes, and always monitor logs to catch issues early. 