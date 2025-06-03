# LightRAG Development TODO

*Last Updated: [Current Date]*

---

## 🐛 **Bugs & Issues**

### **P1 - High Priority**

- [ ] **Context Rename Breaks Retrieval Chat**
  - **Issue**: When a context is renamed, retrieval chat generates 500 error
  - **Error**: `[Errno 2] No such file or directory: '/app/data/contexts/bc_data/kv_store_llm_response_cache.json'`
  - **Location**: `/query/stream` endpoint
  - **Impact**: Chat functionality broken after context rename
  - **Root Cause**: File paths not updated when context directory is renamed
  - **Notes**: Graph and document pipeline/processing still work correctly
  - **Status**: Investigation needed

- [ ] **Stats Not Calculated/Populated** 
  - **Issue**: Context stats (Documents, Entities, Relationships, Size) show as 0 or empty
  - **Impact**: Users cannot see context metrics and storage information
  - **Status**: Investigation needed to determine calculation logic

### **P2 - Medium Priority**

*No medium priority bugs currently identified*

### **P3 - Low Priority**

*No low priority bugs currently identified*

---

## 🚀 **Features & Enhancements**

### **Multi-Context Support**

- [ ] **Extend multicontext support to the rest of the data store options**
  - **Status**: In progress
  - **Priority**: Medium
  - **Notes**: Currently focused on KV store, need to extend to other storage backends

### **Testing & Quality**

- [ ] **Write tests for multicontext enhancements**
  - **Status**: Planned
  - **Priority**: Medium
  - **Dependencies**: Complete multicontext support implementation

### **Documentation**

- [ ] **Clean up/expand this document**
  - **Status**: In progress
  - **Priority**: Low
  - **Notes**: This reformatting addresses part of this requirement

---

## 🔧 **Technical Debt**

*Technical debt items to be identified and added*

---

## 📈 **Performance & Optimization**

*Performance optimization tasks to be identified and added*

---

## 🛡️ **Security & Hardening**

*Security improvements to be identified and added*

---

## 📋 **Task Status Legend**

- [ ] **Not Started** - Task not yet begun
- [🔄] **In Progress** - Task currently being worked on
- [✅] **Complete** - Task finished and validated
- [⏸️] **Blocked** - Task waiting on dependencies
- [❌] **Cancelled** - Task no longer needed

---

## 📝 **Notes**

- Use GitHub issues for tracking detailed progress
- Update this document regularly as new items are identified
- Link to relevant commits, PRs, and documentation
- Include reproduction steps for bugs when possible