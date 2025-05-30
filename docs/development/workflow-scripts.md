# LightRAG Development Workflow Scripts

This document provides detailed information about the development scripts and workflow automation available in the LightRAG project.

## 🚀 Core Development Scripts

### `reload_server.sh` - Primary Development Tool

**Location**: `../LightRAG/reload_server.sh`
**Purpose**: Fast development iteration with Docker container management

#### Command Options

```bash
# FASTEST: Code changes only (~10s)
../LightRAG/reload_server.sh

# SLOWEST: Full rebuild (~2-5min)  
../LightRAG/reload_server.sh --build

# Refresh and reload active context (~10-20s)
../LightRAG/reload_server.sh --restart

# Skip logs (for agent/automated use)
../LightRAG/reload_server.sh --no-follow-logs
```

#### When to Use Each Mode

**Quick Mode (Default)**
- ✅ Python code changes
- ✅ Configuration updates  
- ✅ Bug fixes
- ✅ Most development iterations
- ⚡ **Performance**: ~10 seconds

**Build Mode (`--build`)**
- ✅ Docker configuration changes
- ✅ Dockerfile modifications
- ✅ Major dependency updates
- ✅ Complete environment reset
- ⏰ **Performance**: ~2-5 minutes

**Restart Mode (`--restart`)**
- ✅ Resetting data context from backup
- ✅ Loading documents from active repository
- ✅ Context switching debugging
- ⏱️ **Performance**: ~10-20 seconds

## 🌐 Frontend Development

### WebUI Development Server

```bash
# Start Vue.js development server
./lightrag_webui/npm run dev-no-bun
```

**Features**:
- ✅ Hot reload for Vue.js changes
- ✅ Connects to backend at `http://localhost:9621`
- ✅ Frontend served at `http://localhost:5173`

## 🐳 Docker Management

### Service Status Checking

```bash
# Check service status
./dev-tools.sh status

# Clean environment
./dev-tools.sh cleanup
```

### Manual Docker Commands

```bash
# View backend logs
../lightrag-test/docker compose logs

# Follow logs in real-time
../lightrag-test/docker compose logs -f

# Restart specific service
../lightrag-test/docker compose restart lightrag-api
```

## 🔄 Development Workflow Patterns

### Typical Development Session

1. **Start frontend** (runs continuously):
   ```bash
   ./lightrag_webui/npm run dev-no-bun
   ```

2. **Make backend changes**

3. **Quick reload** (most common):
   ```bash
   ../LightRAG/reload_server.sh
   ```

4. **Test changes** in browser at `http://localhost:5173`

5. **Repeat steps 2-4**

### Context Switching Development

1. **Switch context** via API or UI
2. **Verify context switch** in logs
3. **Test document loading** (should not reprocess)
4. **Use restart mode if needed**:
   ```bash
   ../LightRAG/reload_server.sh --restart
   ```

### Debugging Workflow

1. **Reproduce issue** with current setup
2. **Check Docker logs**:
   ```bash
   ../lightrag-test/docker compose logs
   ```
3. **Make targeted fix**
4. **Quick reload and test**:
   ```bash
   ../LightRAG/reload_server.sh
   ```
5. **Use browser tools** for frontend debugging

## ⚡ Performance Optimization Tips

### Fastest Development Cycle
- Keep WebUI running continuously
- Use quick reload for backend changes  
- Only use `--build` when absolutely necessary
- Use `--no-follow-logs` for automated processes

### File Watching & Auto-Reload
- Backend: Use `reload_server.sh` after changes
- Frontend: Automatic hot reload via npm dev server
- Exclude unnecessary files: `node_modules`, `__pycache__`, etc.

## 🚨 Common Issues & Solutions

### Container Won't Start
1. **Check port conflicts**: `./dev-tools.sh status`
2. **Clean environment**: `./dev-tools.sh cleanup`  
3. **Full rebuild**: `./reload_server.sh --build`

### Frontend Can't Connect to Backend
- ✅ Verify backend URL: `http://localhost:9621`
- ✅ Check Docker container status
- ✅ Ensure no port conflicts

### Context Switch Issues
- ✅ Check backend logs for callback execution
- ✅ Verify document status storage paths
- ✅ Use restart mode to refresh context data

## 📊 Script Performance Metrics

| Operation | Time | Use Case |
|-----------|------|----------|
| Quick Reload | ~10s | Code changes |
| Full Build | ~2-5min | Docker/dependency changes |
| Context Restart | ~10-20s | Data context issues |
| WebUI Start | ~5s | Frontend development |

## 🔗 Related Documentation

- **[Environment Setup](./environment-setup.md)** - Complete setup guide
- **[Cursor Rules](./cursor-rules.md)** - AI assistant development patterns

---

*Keep this documentation updated as new scripts and workflow improvements are added.* 