#!/bin/bash

# CCR Compliance Agent - Automation & Operations Runner
# Usage: ./run.sh [setup|crawl|start]

set -e

# Curated HSL colors for logs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0;0m' # No Color

function log_info() {
    echo -e "${CYAN}[INFO] $(date '+%Y-%m-%d %H:%M:%S') - $1${NC}"
}

function log_success() {
    echo -e "${GREEN}[SUCCESS] $(date '+%Y-%m-%d %H:%M:%S') - $1${NC}"
}

function log_warn() {
    echo -e "${YELLOW}[WARNING] $(date '+%Y-%m-%d %H:%M:%S') - $1${NC}"
}

function log_error() {
    echo -e "${RED}[ERROR] $(date '+%Y-%m-%d %H:%M:%S') - $1${NC}"
}

case "$1" in
    setup)
        log_info "Initializing development environment..."
        if [ ! -d "venv" ]; then
            log_info "Creating virtual environment 'venv'..."
            python3 -m venv venv
        fi
        
        log_info "Installing package dependencies from requirements.txt..."
        ./venv/bin/pip install --upgrade pip
        ./venv/bin/pip install -r requirements.txt
        
        log_info "Installing Playwright browser engine dependencies..."
        ./venv/bin/playwright install chromium
        
        log_success "Environment setup completed successfully!"
        log_info "To activate the environment: source venv/bin/activate"
        ;;
        
    crawl)
        if [ -z "$2" ]; then
            log_error "Missing seed URL parameter. Usage: ./run.sh crawl <URL> [limit]"
            exit 1
        fi
        URL="$2"
        LIMIT="${3:-20}"
        
        # Determine python executable
        PYTHON_EXEC="python3"
        if [ -d "venv" ]; then
            PYTHON_EXEC="./venv/bin/python"
        fi
        
        log_info "Starting ingestion pipeline for seed URL: $URL (limit: $LIMIT)..."
        $PYTHON_EXEC ingest.py --url "$URL" --limit "$LIMIT" --max-depth 1
        log_success "Ingestion completed successfully."
        ;;
        
    start)
        # Determine uvicorn executable
        UVICORN_EXEC="uvicorn"
        if [ -d "venv" ]; then
            UVICORN_EXEC="./venv/bin/uvicorn"
        fi
        
        log_info "Starting FastAPI Application backend & Web Dashboard..."
        $UVICORN_EXEC app.main:app --host 0.0.0.0 --port 8000 --reload
        ;;
        
    *)
        echo "CCR Compliance Agent Operations Runner"
        echo "Usage: $0 {setup|crawl <URL> [limit]|start}"
        echo "  setup               : Installs python dependencies and Playwright browser"
        echo "  crawl <URL> [limit] : Runs recursive crawling and DB ingestion pipeline"
        echo "  start               : Launches API backend server and React UI"
        exit 1
        ;;
esac
