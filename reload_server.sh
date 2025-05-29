#!/bin/bash

# Script to reload LightRAG service
# Stops running containers, updates code, and restarts services

set -e  # Exit on any error
# Function to restart containers only
restart_only() {
    cd ../lightrag-test
    # Copy backup data before restart
    cp -frv ../LightRAG-data_bak/data/bc_data ./data/contexts/
    cp -frv ../LightRAG-data_bak/data/dxops ./data/contexts/
    docker compose restart
    docker compose logs -f
    exit 0
}


# Parse command line arguments
BUILD_FLAG=""
REBUILD=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --build)
            BUILD_FLAG="--build"
            REBUILD=true
            shift
            ;;
        --restart)
            restart_only
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--build]"
            exit 1
            ;;
    esac
done

# Only do full teardown if rebuild requested
if [ "$REBUILD" = true ]; then
    cd ../lightrag-test
    docker compose down -v --rmi local
    cd ../LightRAG
fi

cp -frv lightrag/lightrag.py ../lightrag-test/lightrag/lightrag.py
cp -frv lightrag/api ../lightrag-test/lightrag/
cp -frv lightrag/contexts ../lightrag-test/lightrag/
cp -frv lightrag/kg ../lightrag-test/lightrag/
# cp -frv lightrag/lightrag ../lightrag-test/lightrag/
cp -frv lightrag_webui/src ../lightrag-test/lightrag_webui/
cp -frv ../LightRAG-data_bak/data/bc_data ../lightrag-test/data/contexts/
cp -frv ../LightRAG-data_bak/data/dxops ../lightrag-test/data/contexts/

cd ../lightrag-test
docker compose up -d $BUILD_FLAG
docker compose logs -f


    