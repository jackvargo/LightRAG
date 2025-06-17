# Development Management for PR Plan

## 🚀 **Quick Reference - Immediate Implementation**

### **Current Status Check**
```bash
# You are here: feat-multicontext branch with committed cursor rules ✅
git branch                 # Confirm you're on feat-multicontext
git status                 # Check current state
```

### **Immediate Next Steps**
```bash
# 1. Clean up current changes and organize development files
git add aidevdocs/ docs/development/
git commit -m "organize: consolidate development documentation"

# 2. When ready for PR - create clean branch
git checkout -b feat-multicontext-pr
git rm -r .cursor/ aidevdocs/ docs/development/
git rm -f .DS_Store
git commit -m "prepare: clean branch for upstream PR"

# 3. Continue development on original branch
git checkout feat-multicontext
```

## 🎯 **Strategy Overview: Development Branch Management**

This document outlines the strategy for managing development-specific files and configurations while maintaining clean, professional PRs for upstream contributions.

### **Approach: Option 3 - Development Branch Strategy**
- **Keep development tools on feature branches**
- **Create clean PR branches without development artifacts**
- **Maintain development environment in version control for safety**
- **Clean merge path back to main branch**

---

## 📋 **File and Folder Exclusion Strategy**

### **Development-Specific Content (Keep on Dev Branches)**

#### **Primary Exclusions for PR Branches:**
```bash
# IDE and development environment
.cursor/                    # Cursor AI assistant rules and configurations
.cursor/rules/             # Development environment rules

# Development documentation
aidevdocs/                 # AI development documentation and screenshots
docs/development/          # Development-specific guides and workflows

# Development artifacts
*.DS_Store                 # macOS system files
.dev-config/              # Development configuration (if using external repo)
dev-tools/                # Development helper scripts (if separate)
```

#### **Additional Exclusions:**
```bash
# Personal development files
.vscode/settings.json      # Personal VS Code settings
.idea/workspace.xml        # Personal IntelliJ settings
*.local.env               # Personal environment variables
*-local.*                 # Any local configuration files
```

---

## 🔄 **Branch Management Workflow**

### **Phase 1: Development Branch (feat-multicontext)**
```bash
# Current working branch with all development tools
git checkout feat-multicontext

# Development files are committed and tracked:
✅ .cursor/rules/
✅ aidevdocs/
✅ docs/development/
✅ All development artifacts
```

**Purpose:**
- Safe version control of development environment
- Collaboration with other developers on the feature
- Iterative improvement of development tools
- Backup and history of development practices

### **Phase 2: Clean PR Branch Creation**
```bash
# Create clean branch for upstream PR
git checkout feat-multicontext
git checkout -b feat-multicontext-pr

# Remove development-specific content
git rm -r .cursor/
git rm -r aidevdocs/
git rm -r docs/development/
git rm .DS_Store

# Commit the clean state
git commit -m "prepare: remove development-specific files for upstream PR

- Remove .cursor/ directory (IDE-specific configuration)
- Remove aidevdocs/ directory (development documentation)
- Remove docs/development/ directory (dev environment guides)
- Clean branch ready for upstream contribution"

# Push clean PR branch
git push origin feat-multicontext-pr
```

**Purpose:**
- Professional, focused contribution
- No IDE-specific clutter for maintainers
- Clean diff showing only code changes
- Respects upstream repository conventions

### **Phase 3: PR Creation and Management**
```bash
# Create PR from clean branch
gh pr create --base main --head feat-multicontext-pr \
  --title "feat: implement multi-context support" \
  --body "$(cat PR_DESCRIPTION.md)"

# Continue development on main branch
git checkout feat-multicontext
# All development tools remain available
```

**Purpose:**
- Upstream PR contains only relevant code changes
- Development continues uninterrupted
- Easy to incorporate PR feedback

---

## 🔀 **Merge Strategy: Development Branch to Main**

### **Option A: Selective Merge (Recommended)**
```bash
# After PR is accepted upstream
git checkout main
git pull upstream main

# Cherry-pick only code changes from development branch
git checkout feat-multicontext

# Create final clean commit for main branch
git checkout main
git checkout -b integrate-multicontext-clean

# Manual selective merge of code changes only
cp -r lightrag/ ../temp-lightrag/
cp -r lightrag_webui/ ../temp-lightrag_webui/
cp reload_server.sh ../temp-reload_server.sh

# Verify only code changes are included
git add lightrag/ lightrag_webui/ reload_server.sh
git commit -m "feat: integrate multi-context support from upstream PR"

# Merge to main
git checkout main
git merge integrate-multicontext-clean
git branch -d integrate-multicontext-clean
```

### **Option B: Development Branch Maintenance**
```bash
# Keep development branch active for future work
git checkout feat-multicontext
git merge main  # Incorporate upstream changes
git push origin feat-multicontext

# Development environment remains intact for next feature
```

---

## 📁 **Repository Structure Post-Merge**

### **Main Branch (Clean Production)**
```
LightRAG/
├── lightrag/              # Core code only
├── lightrag_webui/        # Frontend code only
├── reload_server.sh       # Essential scripts only
├── docs/                  # User-facing documentation only
│   ├── api/
│   └── README.md
└── README.md             # Project documentation
```

### **Development Branch (Full Environment)**
```
LightRAG/
├── lightrag/              # Core code
├── lightrag_webui/        # Frontend code
├── reload_server.sh       # Essential scripts
├── .cursor/               # Development environment
│   └── rules/
├── aidevdocs/             # Development documentation
│   ├── context-switching-remediation-plan.md
│   ├── merge-webui-deploy-hardening-plan.md
│   └── screenshots/
├── docs/                  # All documentation
│   ├── development/       # Dev-specific guides
│   ├── api/
│   └── README.md
└── README.md
```

---

## ⚡ **Development Workflow Integration**

### **Daily Development Process**
```bash
# Always work on development branch
git checkout feat-multicontext

# Use all development tools normally
./reload_server.sh
# Cursor rules are active
# Development documentation is accessible
# Full development environment available

# Regular commits include development improvements
git add .cursor/rules/development-environemt-management.mdc
git commit -m "improve: update context switching debug procedures"
```

### **PR Update Process**
```bash
# When PR needs updates
git checkout feat-multicontext
# Make code changes with full development environment

# Update clean PR branch
git checkout feat-multicontext-pr
git merge feat-multicontext
git rm -r .cursor/ aidevdocs/ docs/development/ || true
git commit -m "update: incorporate latest changes, maintain clean PR state"
git push origin feat-multicontext-pr
```

---

## 🎯 **Benefits of This Strategy**

### **✅ Development Benefits**
- **Safe Environment**: Development tools are version controlled
- **Team Collaboration**: Other developers can use the same environment
- **Iterative Improvement**: Development practices improve over time
- **No Data Loss**: Everything is backed up in git

### **✅ PR Benefits**
- **Professional Appearance**: Clean, focused contributions
- **Maintainer Friendly**: No irrelevant files to review
- **Clear Intent**: Obvious what the contribution adds
- **Upstream Standards**: Respects repository conventions

### **✅ Maintenance Benefits**
- **Clean Main Branch**: Production code only
- **Flexible Development**: Rich development environment available
- **Easy Updates**: Simple process to update PRs
- **Scalable Pattern**: Applies to future features

---

## 🚨 **Important Considerations**

### **Security**
- Review development files before committing (no secrets)
- Personal API keys should never be in development configs
- Use environment variables for sensitive data

### **Team Coordination**
- Document which branch teammates should use for collaboration
- Establish conventions for development branch naming
- Consider shared development environment standards

### **Upstream Relationship**
- Monitor upstream changes that might conflict with development setup
- Be prepared to rebase development branch on upstream main
- Keep development tooling updated with project evolution

---

## 🔄 **Upstream Sync Strategy: Preserving Dev Relics**

Managing upstream changes while maintaining your development environment is critical for long-running feature branches. This section covers safe practices for staying current with upstream while preserving your development artifacts.

### **🎯 Sync Timing Strategy**

#### **When to Sync with Upstream**
```bash
# Regular sync schedule (recommended)
- Weekly: Check for upstream changes
- Before major development milestones
- Before creating/updating PR branches
- When upstream releases new versions
- When conflicts are likely (active development areas)
```

#### **Pre-Sync Safety Checklist**
```bash
# 1. Ensure development branch is clean
git status                    # Should show clean working directory
git add . && git commit -m "wip: save current work before upstream sync"

# 2. Backup current development state
git tag backup-dev-$(date +%Y%m%d-%H%M%S) feat-multicontext

# 3. Verify all development artifacts are committed
git ls-files .cursor/ aidevdocs/ docs/development/ | wc -l
```

---

### **🔄 Upstream Integration Process**

#### **Step 1: Fetch Latest Upstream**
```bash
# Ensure upstream remote is configured
git remote -v | grep upstream || git remote add upstream https://github.com/HKUDS/LightRAG.git

# Fetch all upstream changes
git fetch upstream
git fetch upstream --tags

# Review what's changed
git log --oneline feat-multicontext..upstream/main
git diff feat-multicontext upstream/main --stat
```

#### **Step 2: Safe Development Branch Update**
```bash
# Create integration branch for safety
git checkout feat-multicontext
git checkout -b integrate-upstream-$(date +%Y%m%d)

# Merge upstream changes
git merge upstream/main

# Alternative: Rebase for cleaner history (advanced)
# git rebase upstream/main
```

#### **Step 3: Conflict Resolution Strategy**
```bash
# During merge conflicts, prioritize preservation of dev artifacts

# Common conflict scenarios:
# 1. Core code conflicts (merge normally)
git add lightrag/ lightrag_webui/
git commit

# 2. Documentation conflicts (preserve both, merge manually)
# Keep upstream docs for users, your dev docs for development
git checkout --ours docs/development/
git checkout --theirs docs/README.md
git add docs/

# 3. Configuration conflicts (preserve your development setup)
git checkout --ours .cursor/
git checkout --ours aidevdocs/
git add .cursor/ aidevdocs/

# Complete the merge
git commit -m "merge: integrate upstream changes while preserving development environment"
```

---

### **🛡️ Development Artifact Protection**

#### **Critical Files to Always Preserve**
```bash
# These should NEVER be overwritten by upstream
.cursor/                      # Your development environment
aidevdocs/                    # Your development documentation
docs/development/             # Your development guides
*-local.*                     # Personal configuration files
dev-backup-*/                 # Any backup directories
```

#### **Merge Strategy for Development Files**
```bash
# If upstream introduces conflicting development files:

# 1. Rename upstream version for reference
git mv docs/development/ docs/development-upstream/

# 2. Restore your development environment
git checkout HEAD~1 -- docs/development/

# 3. Review and selectively integrate useful upstream practices
diff -r docs/development/ docs/development-upstream/

# 4. Commit the resolution
git add docs/
git commit -m "preserve: maintain custom development environment while archiving upstream version"
```

---

### **🔄 Post-Sync Verification**

#### **Development Environment Health Check**
```bash
# 1. Verify development tools still work
./reload_server.sh --build    # Test full rebuild
./reload_server.sh            # Test quick reload

# 2. Verify cursor rules are intact
ls -la .cursor/rules/
cat .cursor/rules/development-environemt-management.mdc | head -5

# 3. Test development workflows
npm run dev-no-bun           # Test WebUI development
docker compose logs | head -10   # Test backend integration

# 4. Verify documentation is accessible
ls -la aidevdocs/
ls -la docs/development/
```

#### **Integration Testing**
```bash
# Test that new upstream features work with your development setup
cd lightrag_webui && npm run build
./reload_server.sh --restart
# Test multi-context functionality with upstream changes
```

---

### **🔄 Clean PR Branch Updates**

#### **Updating PR Branch After Upstream Sync**
```bash
# Your development branch now has upstream changes
git checkout feat-multicontext

# Update your clean PR branch
git checkout feat-multicontext-pr
git reset --hard feat-multicontext

# Remove development artifacts (they may have been restored during merge)
git rm -r .cursor/ aidevdocs/ docs/development/ || true
git rm -f .DS_Store *.local.* || true

# Commit clean state
git commit -m "sync: update PR branch with latest upstream changes

- Incorporates upstream changes from main branch
- Maintains clean PR state without development artifacts
- Ready for upstream review"

# Force push to update remote PR branch
git push origin feat-multicontext-pr --force-with-lease
```

---

### **🚨 Emergency Recovery Procedures**

#### **If Upstream Sync Goes Wrong**
```bash
# 1. Restore from backup tag
git tag | grep backup-dev
git reset --hard backup-dev-YYYYMMDD-HHMMSS

# 2. Alternative: Cherry-pick specific upstream commits
git log upstream/main --oneline | head -10
git cherry-pick <specific-commit-hash>

# 3. Nuclear option: Restart integration process
git checkout feat-multicontext
git branch -D integrate-upstream-YYYYMMDD
# Start over with fresh integration branch
```

#### **Development Artifact Recovery**
```bash
# If development files were accidentally overwritten
git reflog | grep "development"
git checkout <reflog-entry> -- .cursor/ aidevdocs/ docs/development/
git commit -m "recover: restore development environment from reflog"
```

---

### **📅 Long-Term Maintenance Strategy**

#### **Monthly Development Branch Hygiene**
```bash
# 1. Clean up old integration branches
git branch | grep integrate-upstream | head -5
git branch -D integrate-upstream-old-date

# 2. Update development documentation
git add aidevdocs/
git commit -m "docs: update development procedures based on recent experience"

# 3. Review and update cursor rules
git add .cursor/rules/
git commit -m "improve: update development environment based on upstream changes"
```

#### **Development Environment Evolution**
```bash
# As upstream evolves, your development environment should too
# Document lessons learned in:
# - aidevdocs/upstream-integration-notes.md
# - docs/development/environment-setup.md
# - .cursor/rules/development-environemt-management.mdc
```

---

### **🎯 Benefits of This Upstream Strategy**

**✅ **Safe Integration**
- Development artifacts are protected during merges
- Backup tags provide easy recovery points
- Conflicts are resolved with development preservation priority

**✅ **Current with Upstream**
- Regular sync prevents large, difficult merges
- Clean PR branches stay current automatically
- Integration issues are caught early

**✅ **Development Continuity**
- No disruption to daily development workflow
- Cursor rules and development docs remain intact
- Team development environment stays consistent

**✅ **Professional PR Management**
- Clean PR branches automatically updated with upstream changes
- Clear history of what changed and why
- Easy to rebase or update PRs as needed

---

## 📚 **Related Documentation**

- **[Context Switching Remediation Plan](./context-switching-remediation-plan.md)** - Technical implementation details
- **[Development Environment Setup](../docs/development/environment-setup.md)** - Setup procedures
- **[Workflow Scripts Documentation](../docs/development/workflow-scripts.md)** - Script usage and patterns

---

*This plan ensures clean upstream contributions while maintaining a rich, safe development environment for ongoing work.*
