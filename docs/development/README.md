# LightRAG Development Documentation

This directory contains development environment setup, workflows, and best practices for the LightRAG project.

## 📁 Documentation Structure

- **[Environment Setup](./environment-setup.md)** - Development environment configuration and scripts
- **[Cursor Rules](./cursor-rules.md)** - AI assistant rules and development patterns
- **[Workflow Scripts](./workflow-scripts.md)** - Development script documentation and usage
- **[Architecture Notes](./architecture-notes.md)** - Project architecture and design decisions

## 🚀 Quick Start for New Developers

1. **Environment Setup**: Follow [environment-setup.md](./environment-setup.md)
2. **Development Workflow**: Review [workflow-scripts.md](./workflow-scripts.md) 
3. **AI Assistant Setup**: Configure [cursor-rules.md](./cursor-rules.md)
4. **Architecture Understanding**: Read [architecture-notes.md](./architecture-notes.md)

## 🔄 Development Workflow Summary

### Fast Development Cycle
```bash
# Quick code changes (~10s)
../LightRAG/reload_server.sh

# Full rebuild (~2-5min) 
../LightRAG/reload_server.sh --build

# Context refresh (~10-20s)
../LightRAG/reload_server.sh --restart
```

### Service Ports
- **Backend**: http://localhost:9621 (FastAPI + Docker)
- **Frontend**: http://localhost:5173 (Vue.js WebUI)

## 📚 Related Documentation

- **[Main README](../../README.md)** - Project overview and usage
- **[Context Switching Guide](../../aidocs/context-switching-remediation-plan.md)** - Multi-context development
- **[API Documentation](../api/)** - Backend API reference

---

*This documentation is maintained alongside the codebase to ensure development practices stay current with project evolution.* 