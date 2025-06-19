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

# Production Settings - Enhanced Performance with Gunicorn Multi-Worker
NODE_ENV=production
MEMORY_LIMIT=8G
MEMORY_RESERVATION=4G
WORKERS=4

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
# Note: Now uses Gunicorn with 4 workers for better production performance
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
docker exec lightrag ps aux | grep gunicorn
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
| Performance issues | Verify multiple workers: `docker exec lightrag ps aux \| grep gunicorn` |
| Worker process issues | Check Gunicorn master/worker processes: `docker exec lightrag ps aux` |
| WebUI 404 errors | Verify static files mounted: `docker exec lightrag ls -la /app/static/` |

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
docker exec lightrag ps aux | grep gunicorn

# Verify WebUI static files (NEW)
docker exec lightrag ls -la /app/static/
docker exec lightrag curl -I http://localhost:9621/webui/

# Debug authentication issues (NEW)
docker exec lightrag env | grep AUTH
docker exec lightrag cat /run/secrets/auth_users
docker exec lightrag python -c "from lightrag.api.auth import auth_handler; print('Accounts loaded:', bool(auth_handler.accounts)); print('Account details:', list(auth_handler.accounts.keys()) if auth_handler.accounts else 'None')"

# Test bcrypt hash verification (NEW)
docker exec lightrag python -c "
from passlib.context import CryptContext
import sys
print('Python version:', sys.version)

# Read and analyze the hash
hash_from_file = open('/run/secrets/auth_users').read().split(':')[1].strip()
print('Hash from file:', repr(hash_from_file))  # Use repr to see hidden characters
print('Hash length:', len(hash_from_file))
print('First 4 chars:', repr(hash_from_file[:4]))

# Test format detection step by step
valid_prefixes = ('$2a$', '$2b$', '$2x$', '$2y$')
print('Valid prefixes:', valid_prefixes)
for prefix in valid_prefixes:
    if hash_from_file.startswith(prefix):
        print(f'Hash starts with {prefix}: True')
        break
else:
    print('Hash does not start with any valid prefix')

# Test bcrypt directly without passlib first
try:
    import bcrypt
    print('bcrypt library available')
    print('bcrypt version:', getattr(bcrypt, '__version__', 'unknown'))
    
    # Test with bcrypt directly
    test_password = b'your_test_password'
    hash_bytes = hash_from_file.encode('utf-8')
    result = bcrypt.checkpw(test_password, hash_bytes)
    print('Direct bcrypt verification:', result)
except Exception as e:
    print('Direct bcrypt error:', str(e))

# Test with passlib
try:
    pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')
    result = pwd_context.verify('your_test_password', hash_from_file)
    print('Passlib verification result:', result)
except Exception as e:
    print('Passlib verification error:', str(e))
"

### **Quick Fix for bcrypt Authentication Issues**

**The `htpasswd -Bc` command SHOULD work perfectly!** If it's not working, there's a bug that needs debugging.

**Standard htpasswd approach (SHOULD work):**
```bash
# This is the correct and simple way to generate bcrypt hashes
htpasswd -Bc secrets/auth_users jack

# Redeploy
docker compose --profile prod up -d
```

**If htpasswd -Bc doesn't work, debug with:**
```bash
# Check what htpasswd actually generated
cat secrets/auth_users
# Should show: jack:$2y$12$... (this IS a valid bcrypt hash)

# Enable debug logging to see what's happening
docker compose --profile prod logs -f | grep -E "(Auth attempt|Hash from storage|Is bcrypt|verification)"

# Test the exact hash htpasswd generated
docker exec lightrag python -c "
hash_line = open('/run/secrets/auth_users').read().strip()
username, hash_value = hash_line.split(':', 1)
print(f'Username: {username}')
print(f'Hash: {repr(hash_value)}')
print(f'Hash starts with: {repr(hash_value[:4])}')
print(f'Is valid bcrypt format: {hash_value.startswith((\"\$2a\$\", \"\$2b\$\", \"\$2x\$\", \"\$2y\$\"))}')
"
```

**Only if htpasswd continues to fail, use alternatives:**

```bash
# Option 1: Force regenerate hash with Python (compatible format)
docker exec lightrag python -c "
import bcrypt
password = b'your_actual_password'  # Replace with your real password
salt = bcrypt.gensalt()
hash_bytes = bcrypt.hashpw(password, salt)
hash_str = hash_bytes.decode('utf-8')
print(f'jack:{hash_str}')
" > secrets/auth_users

# Option 2: Use plain text temporarily (less secure but works)
echo "jack:your_plain_password" > secrets/auth_users

# Redeploy after either fix
docker compose --profile prod up -d
```

### **Known Harmless Warnings**

You may see this warning in the logs - **it's completely harmless and doesn't affect functionality**:
```
[WARNING] passlib.handlers.bcrypt: (trapped) error reading bcrypt version
```

This is just a version compatibility issue between passlib and bcrypt libraries. The authentication works perfectly despite this warning.

---

## 🔄 **Updates & Maintenance**

### **Updating LightRAG**
```bash
# Pull latest changes
git pull origin feature/webui-integrated-deployment

# Rebuild and redeploy (now uses improved architecture)
docker compose --profile prod up -d --build

# Verify improved performance
docker exec lightrag ps aux | grep gunicorn
```

### **Updating Traefik**
```bash
cd traefik
docker compose -f docker-compose.traefik.yml pull
docker compose -f docker-compose.traefik.yml up -d
```

### **Migrating to bcrypt Passwords (Recommended)**
```bash
# Generate new bcrypt hash (ensure compatibility)
htpasswd -Bc secrets/auth_users_new jack
# Or use Python to generate hash
python3 -c "
from passlib.context import CryptContext
import getpass
pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')
password = getpass.getpass('Enter password: ')
hash_value = pwd_context.hash(password)
print(f'jack:{hash_value}')
" > secrets/auth_users_new

# Test the new hash works before applying
docker exec lightrag python -c "
from passlib.context import CryptContext
pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')
# Test with your actual password
test_result = pwd_context.verify('your_actual_password', 'your_generated_hash')
print('Hash verification test:', test_result)
"

# If test passes, replace old file
mv secrets/auth_users_new secrets/auth_users

# Redeploy to apply changes
docker compose --profile prod up -d
```

### **Troubleshooting bcrypt Authentication**
```bash
# If bcrypt authentication fails:

# 1. Check hash format
cat secrets/auth_users
# Should show: jack:$2b$12$... (or $2a$, $2x$, $2y$)

# 2. Test hash manually
docker exec lightrag python -c "
from passlib.context import CryptContext
pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')
# Replace with your actual values
result = pwd_context.verify('your_password', 'your_hash')
print('Manual verification:', result)
"

# 3. Temporarily use plain text for testing
echo 'jack:your_plain_password' > secrets/auth_users
docker compose --profile prod up -d
# If this works, the issue is with bcrypt hash generation/verification
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
- ✅ **NEW**: Production Gunicorn deployment

---

## 🆕 **What's New in This Version**

### **Performance Improvements**
- **4 Worker Processes**: Better concurrent request handling with Gunicorn
- **Production WSGI Server**: Uses Gunicorn instead of development uvicorn
- **Shared Data Architecture**: Optimized for multi-process deployment
- **Memory Optimization**: Better resource utilization across workers

### **Security Enhancements**
- **Native Secret Handling**: Application reads secrets directly from files
- **bcrypt Support**: Proper password hashing with backward compatibility
- **Cleaner Architecture**: Removed workaround scripts and duplicate code

### **Deployment Simplification**
- **Direct Configuration**: No more intermediate launcher scripts
- **File-based Secrets**: Standard Docker secrets pattern
- **Improved Logging**: Better visibility into application performance
- **Fixed WebUI Serving**: Corrected static file mounting logic for production mode

---

## 📞 **Support**

For issues specific to this deployment:
1. Check container logs: `docker logs lightrag`