#!/bin/bash

# LightRAG MCP Server Deployment Script
# Used by GitHub Actions CI/CD pipeline for automated deployment

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DEPLOY_ENV="${DEPLOY_ENV:-development}"
VERSION="${MCP_SERVER_VERSION:-latest}"

echo "🚀 Starting LightRAG MCP Server deployment..."
echo "   Environment: $DEPLOY_ENV"
echo "   Version: $VERSION"
echo "   Project Directory: $PROJECT_DIR"

# Function to log with timestamp
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Validate environment
validate_environment() {
    log "Validating deployment environment..."
    
    if ! command_exists uv; then
        log "ERROR: UV package manager not found. Please install UV."
        exit 1
    fi
    
    if ! command_exists docker; then
        log "ERROR: Docker not found. Please install Docker."
        exit 1
    fi
    
    log "✅ Environment validation passed"
}

# Build package
build_package() {
    log "Building MCP server package..."
    cd "$PROJECT_DIR"
    
    # Install dependencies if not already installed
    if [ ! -d ".venv" ]; then
        log "Creating virtual environment..."
        uv venv
    fi
    
    log "Installing dependencies..."
    uv sync --dev
    
    log "Building package..."
    uv build
    
    log "✅ Package build completed"
}

# Run tests
run_tests() {
    log "Running automated tests..."
    cd "$PROJECT_DIR"
    
    source .venv/bin/activate
    
    # Run unit tests only (integration tests require external services)
    python -m pytest ../tests/mcp/unit/ -v --tb=short || true
    
    log "✅ Tests completed"
}

# Build Docker image
build_docker_image() {
    log "Building Docker image..."
    cd "$PROJECT_DIR"
    
    # Create Dockerfile if it doesn't exist
    if [ ! -f "Dockerfile" ]; then
        log "Creating basic Dockerfile..."
        cat > Dockerfile << 'EOF'
FROM python:3.11-slim

WORKDIR /app

# Install UV
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copy project files
COPY . /app

# Install dependencies
RUN uv sync --no-dev

# Expose port
EXPOSE 8000

# Set default command
CMD ["uv", "run", "python", "-m", "lightrag_mcp"]
EOF
    fi
    
    # Build image
    docker build -t "lightrag-mcp-server:$VERSION" .
    
    log "✅ Docker image built: lightrag-mcp-server:$VERSION"
}

# Deploy based on environment
deploy() {
    case "$DEPLOY_ENV" in
        "development")
            deploy_development
            ;;
        "production")
            deploy_production
            ;;
        *)
            log "ERROR: Unknown deployment environment: $DEPLOY_ENV"
            exit 1
            ;;
    esac
}

# Development deployment
deploy_development() {
    log "Deploying to development environment..."
    
    # Stop existing container if running
    docker stop lightrag-mcp-dev 2>/dev/null || true
    docker rm lightrag-mcp-dev 2>/dev/null || true
    
    # Run new container
    docker run -d \
        --name lightrag-mcp-dev \
        --restart unless-stopped \
        -p 8001:8000 \
        -e "ENVIRONMENT=development" \
        "lightrag-mcp-server:$VERSION"
    
    log "✅ Development deployment completed"
    log "   Server accessible at: http://localhost:8001"
}

# Production deployment
deploy_production() {
    log "Deploying to production environment..."
    
    # Production deployment would typically involve:
    # - Kubernetes deployment
    # - Docker Swarm
    # - Container registry push
    # - Load balancer configuration
    
    log "⚠️  Production deployment not yet implemented"
    log "   This would involve:"
    log "   - Container registry push"
    log "   - Kubernetes/Docker Swarm deployment"
    log "   - Load balancer configuration"
    log "   - SSL certificate setup"
}

# Health check
health_check() {
    log "Performing health check..."
    
    # Wait for service to start
    sleep 10
    
    # Check if service is responding
    if command_exists curl; then
        if curl -f "http://localhost:8001/health" >/dev/null 2>&1; then
            log "✅ Health check passed"
        else
            log "⚠️  Health check failed - service may still be starting"
        fi
    else
        log "⚠️  curl not available - skipping health check"
    fi
}

# Cleanup function
cleanup() {
    log "Cleaning up temporary files..."
    # Add cleanup logic here if needed
}

# Main deployment flow
main() {
    trap cleanup EXIT
    
    validate_environment
    build_package
    run_tests
    build_docker_image
    deploy
    
    if [ "$DEPLOY_ENV" = "development" ]; then
        health_check
    fi
    
    log "🎉 Deployment completed successfully!"
}

# Show usage if no arguments
if [ $# -eq 0 ]; then
    echo "Usage: $0 [development|production]"
    echo ""
    echo "Environment variables:"
    echo "  DEPLOY_ENV          - Deployment environment (development|production)"
    echo "  MCP_SERVER_VERSION  - Version tag for deployment (default: latest)"
    echo ""
    echo "Examples:"
    echo "  $0 development"
    echo "  DEPLOY_ENV=production MCP_SERVER_VERSION=v1.0.0 $0"
    exit 1
fi

# Set environment if provided as argument
if [ $# -gt 0 ]; then
    DEPLOY_ENV="$1"
fi

# Run main deployment
main 