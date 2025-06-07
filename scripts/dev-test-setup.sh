#!/bin/bash

# LightRAG Development Testing Setup Script
# Comprehensive environment setup and validation for post-integration testing

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
BACKEND_PORT=9621
FRONTEND_PORT=5173
HEALTH_ENDPOINT="http://localhost:${BACKEND_PORT}/health"
FRONTEND_ENDPOINT="http://localhost:${FRONTEND_PORT}"

# Logging function
log() {
    echo -e "${BLUE}[$(date +'%H:%M:%S')]${NC} $1"
}

success() {
    echo -e "${GREEN}✅${NC} $1"
}

warning() {
    echo -e "${YELLOW}⚠️${NC} $1"
}

error() {
    echo -e "${RED}❌${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log "Checking prerequisites..."
    
    if ! command -v docker &> /dev/null; then
        error "Docker not found. Please install Docker."
        exit 1
    fi
    
    if ! docker info > /dev/null 2>&1; then
        error "Docker is not running. Please start Docker."
        exit 1
    fi
    
    if ! command -v curl &> /dev/null; then
        error "curl not found. Please install curl."
        exit 1
    fi
    
    if [ ! -f "docker-compose.yml" ]; then
        error "docker-compose.yml not found. Run from project root."
        exit 1
    fi
    
    success "Prerequisites check passed"
}

# Environment cleanup
cleanup_environment() {
    log "Cleaning up existing environment..."
    
    # Stop any running containers
    docker compose down > /dev/null 2>&1 || true
    
    # Clean up old containers and networks
    docker system prune -f > /dev/null 2>&1 || true
    
    # Ensure proxy network exists
    docker network create proxy > /dev/null 2>&1 || true
    
    success "Environment cleanup completed"
}

# Start development environment
start_dev_environment() {
    log "Starting development environment..."
    
    # Start development profile
    docker compose --profile dev up -d
    
    if [ $? -eq 0 ]; then
        success "Development containers started"
    else
        error "Failed to start development containers"
        docker compose --profile dev logs
        exit 1
    fi
}

# Wait for backend to be ready
wait_for_backend() {
    log "Waiting for backend to be ready..."
    
    local retries=30
    local count=0
    
    while [ $count -lt $retries ]; do
        if curl -f "$HEALTH_ENDPOINT" > /dev/null 2>&1; then
            success "Backend is ready at $HEALTH_ENDPOINT"
            return 0
        fi
        
        count=$((count + 1))
        echo -n "."
        sleep 2
    done
    
    error "Backend failed to become ready after $((retries * 2)) seconds"
    docker compose --profile dev logs lightrag-dev
    exit 1
}

# Start WebUI development server
start_webui_dev() {
    log "Starting WebUI development server..."
    
    if [ ! -d "lightrag_webui" ]; then
        warning "WebUI directory not found, skipping frontend dev server"
        return 0
    fi
    
    cd lightrag_webui
    
    # Check if npm dependencies are installed
    if [ ! -d "node_modules" ]; then
        log "Installing npm dependencies..."
        npm install
    fi
    
    # Start dev server in background
    log "Starting Vite dev server on port $FRONTEND_PORT..."
    nohup npm run dev-no-bun > ../dev-server.log 2>&1 &
    local webui_pid=$!
    echo $webui_pid > ../webui_dev.pid
    
    cd ..
    
    # Wait a moment for server to start
    sleep 5
    
    success "WebUI dev server started (PID: $webui_pid)"
}

# Validate environment
validate_environment() {
    log "Validating environment..."
    
    # Check backend health
    if curl -f "$HEALTH_ENDPOINT" > /dev/null 2>&1; then
        success "Backend health check passed"
    else
        error "Backend health check failed"
        return 1
    fi
    
    # Check WebUI dev server (if running)
    if curl -f "$FRONTEND_ENDPOINT" > /dev/null 2>&1; then
        success "WebUI dev server check passed"
    else
        warning "WebUI dev server not responding (this is optional)"
    fi
    
    # Check container status
    log "Container status:"
    docker compose --profile dev ps
    
    return 0
}

# Display access information
display_access_info() {
    echo ""
    echo -e "${GREEN}🎉 Development environment is ready!${NC}"
    echo ""
    echo -e "${BLUE}Access URLs:${NC}"
    echo "  🔧 Backend API: http://localhost:$BACKEND_PORT"
    echo "  🌐 API Health: $HEALTH_ENDPOINT"
    echo "  📱 WebUI Dev: http://localhost:$FRONTEND_PORT (if running)"
    echo "  📚 API Docs: http://localhost:$BACKEND_PORT/docs"
    echo ""
    echo -e "${BLUE}Authentication:${NC}"
    echo "  👤 Username: admin"
    echo "  🔑 Password: admin123"
    echo ""
    echo -e "${BLUE}Testing Commands:${NC}"
    echo "  📋 View logs: docker compose --profile dev logs -f"
    echo "  🔄 Restart backend: docker compose --profile dev restart lightrag-dev"
    echo "  🛑 Stop all: docker compose --profile dev down"
    echo ""
    echo -e "${BLUE}Next Steps:${NC}"
    echo "  1. Test multi-context switching"
    echo "  2. Upload and process documents"
    echo "  3. Validate API endpoints"
    echo "  4. Test WebUI functionality"
    echo ""
}

# Cleanup function for script exit
cleanup_on_exit() {
    if [ -f "webui_dev.pid" ]; then
        local webui_pid=$(cat webui_dev.pid)
        if kill -0 $webui_pid 2>/dev/null; then
            warning "Stopping WebUI dev server (PID: $webui_pid)"
            kill $webui_pid 2>/dev/null || true
        fi
        rm -f webui_dev.pid
    fi
}

# Main execution
main() {
    echo -e "${BLUE}🚀 LightRAG Development Testing Setup${NC}"
    echo "================================="
    
    # Set up cleanup on exit
    trap cleanup_on_exit EXIT
    
    check_prerequisites
    cleanup_environment
    start_dev_environment
    wait_for_backend
    start_webui_dev
    
    if validate_environment; then
        display_access_info
        success "Development environment setup completed successfully!"
    else
        error "Environment validation failed"
        exit 1
    fi
}

# Handle script arguments
case "${1:-}" in
    --help|-h)
        echo "LightRAG Development Testing Setup Script"
        echo ""
        echo "Usage: $0 [options]"
        echo ""
        echo "Options:"
        echo "  --help, -h    Show this help message"
        echo "  --no-webui    Skip WebUI dev server setup"
        echo "  --cleanup     Only perform cleanup, don't start services"
        echo ""
        exit 0
        ;;
    --cleanup)
        check_prerequisites
        cleanup_environment
        success "Cleanup completed"
        exit 0
        ;;
    --no-webui)
        SKIP_WEBUI=true
        ;;
esac

# Run main function
main 