# LightRAG Integrated WebUI Development Guide

This guide covers the setup and testing procedures for the integrated WebUI deployment architecture.

## 🏗️ **Architecture Overview**

```
Internet → Dynamic Public IP → Router → ProxMox → Ubuntu Docker Host → Traefik → LightRAG
                                                           ↓
                                                    Integrated WebUI
```

## 🔧 **Initial Setup Requirements**

### **1. Docker Network Setup**
```bash
# Create the proxy network for Traefik communication
docker network create proxy
```
**Status**: ✅ **Completed** (Network ID: 129a894f335a)

### **2. Host File Configuration (Local Testing)**
```bash
# Add to /etc/hosts for local testing
sudo nano /etc/hosts

# Add these lines:
127.0.0.1 homelab.localhost
127.0.0.1 traefik.localhost
```

### **3. Environment Configuration**
```bash
# Create .env.local for local testing
cat > .env.local << EOF
DOMAIN=localhost
LIGHTRAG_DOMAIN=homelab.localhost
ACME_EMAIL=admin@localhost
CORS_ORIGINS=https://homelab.localhost,http://homelab.localhost
EOF
```

## 🌐 **Production Domain Setup (flipgoal.xyz)**

### **Network Requirements**
- **Dynamic Public IP**: Your ISP-assigned IP (check with `curl ifconfig.me`)
- **Internal Ubuntu Docker Host**: Inside ProxMox (e.g., 192.168.x.x)
- **Router Port Forwarding**: 80,443 → Ubuntu Docker Host IP

### **DNS Configuration ✅ CONFIGURED**

Your DNS is already configured with CNAME records:
```bash
# Current DNS Setup:
homelab.flipgoal.xyz → vargohome.duckdns.org (LightRAG)
traefik.flipgoal.xyz → vargohome.duckdns.org (Traefik Dashboard)
n8n.flipgoal.xyz → vargohome.duckdns.org (n8n Automation)
bc_knowledgebase.flipgoal.xyz → vargohome.duckdns.org (Knowledge Base)
mesdevkb.flipgoal.xyz → vargohome.duckdns.org (MES Dev KB)
```

**Status**: ✅ DNS configured via CNAME → DuckDNS
**Pending**: Router port forwarding configuration

### **Router Configuration (Pending)**
```bash
# Port forwarding rules needed:
External Port 80 → Ubuntu Docker Host IP:80
External Port 443 → Ubuntu Docker Host IP:443
```

## 🧪 **Testing Procedures**

### **✅ Phase 1: COMPLETE - WebUI Integration**

**Status**: ✅ **Successfully completed**

All Phase 1 objectives achieved:
- ✅ **Development workflow preserved**: `docker compose --profile dev up -d` works perfectly
- ✅ **Production container validated**: Single container serves API + WebUI on port 9621  
- ✅ **Static asset serving**: WebUI assets serve correctly with `/webui/` base path
- ✅ **Multi-context support**: All environment variables and functionality preserved
- ✅ **Health monitoring**: Comprehensive `/health` endpoint operational

#### **Production Container Testing Results**
```bash
# ✅ VERIFIED: Production deployment works
docker compose --profile prod up -d

# ✅ VERIFIED: Health endpoint operational  
curl http://localhost:9621/health
# Returns: {"status":"healthy","webui_available":true,...}

# ✅ VERIFIED: WebUI integration complete
curl http://localhost:9621/webui/
# Returns: 200 OK - Complete WebUI served

# ✅ VERIFIED: Static assets loading correctly
curl http://localhost:9621/webui/assets/index-K-IL4uaq.css
# Returns: 200 OK - CSS assets served correctly
```

### **🔄 Phase 2: IN PROGRESS - Functional Testing**

**Current Focus**: Validate end-to-end functionality in integrated container

#### **Test Checklist**
- [ ] **Multi-Context Switching**: Test context switching in integrated container
- [ ] **Document Processing**: Upload, process, and query documents end-to-end
- [ ] **API Endpoint Validation**: Verify all REST API routes work correctly
- [ ] **Authentication Testing**: JWT token flow and admin:admin123 credentials
- [ ] **WebUI Functionality**: All WebUI features operational in production mode

### **📋 Phase 3: READY - Production Deployment**

**Prerequisites**: Router configuration for external access

#### **Deployment Validation**
- [ ] **Traefik Integration**: Test with homelab.flipgoal.xyz domain
- [ ] **External Access**: Full stack deployment in target environment  
- [ ] **Performance Testing**: Compare integrated vs separate service performance
- [ ] **Team Onboarding**: Validate external team member access

## 📋 **Development Profiles**

### **Development Profile (`--profile dev`)**
- **Purpose**: Maintains existing development workflow
- **Backend**: Docker container on 9621
- **Frontend**: Separate Vite dev server on 5173 (via npm run dev-no-bun)
- **Data**: Same volume mounts as current setup
- **Use**: Development and testing

### **Production Profile (`--profile prod`)**
- **Purpose**: Integrated single-container deployment
- **Backend**: FastAPI with static file serving
- **Frontend**: Built and served from `/webui/` route
- **Data**: Same volume mounts for compatibility
- **Use**: Homelab and production deployment

### **CI Profile (`--profile ci`)**
- **Purpose**: Build validation and testing
- **Use**: CI/CD pipelines and build verification

## 🔐 **Security Setup**

### **Secrets Generation**
```bash
# Generate production secrets
./scripts/setup-secrets.sh

# Files created (git-ignored):
# - secrets/token_secret (JWT secret)
# - secrets/api_key (API access key)
# - secrets/auth_users (bcrypt user hashes)
```

### **Security Files**
```bash
# Never commit to git:
secrets/
traefik/data/
.env.local
```

## 🚀 **Deployment Commands**

### **Local Testing**
```bash
# Development mode
docker compose --profile dev up -d

# Production mode (local)
docker compose --profile prod up -d

# With Traefik (local)
./scripts/deploy-homelab.sh
```

### **Homelab Deployment**
```bash
# Full production deployment (when router is configured)
DOMAIN=flipgoal.xyz LIGHTRAG_DOMAIN=homelab.flipgoal.xyz ./scripts/deploy-homelab.sh
```

## 🐛 **Troubleshooting**

### **Common Issues**

#### **Build Failures**
```bash
# Check Docker build logs
docker compose --profile ci build

# Common fix: npm dependency conflicts
# Solution: Uses --legacy-peer-deps in Dockerfile
```

#### **Network Issues**
```bash
# Verify proxy network exists
docker network ls | grep proxy

# Recreate if needed
docker network rm proxy
docker network create proxy
```

#### **Health Check Failures**
```bash
# Check container logs
docker compose --profile prod logs

# Verify health endpoint
curl http://localhost:9621/health
```

#### **Static Asset Issues**
```bash
# Verify WebUI build completed
ls -la lightrag_webui/dist/

# Check static files in container
docker exec -it lightrag-prod ls -la /app/static/
```

#### **Domain Access Issues (When Router Configured)**
```bash
# Test external domain access
curl -v https://homelab.flipgoal.xyz/health

# Check DNS resolution
nslookup homelab.flipgoal.xyz
nslookup vargohome.duckdns.org

# Verify external IP
curl ifconfig.me
```

## 📊 **Monitoring & Maintenance**

### **Useful Commands**
```bash
# View logs
docker compose --profile prod logs -f

# Restart services
docker compose --profile prod restart

# Update and rebuild
docker compose --profile prod down
docker compose --profile prod build
docker compose --profile prod up -d

# Cleanup
docker compose --profile prod down -v
```

### **Performance Monitoring**
```bash
# Container resource usage
docker stats

# Disk usage
du -sh data/

# Network connectivity (when router configured)
curl -v https://homelab.flipgoal.xyz/health
```

## 🔄 **Migration from Current Setup**

### **Current State**: `../lightrag-test` + `reload_server.sh`
### **New State**: Integrated container with profiles

### **Migration Steps**:
1. Test dev profile preserves workflow
2. Validate production container locally
3. Test with Traefik integration
4. Deploy to homelab (when router configured)
5. Update development workflow to use new profiles

### **Rollback Strategy**:
- Keep `../lightrag-test` until migration validated
- Use git branch management
- Current reload_server.sh remains functional

### **Production Access**:
- **Internal**: Continue using Tailscale for admin access
- **External**: `https://homelab.flipgoal.xyz` (when router configured)
- **Team Access**: Secure HTTPS with authentication

---

*This guide will be updated as we complete each testing phase.* 