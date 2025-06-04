# LightRAG Homelab Deployment Guide

*Single Traefik Strategy Implementation for `flipgoal.xyz`*

---

## 🎯 **Deployment Overview**

This guide implements the robust single-Traefik architecture where:
- **Traefik**: Runs in its own stack, handles all TLS and routing
- **LightRAG**: Connects via external network, no port exposure
- **Domain**: `homelab.flipgoal.xyz` → `vargohome.duckdns.org`

---

## 📋 **Prerequisites Checklist**

- [ ] Ubuntu Docker host with Docker & Docker Compose installed
- [ ] Router configured for port forwarding: `80,443 → Docker host IP`
- [ ] DNS: CNAME `homelab.flipgoal.xyz` → `vargohome.duckdns.org` (✅ Complete)
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
htpasswd -Bbn admin > secrets/auth_users  # Enter password when prompted
openssl rand -hex 48 > secrets/api_key

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

# Production Settings
NODE_ENV=production
MEMORY_LIMIT=8G
MEMORY_RESERVATION=4G

# Email for Let's Encrypt
ACME_EMAIL=admin@flipgoal.xyz
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
    
    redirect-https:
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
    
    auth:
      basicAuth:
        usersFile: /etc/traefik/users  # You'll need to create this
EOF

# Create basic auth file for Traefik dashboard
htpasswd -Bbn admin > traefik/users  # Enter dashboard password
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
docker compose --profile prod up -d

# Monitor deployment
docker logs -f lightrag-prod
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
docker exec lightrag-prod curl -f http://localhost:9621/health
```

### **External Access Tests**
```bash
# Test HTTP redirect (should redirect to HTTPS)
curl -I http://homelab.flipgoal.xyz

# Test HTTPS access (after certificate generation)
curl -I https://homelab.flipgoal.xyz

# Test WebUI access
curl -I https://homelab.flipgoal.xyz/webui/
```

---

## 🛠️ **Troubleshooting**

### **Common Issues**

| Issue | Solution |
|-------|----------|
| Certificate generation fails | Check ports 80,443 are forwarded to Docker host |
| 502 Bad Gateway | Verify LightRAG container is healthy: `docker logs lightrag-prod` |
| Network not found | Ensure `traefik_proxy` network exists: `docker network ls` |
| Permission denied on secrets | Check file permissions: `chmod 600 secrets/*` |

### **Debug Commands**
```bash
# View Traefik dashboard (after setting up auth)
# https://traefik.flipgoal.xyz

# Check certificate status
docker exec traefik cat /acme.json | jq '.le.Certificates'

# View all logs
docker compose --profile prod logs -f
```

---

## 🔄 **Updates & Maintenance**

### **Updating LightRAG**
```bash
# Pull latest changes
git pull origin feature/webui-integrated-deployment

# Rebuild and redeploy
docker compose --profile prod up -d --build
```

### **Updating Traefik**
```bash
cd traefik
docker compose -f docker-compose.traefik.yml pull
docker compose -f docker-compose.traefik.yml up -d
```

---

## 🏆 **Success Criteria**

After deployment, you should have:
- ✅ `https://homelab.flipgoal.xyz` serves LightRAG WebUI
- ✅ `https://traefik.flipgoal.xyz` serves Traefik dashboard (with auth)
- ✅ Automatic HTTPS certificates from Let's Encrypt
- ✅ HTTP automatically redirects to HTTPS
- ✅ All containers running and healthy
- ✅ Multi-context functionality preserved

---

## 📞 **Support**

For issues specific to this deployment:
1. Check container logs: `docker logs <container-name>`
2. Verify network connectivity: `docker network inspect traefik_proxy`
3. Test internal health: `docker exec lightrag-prod curl http://localhost:9621/health`
4. Review Traefik dashboard for routing issues

**Domain Status**: `homelab.flipgoal.xyz` configured and ready for deployment 🚀 