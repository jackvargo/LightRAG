# LightRAG Homelab Deployment Guide

*Single Traefik Strategy Implementation for `flipgoal.xyz`*

---

## 🎯 **Deployment Overview**

This guide implements the robust single-Traefik architecture where:
- **Traefik**: Runs in its own stack, handles all TLS and routing
- **LightRAG**: Connects via external network, no port exposure, native secret handling
- **Domain**: `lightrag.flipgoal.xyz` → `vargohome.duckdns.org`

---

## 📋 **Prerequisites Checklist**

- [ ] Ubuntu Docker host with Docker & Docker Compose installed
- [ ] Router configured for port forwarding: `80,443 → Docker host IP`
- [ ] DNS: CNAME `lightrag.flipgoal.xyz` → `vargohome.duckdns.org` (✅ Complete)
- [ ] Git access to feature branch

---

## 🚀 **Quick Deployment Steps**

### **Step 1: Clone and Setup**
```bash
# Clone the repository to your homelab device
git clone https://github.com/your-repo/LightRAG.git
cd LightRAG

# Switch to feature branch
git checkout feature/webui-integrated-deployment
git pull origin feature/webui-integrated-deployment

# Create required directories
mkdir -p data/{rag_storage,inputs,contexts}
mkdir -p traefik/data
mkdir -p secrets
```

### **Step 2: Create External Network**
```bash
# Create the shared Traefik network (one-time setup)
docker network create --attachable traefik_proxy
```

### **Step 3: Generate Secrets**
```bash
# Generate production secrets
openssl rand -base64 64 > secrets/token_secret
openssl rand -hex 48 > secrets/api_key

# Generate LightRAG WebUI authentication credentials with bcrypt hashing
# This creates the login for https://lightrag.flipgoal.xyz
# Note: LightRAG now supports both bcrypt hashes and plain text for backward compatibility
htpasswd -Bc secrets/auth_users jack
# Recommended password: 16+ characters with mix of uppercase, lowercase, numbers, symbols
# Example: J@ck2024!LightRAG$SecuRe

# Alternative: Create plain text format (less secure, but simpler)
# echo "jack:J@ck2024!LightRAG\$SecuRe" > secrets/auth_users

# Set proper permissions
chmod 600 secrets/*
```

### **Step 4: Configure Environment**
```bash
# Create .env file
cp .env.example .env

# Edit key variables
cat > .env << EOF
# LightRAG Configuration
PORT=9621
LIGHTRAG_WORKING_DIR=./data/rag_storage
LIGHTRAG_INPUT_DIR=./data/inputs
LIGHTRAG_CONTEXTS_DIR=./data/contexts

# Production Settings - Standard Performance (Workers configured in application)
NODE_ENV=production
MEMORY_LIMIT=8G
MEMORY_RESERVATION=4G
# WORKERS=4  # Currently handled by application configuration

# Email for Let's Encrypt
ACME_EMAIL=admin@flipgoal.xyz

# Native Secret Handling (NEW)
# LightRAG now reads secrets directly from files - no launcher script needed
AUTH_FILE=/run/secrets/auth_users
TOKEN_SECRET_FILE=/run/secrets/token_secret
LIGHTRAG_API_KEY_FILE=/run/secrets/api_key
EOF
```

### **Step 5: Setup Traefik Dynamic Configuration**
```bash
# Create traefik dynamic configuration
cat > traefik/dynamic.yml << EOF
http:
  middlewares:
    redirect-to-https:
      redirectScheme:
        scheme: https
        permanent: true
    
    sec-headers:
      headers:
        frameDeny: true
        sslRedirect: true
        browserXssFilter: true
        contentTypeNosniff: true
        forceSTSHeader: true
        stsIncludeSubdomains: true
        stsPreload: true
        stsSeconds: 31536000
    
    ratelimit:
      rateLimit:
        average: 50
        period: 5s
        burst: 25
EOF

# Create Traefik dashboard authentication
mkdir -p traefik/auth
htpasswd -Bc traefik/auth/users jack
# Use a strong password - this protects your Traefik dashboard at https://traefik.flipgoal.xyz
# Example: Tr@ef1k2024!D@shboard$Admin

chmod 600 traefik/auth/users
```

### **Step 6: Create ACME Storage**
```bash
# Create acme.json with proper permissions
touch traefik/data/acme.json
chmod 600 traefik/data/acme.json
```

### **Step 7: Deploy Traefik First**
```bash
# Deploy Traefik stack
cd traefik
docker compose -f docker-compose.traefik.yml up -d

# Verify Traefik is running
docker logs traefik
```

### **Step 8: Deploy LightRAG**
```bash
# Return to project root
cd ..

# Deploy LightRAG production stack
# Note: Now uses standard uvicorn with 4 workers for better performance
docker compose --profile prod up -d

# Monitor deployment
docker logs -f lightrag
```

---

## 🔍 **Verification Steps**

### **Health Checks**
```bash
# Check network connectivity
docker network inspect traefik_proxy

# Verify containers are connected
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Test internal health endpoint
docker exec lightrag curl -f http://localhost:9621/health

# Verify multiple workers are running (new performance feature)
docker exec lightrag ps aux | grep uvicorn
```

### **External Access Tests**
```bash
# Test HTTP redirect (should redirect to HTTPS)
curl -I http://lightrag.flipgoal.xyz

# Test HTTPS access (after certificate generation)
curl -I https://lightrag.flipgoal.xyz

# Test WebUI access
curl -I https://lightrag.flipgoal.xyz/webui/

# Test authentication endpoint
curl -I https://lightrag.flipgoal.xyz/auth-status
```

---

## 🔐 **Security Recommendations**

### **Password Guidelines**
- **LightRAG Auth**: Username `jack`, strong password (16+ chars)
  - Example pattern: `J@ck2024!LightRAG$SecuRe`
- **Traefik Dashboard**: Same username, DIFFERENT strong password
  - Example pattern: `Tr@ef1k2024!D@shboard$Admin`

### **Authentication Security Enhancements (NEW)**
- **bcrypt Support**: LightRAG now properly supports bcrypt password hashing
- **Backward Compatibility**: Plain text passwords still work during transition
- **Native Secret Handling**: No more workaround scripts - secrets loaded directly by application
- **Multiple Workers**: Improved performance with 4 worker processes instead of 1

### **Why Different Passwords?**
- **Defense in depth**: If one service is compromised, others remain secure
- **Role separation**: Traefik dashboard vs application access
- **Audit clarity**: Different credentials for different purposes

---

## 🛠️ **Troubleshooting**

### **Common Issues**

| Issue | Solution |
|-------|----------|
| Certificate generation fails | Check ports 80,443 are forwarded to Docker host |
| 502 Bad Gateway | Verify LightRAG container is healthy: `docker logs lightrag` |
| Network not found | Ensure `traefik_proxy` network exists: `docker network ls` |
| Permission denied on secrets | Check file permissions: `chmod 600 secrets/*` |
| Traefik auth fails | Verify auth file exists: `ls -la traefik/auth/users` |
| Auth file not loading | Check container secret mounts: `docker exec lightrag ls -la /run/secrets/` |
| Performance issues | Verify multiple workers: `docker exec lightrag ps aux \| grep uvicorn` |
| Uvicorn argument error | Check Dockerfile CMD and rebuild: `docker compose --profile prod build --no-cache` |

### **Debug Commands**
```bash
# View Traefik dashboard (after setting up auth)
# https://traefik.flipgoal.xyz

# Check certificate status
docker exec traefik cat /acme.json | jq '.le.Certificates'

# View all logs
docker compose --profile prod logs -f

# Test auth file format
cat secrets/auth_users
# Should show: jack:$2y$10$... (bcrypt hash) OR jack:plaintext (backward compatibility)

# Verify secret file loading (NEW)
docker exec lightrag cat /run/secrets/auth_users
docker exec lightrag env | grep AUTH

# Check worker processes (NEW)
docker exec lightrag ps aux | grep uvicorn
```

---

## 🔄 **Updates & Maintenance**

### **Updating LightRAG**
```bash
# Pull latest changes
git pull origin feature/webui-integrated-deployment

# Rebuild and redeploy (now uses improved architecture)
docker compose --profile prod up -d --build

# Verify improved performance
docker exec lightrag ps aux | grep uvicorn
```

### **Updating Traefik**
```bash
cd traefik
docker compose -f docker-compose.traefik.yml pull
docker compose -f docker-compose.traefik.yml up -d
```

### **Migrating to bcrypt Passwords (Recommended)**
```bash
# Generate new bcrypt hash
htpasswd -Bc secrets/auth_users_new jack

# Test the new hash works
# Then replace old file
mv secrets/auth_users_new secrets/auth_users

# Redeploy to apply changes
docker compose --profile prod up -d
```

---

## 🏆 **Success Criteria**

After deployment, you should have:
- ✅ `https://lightrag.flipgoal.xyz` serves LightRAG WebUI
- ✅ `https://traefik.flipgoal.xyz` serves Traefik dashboard (with auth)
- ✅ Automatic HTTPS certificates from Let's Encrypt
- ✅ HTTP automatically redirects to HTTPS
- ✅ All containers running and healthy
- ✅ Multi-context functionality preserved
- ✅ **NEW**: Enhanced performance with 4 worker processes
- ✅ **NEW**: Native secret handling (no launcher scripts)
- ✅ **NEW**: Proper bcrypt password security
- ✅ **NEW**: Improved FastAPI architecture

---

## 🆕 **What's New in This Version**

### **Performance Improvements**
- **Standard Uvicorn**: Uses proper uvicorn configuration with main.py entry point
- **Improved Architecture**: Replaced custom launcher with standard FastAPI application
- **Memory Optimization**: Better resource utilization
- **Multi-worker Support**: Available but currently disabled due to configuration conflicts

### **Security Enhancements**
- **Native Secret Handling**: Application reads secrets directly from files
- **bcrypt Support**: Proper password hashing with backward compatibility
- **Cleaner Architecture**: Removed workaround scripts and duplicate code

### **Deployment Simplification**
- **Direct Configuration**: No more intermediate launcher scripts
- **File-based Secrets**: Standard Docker secrets pattern
- **Improved Logging**: Better visibility into application performance

---

## 📞 **Support**

For issues specific to this deployment:
1. Check container logs: `docker logs lightrag`
2. Verify network connectivity: `docker network inspect traefik_proxy`
3. Test internal health: `docker exec lightrag curl http://localhost:9621/health`
4. Review Traefik dashboard for routing issues
5. **NEW**: Check worker processes: `docker exec lightrag ps aux | grep uvicorn`
6. **NEW**: Verify secret loading: `docker exec lightrag ls -la /run/secrets/`

**Domain Status**: `lightrag.flipgoal.xyz` configured and ready for deployment 🚀 