#!/bin/bash

# LightRAG Homelab Deployment Script
# Sets up complete stack with Traefik and LightRAG

set -e

# Configuration
DOMAIN=${DOMAIN:-"example.com"}
LIGHTRAG_DOMAIN=${LIGHTRAG_DOMAIN:-"lightrag.$DOMAIN"}
ACME_EMAIL=${ACME_EMAIL:-"admin@$DOMAIN"}

echo "🚀 Deploying LightRAG to homelab..."
echo "Domain: $LIGHTRAG_DOMAIN"
echo "Email: $ACME_EMAIL"

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker and try again."
    exit 1
fi

# Check if secrets exist
if [ ! -d "./secrets" ] || [ ! -f "./secrets/token_secret" ]; then
    echo "❌ Secrets not found. Please run ./scripts/setup-secrets.sh first."
    exit 1
fi

# Create proxy network if it doesn't exist
echo "🔧 Setting up Docker networks..."
docker network create proxy 2>/dev/null || echo "Network 'proxy' already exists"

# Create Traefik data directory
echo "🔧 Setting up Traefik..."
mkdir -p traefik/data
touch traefik/data/acme.json
chmod 600 traefik/data/acme.json

# Start Traefik
echo "🌐 Starting Traefik reverse proxy..."
cd traefik
DOMAIN=$DOMAIN ACME_EMAIL=$ACME_EMAIL docker compose -f docker-compose.traefik.yml up -d
cd ..

# Wait for Traefik to be ready
echo "⏳ Waiting for Traefik to be ready..."
sleep 10

# Build and start LightRAG production container
echo "🏗️  Building LightRAG production image..."
docker compose --profile prod build

echo "🚀 Starting LightRAG production container..."
CORS_ORIGINS="https://$LIGHTRAG_DOMAIN" LIGHTRAG_DOMAIN=$LIGHTRAG_DOMAIN docker compose --profile prod up -d

# Wait for services to be ready
echo "⏳ Waiting for services to start..."
sleep 30

# Health check
echo "🔍 Checking service health..."
if curl -f -k "https://$LIGHTRAG_DOMAIN/health" > /dev/null 2>&1; then
    echo "✅ LightRAG is healthy and accessible at https://$LIGHTRAG_DOMAIN"
elif curl -f "http://localhost:9621/health" > /dev/null 2>&1; then
    echo "⚠️  LightRAG is running locally but may not be accessible via Traefik yet"
    echo "   Check Traefik logs: docker logs traefik"
else
    echo "❌ LightRAG health check failed"
    echo "   Check container logs: docker compose --profile prod logs"
    exit 1
fi

# Display status
echo ""
echo "🎉 Deployment complete!"
echo ""
echo "Services:"
echo "  🌐 LightRAG WebUI: https://$LIGHTRAG_DOMAIN"
echo "  📊 Traefik Dashboard: https://traefik.$DOMAIN (admin/admin)"
echo ""
echo "API Access:"
echo "  📡 API Endpoint: https://$LIGHTRAG_DOMAIN/api"
echo "  🔑 API Key: $(cat ./secrets/api_key)"
echo ""
echo "Useful commands:"
echo "  📋 View logs: docker compose --profile prod logs -f"
echo "  🔄 Restart: docker compose --profile prod restart"
echo "  🛑 Stop: docker compose --profile prod down"
echo "  🧹 Cleanup: docker compose --profile prod down -v"
echo ""
echo "⚠️  Remember to:"
echo "  1. Update DNS records to point $LIGHTRAG_DOMAIN to this server"
echo "  2. Configure firewall to allow ports 80 and 443"
echo "  3. Set up monitoring and log rotation"
echo "" 