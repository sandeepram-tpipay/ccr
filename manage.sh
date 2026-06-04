#!/usr/bin/env base
# Compliance Engine Orchestrator script

set -e

# Styled HSL colors for status logs
MAGENTA='\033[0;35m'
EMERALD='\033[0;32m'
GOLD='\033[1;33m'
BLUE='\033[0;34m'
RESET='\033[0;0m'

function print_info() {
    echo -e "${BLUE}[INFO] $(date '+%Y-%m-%d %H:%M:%S') - $1${RESET}"
}

function print_ok() {
    echo -e "${EMERALD}[OK] $(date '+%Y-%m-%d %H:%M:%S') - $1${RESET}"
}

function print_warn() {
    echo -e "${GOLD}[WARN] $(date '+%Y-%m-%d %H:%M:%S') - $1${RESET}"
}

function print_error() {
    echo -e "${MAGENTA}[ERROR] $(date '+%Y-%m-%d %H:%M:%S') - $1${RESET}"
}

case "$1" in
    setup)
        print_info "Starting environment setup..."
        if [ ! -d "venv" ]; then
            print_info "Creating new virtual environment 'venv'..."
            python3 -m venv venv
        fi
        
        print_info "Upgrading pip and installing requirements..."
        ./venv/bin/pip install --upgrade pip
        ./venv/bin/pip install -r requirements.txt
        
        print_info "Installing playwright driver packages..."
        ./venv/bin/playwright install chromium
        
        print_ok "Setup finished successfully."
        ;;
        
    crawl)
        if [ -z "$2" ]; then
            print_error "Error: Seed URL is required. Format: ./manage.sh crawl <URL> [limit]"
            exit 1
        fi
        URL="$2"
        LIMIT="${3:-20}"
        
        PY_BIN="python3"
        if [ -d "venv" ]; then
            PY_BIN="./venv/bin/python"
        fi
        
        print_info "Triggering load_data.py on: $URL with limit $LIMIT..."
        $PY_BIN load_data.py --url "$URL" --limit "$LIMIT" --depth 1
        print_ok "Ingestion scan run finalized."
        ;;
        
    start)
        UVICORN_BIN="uvicorn"
        if [ -d "venv" ]; then
            UVICORN_BIN="./venv/bin/uvicorn"
        fi
        
        print_info "Booting Uvicorn server hosting compliance_engine.server..."
        $UVICORN_BIN compliance_engine.server:app --host 0.0.0.0 --port 8000 --reload
        ;;
        
    *)
        echo "California Code of Regulations Compliance Engine Command Orchestrator"
        echo "Usage: $0 {setup|crawl <URL> [limit]|start}"
        echo "  setup               : Sets up virtual environment and browser packages"
        echo "  crawl <URL> [limit] : Discovers URLs and indexes regulation sections"
        echo "  start               : Runs Uvicorn API server and front end client dashboard"
        exit 1
        ;;
esac
