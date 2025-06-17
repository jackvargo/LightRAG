# LightRAG Architecture Notes

*This document contains architectural decisions, design patterns, and technical insights for the LightRAG project.*

## 🏗️ System Architecture

### Core Components
- **Backend**: FastAPI service with Docker containerization
- **Frontend**: Vue.js WebUI with hot reload development
- **Storage**: Context-based file storage with JSON document status
- **Context Management**: Multi-context support with dynamic switching

### Service Architecture
```
Frontend (Vue.js) :5173
    ↓ HTTP API
Backend (FastAPI) :9621
    ↓ File I/O
Storage (JSON/Files) ./data/contexts/
```

## 🔄 Context Switching Architecture

### Context Structure
```
data/contexts/
├── {context}/           # Working directory
│   ├── kv_store_doc_status.json
│   ├── graph_chunk_entity_relation.graphml
│   └── [other storage files]
└── {context}_inputs/    # Input documents directory
    └── *.pdf
```

### Context Switch Flow
1. **API Call** → Context switch endpoint
2. **Path Update** → Context manager updates working/input paths
3. **Callback Execution** → RAG instance and storage updated
4. **Storage Reset** → Force re-initialization of document status storage
5. **Document Loading** → Load processed files from new context

## 🚨 Critical Architectural Constraints

### Storage Timing Dependencies
- **Issue**: Storage initialization order affects context switching
- **Solution**: Force storage re-initialization before loading indexed files
- **Pattern**: Timing-sensitive operations require explicit sequencing

### Document Processing Pipeline
- **Constraint**: Never trigger reprocessing during context switches
- **Reason**: Expensive LLM calls and potential data corruption
- **Implementation**: Load existing processed data only

## 📋 Design Patterns

### Surgical Problem Solving
- **Pattern**: Minimal targeted changes over architectural overhauls
- **Application**: Context switching bug fixes
- **Benefit**: Lower risk, faster implementation, easier maintenance

### Multi-Tool Debugging
- **Pattern**: Browser tools + Docker logs + API testing
- **Application**: Context switching and UI debugging
- **Benefit**: Complete visibility into system behavior

## 🔮 Future Architecture Considerations

### Scalability
- Document processing optimization for large document sets
- Storage performance improvements
- Context switching performance optimization

### Reliability
- Unit tests for context switching timing scenarios
- Real-time monitoring and metrics
- Automated testing for context switching workflows

## 🔗 Related Documentation

- **[Context Switching Implementation](../../aidocs/context-switching-remediation-plan.md)** - Detailed technical implementation
- **[Development Workflow](./workflow-scripts.md)** - Development process and scripts

## 🎉 **WebUI Integration Architecture (2025-06-02)**

### **Achievement: Single-Container Production Deployment**

Successfully implemented integrated WebUI deployment architecture that serves both API and WebUI from a single Docker container while preserving development workflow.

#### **Technical Solution**
```
Previous: FastAPI (9621) + Vite Dev Server (5173)
Current:  FastAPI (9621) + Integrated Static Serving

Production: Single container serves both API and WebUI
Development: Preserved separate service workflow
```

#### **Key Architecture Components**

1. **Conditional Mount Strategy** (`lightrag_server.py`)
   ```python
   # Skip old webui mount if integrated static files exist
   integrated_static_dir = Path("/app/static")
   if not (integrated_static_dir.exists() and integrated_static_dir.is_dir()):
       # Mount old webui directory (development mode)
   ```

2. **Integrated Static Serving** (`main.py`)
   ```python
   # Mount fresh static files in production
   if static_dir.exists() and static_dir.is_dir():
       app.mount("/webui", StaticFiles(directory=str(static_dir), html=True), name="webui")
   ```

3. **Multi-Stage Docker Build** (`Dockerfile`)
   ```dockerfile
   # Stage 1: Build WebUI assets
   FROM node:20-alpine AS ui-builder
   RUN npm run build-no-bun

   # Stage 3: Production runtime
   COPY --from=ui-builder /ui/dist /app/static
   ```

#### **Benefits Achieved**
- ✅ **Single Port Deployment**: Port 9621 serves everything
- ✅ **Development Workflow Preserved**: No disruption to existing processes
- ✅ **Clean Architecture**: No complex route manipulation required
- ✅ **Production Ready**: Health checks, authentication, multi-context support
- ✅ **Maintainable**: Simple conditional logic, easy to understand

#### **Performance Impact**
- **Build Time**: ~2-3 minutes (multi-stage caching)
- **Container Size**: Optimized with Python slim base
- **Runtime**: No performance degradation vs separate services
- **Memory**: Single container vs dual container efficiency gain

#### **Deployment Profiles**
| Profile | Purpose | Architecture | Use Case |
|---------|---------|--------------|----------|
| `dev` | Development | API container + Vite dev server | Development workflow |
| `prod` | Production | Integrated API + WebUI container | Homelab, production |
| `ci` | CI/CD | Build validation | Testing, SBOM generation |

This architecture enables seamless transition from development to production while maintaining all LightRAG functionality and providing a foundation for scalable deployment patterns.

---

*This document should be updated as architectural decisions are made and new patterns emerge.*
