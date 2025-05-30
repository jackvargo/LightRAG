# LightRAG WebUI Integration & Deployment Hardening Plan

*Updated with production-ready architecture and security best practices*

---

## 1 Current-State Snapshot

### 1.1 Architecture Friction Points

| Issue | Impact |
| --- | --- |
| Two running services (FastAPI 9621 + Vite 5173) | Extra port plumbing, harder SSL off-load |
| UI build coupled to **npm run dev-no-bun** | Dev onboarding friction |
| No readiness/health probes | Traefik may keep sending traffic to a dead pod |
| Static assets only via dev server | Production image must ship them itself |

---

## 2 Target Topology (Homelab Pre-Prod)

```
Internet ─▶ Traefik (v3.3, :443)
                └▶ LightRAG (container :9621 HTTP)
Tailscale side-car ───────────────────┘

```

- Traefik handles **TLS, rate-limit, CSP, HSTS**.
- LightRAG runs one process (Uvicorn) and serves **API + pre-built SPA**.
- Tailscale side-car receives a dedicated `tailscale` network; the backend never exposes host ports directly.

---

## 3 Build & Release Flow

```
┌────────────┐    (CI profile)        (prod profile)
│  UI build  │──▶ artifact.zip ─┐  ┌───────────┐
│ (Node 20)  │                  ├──│  docker   │─▶ registry
└────────────┘                  │  │  build    │
   npm ci && vite build         │  │ (multi-)  │
                                │  └───────────┘
                                ▼
                       COPY --from=ui-builder /dist /app/static

```

### 3.1 Dockerfile (highlights)

```dockerfile
ARG BUILD_ENV=production
FROM node:20-alpine AS ui-builder
WORKDIR /ui
COPY lightrag_webui/ .
RUN npm ci && npm run build

FROM python:3.12-slim
WORKDIR /app
COPY --from=ui-builder /ui/dist /app/static
COPY . .
RUN pip install -r requirements.txt
HEALTHCHECK CMD curl -f http://localhost:9621/health || exit 1
CMD ["uvicorn","lightrag.api.main:app","--host","0.0.0.0","--port","9621"]
```

---

## 4 FastAPI Changes

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

app = FastAPI()
app.mount("/webui", StaticFiles(directory="static", html=True), name="static")

@app.get("/webui/{_:path}")
async def spa_fallback():
    return FileResponse("static/index.html")
```

---

## 5 Traefik v3.3 Compose Configuration

```yaml
services:
  traefik:
    image: traefik:v3.3
    command:
      - --providers.docker=true
      - --entrypoints.websecure.address=:443
      - --certificatesresolvers.le.acme.email=${ACME_EMAIL}
      - --certificatesresolvers.le.acme.tlschallenge=true
    ports: ['443:443']
    networks: [proxy]
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - ./data/acme.json:/acme.json
  lightrag:
    build:
      context: .
      target: prod
    environment:
      - CORS_ORIGINS=https://lightrag.example.com
      - TOKEN_SECRET_FILE=/run/secrets/token_secret
    secrets:
      - token_secret
    labels:
      - traefik.enable=true
      - traefik.http.routers.lightrag.rule=Host(`lightrag.example.com`)
      - traefik.http.routers.lightrag.entrypoints=websecure
      - traefik.http.routers.lightrag.tls.certresolver=le
      - traefik.http.routers.lightrag.middlewares=redirect-https@file,sec-headers@file,ratelimit@file
      - traefik.http.services.lightrag.loadbalancer.server.port=9621
networks:
  proxy: {external: true}
secrets:
  token_secret:
    file: ./secrets/token_secret
```

**Middlewares in `traefik/dynamic.yml`** add CSP, HSTS, and `ratelimit` (50 req / 5 s).

---

## 6 Environment & Secrets Management

### 6.1 Environment Configuration
```bash
# JWT / Auth
TOKEN_SECRET_FILE=/run/secrets/token_secret
AUTH_FILE=/run/secrets/auth_users   # bcrypt hashes
# API key
LIGHTRAG_API_KEY_FILE=/run/secrets/api_key
```

### 6.2 Secrets Generation
Generate secrets once:

```bash
openssl rand -base64 64 > secrets/token_secret
htpasswd -Bbn admin > secrets/auth_users
openssl rand -hex 48 > secrets/api_key
```

### 6.3 Security Best Practices

#### Password Policy
- **Minimum length**: 12 characters
- **Complexity**: Mix of uppercase, lowercase, numbers, symbols
- **Storage**: bcrypt hashed in Docker secrets
- **Rotation**: Every 90 days for homelab

#### Token Management
- **JWT tokens**: 8 hours for admin, 24 hours for team members
- **API keys**: 64-character random hex
- **Storage**: Docker secrets, never in environment variables
- **Rotation**: Monthly for homelab environment

---

## 7 Compose Profiles

```yaml
profiles: ["dev", "ci", "prod"]
```

- **dev** – FastAPI + vite hot-reload (maintains current workflow)
- **ci** – Build images, run unit-tests, produce SBOM (`trivy sbom`)
- **prod** – All-in-one container, health-checked by Traefik

### 7.1 Development Workflow Isolation
Development mode preserves existing workflow:
```bash
# Development Mode (unchanged)
./lightrag_webui/npm run dev-no-bun  # Port 5173
./reload_server.sh                   # Backend on 9621

# Production Mode (new integrated)
docker compose --profile prod up -d  # Single container on 9621
```

---

## 8 Logging & Observability

- **Traefik access-log** JSON → Loki
- **Uvicorn logs** JSON → same stack
- **OpenTelemetry** exporter enabled in Traefik 3.3 for distributed tracing
- **Health endpoints** for monitoring integration

### 8.1 Health Check Implementation
```python
@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow()}
```

---

## 9 File Structure Changes

```
lightrag/
├── Dockerfile                (multi-stage)
├── docker-compose.yml        (dev/ci/prod profiles)
├── traefik/
│   ├── docker-compose.yml
│   └── dynamic.yml           (middlewares)
├── secrets/                  (git-ignored)
│   ├── token_secret
│   ├── auth_users
│   └── api_key
├── scripts/
│   ├── setup-secrets.sh
│   └── deploy-homelab.sh
└── lightrag_webui/
    ├── src/
    ├── dist/                 (git-ignored)
    └── vite.config.ts        (base:'/webui/')
```

---

## 10 Implementation Task Board

| Phase | Task | Status |
| --- | --- | --- |
| **Setup** | Branch → feature/webui-integrated-deployment | ✅ |
| **Build** | Dockerfile multi-stage | ☐ |
| **Backend** | FastAPI static + fallback routes | ☐ |
| **Frontend** | Vite config for production base path | ☐ |
| **Infrastructure** | Traefik v3.3 stack & TLS | ☐ |
| **Security** | Rate-limit + headers middleware | ☐ |
| **Deployment** | Dev/CI/Prod compose profiles | ☐ |
| **Secrets** | Secrets creation scripts | ☐ |
| **Monitoring** | Health-check & /health endpoint | ☐ |
| **CI/CD** | SBOM & vulnerability scanning | ☐ |
| **Documentation** | Two-minute onboarding guide | ☐ |

---

## 11 Risks & Mitigations

| Risk | Guardrail |
| --- | --- |
| Dev speed hit (UI rebuild) | Keep legacy split in **dev** profile |
| Traefik syntax drift | Pin to v3.3, integrate upgrade test |
| Secrets leakage | Docker `secrets:` + git-ignored `secrets/` dir |
| Brute-force login | Traefik `ratelimit`, 12-char password policy |
| SPA 404s | Catch-all route for SPA history mode |
| Container health issues | Health checks + proper readiness probes |
| Multi-context compatibility | Preserve KV storage approach |

---

## 12 Expected Benefits

1. **Single Port Deployment**: `docker compose --profile prod up -d` exposes only :443
2. **Production Security**: Docker secrets, rate limiting, proper TLS
3. **Development Preserved**: Existing dev workflow unchanged
4. **Team Access**: Secure HTTPS through Traefik for external users
5. **Homelab Ready**: Tailscale admin access + public team access
6. **Monitoring Ready**: Health checks, logging, observability built-in
7. **CI/CD Ready**: Security scanning and SBOM generation
8. **Scalable**: Foundation for future Azure production deployment

---

## 13 Next Steps

1. **Immediate**: Implement multi-stage Dockerfile
2. **Short-term**: Configure FastAPI static file serving
3. **Medium-term**: Set up Traefik v3.3 with security middleware
4. **Long-term**: Team onboarding and production migration planning

*All critical production requirements and security best practices are built-in. The result is a single :443 endpoint that can be confidently deployed and shared with team members.*
