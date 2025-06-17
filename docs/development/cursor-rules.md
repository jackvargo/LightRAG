# Cursor AI Assistant Rules for LightRAG Development

This file contains AI assistant rules and development patterns specific to the LightRAG project. These rules help maintain consistency and best practices during development.

## 🎯 Project Context Rules

### Project Understanding
- This is a LightRAG development environment with multi-context support
- Backend: Python FastAPI service (Docker, port 9621)
- Frontend: Vue.js WebUI (port 5173)
- Data: Context-based storage in `./data/contexts/`
- Development tools: Optimized scripts for fast iteration

### Code Change Philosophy
- **Minimal surgical changes** over architectural overhauls
- **Preserve existing functionality** - only change what's necessary
- **Leverage existing patterns** rather than reinventing functionality
- **Never remove packages** unless explicitly intended - only add new ones
- **Append dependencies** rather than modifying existing ones

## 🔧 Development Workflow Rules

### When Making Changes
1. **Use quick reload first**: `../LightRAG/reload_server.sh` (~10s)
2. **Full rebuild only when needed**: `../LightRAG/reload_server.sh --build` (~2-5min)
3. **Context refresh for data issues**: `../LightRAG/reload_server.sh --restart` (~10-20s)

### Code Quality Standards
- **Add comprehensive logging** for debugging
- **Include error handling** and graceful fallbacks
- **Write clear code comments** and documentation
- **Test changes incrementally** using the reload scripts

## 🚫 Critical Restrictions

### Never Do These Things
- **Don't trigger document reprocessing** during context switches (costly LLM calls)
- **Don't modify core storage initialization** unless absolutely necessary
- **Don't change existing storage class interfaces**
- **Don't alter document processing pipeline** without explicit need
- **Don't start individual server processes** - use reload_server.sh with Docker

### Development Environment Protection
- **OpenAI API key intentionally disabled** to prevent costly reprocessing during debugging
- **Use backup/restore procedures** for document status during testing
- **Context switching should load existing data**, never reprocess documents

## 🎓 Development Patterns

### Debugging Methodology
1. **Multi-tool analysis**: Browser tools + Docker logs + API testing
2. **Iterative debugging**: Each reload cycle reveals new information
3. **Log analysis**: Check Docker logs for timing and sequence issues
4. **Surface vs. deep testing**: Don't assume surface success means deep success

### Problem-Solving Approach
1. **Identify exact timing/sequence issues** before implementing fixes
2. **Test the sequence of operations**, not just their execution
3. **Use surgical fixes** at precise moments rather than broad changes
4. **Document lessons learned** for future similar issues

## 🔗 Related Documentation

- **[Environment Setup](./environment-setup.md)** - Complete development workflow details
- **[Context Switching Guide](../../aidocs/context-switching-remediation-plan.md)** - Context switching implementation and debugging

---

*These rules are derived from actual development experience and should be updated as new patterns emerge.* 