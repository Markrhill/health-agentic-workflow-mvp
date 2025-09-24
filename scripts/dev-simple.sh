#!/bin/bash
# Simple development startup script
# Usage: ./scripts/dev-simple.sh [start|stop|status]

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[DEV]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if .env exists
check_env() {
    if [[ ! -f ".env" ]]; then
        error ".env file not found!"
        echo "Please create .env file from .env.example"
        exit 1
    fi
    
    log "Environment configuration verified"
}

# Check if database is accessible
check_database() {
    log "Checking database connection..."
    if ! psql "$(grep DATABASE_URL .env | cut -d'=' -f2)" -c "SELECT 1;" >/dev/null 2>&1; then
        error "Database connection failed!"
        echo "Please ensure PostgreSQL is running and DATABASE_URL is correct"
        exit 1
    fi
    log "Database connection verified"
}

# Stop all services
stop_all() {
    log "Stopping all services..."
    pkill -f "node.*server.js" 2>/dev/null || true
    pkill -f "react-scripts start" 2>/dev/null || true
    pkill -f "npm start" 2>/dev/null || true
    sleep 2
}

# Check service status
check_status() {
    log "Checking service status..."
    
    # Check backend
    if curl -s "http://localhost:3001/api/health" >/dev/null 2>&1; then
        log "✅ Backend: Running on port 3001"
    else
        warn "❌ Backend: Not responding on port 3001"
    fi
    
    # Check frontend
    if curl -s "http://localhost:3000" >/dev/null 2>&1; then
        log "✅ Frontend: Running on port 3000"
    else
        warn "❌ Frontend: Not responding on port 3000"
    fi
    
    # Check database
    if psql "$(grep DATABASE_URL .env | cut -d'=' -f2)" -c "SELECT 1;" >/dev/null 2>&1; then
        log "✅ Database: Connected"
    else
        warn "❌ Database: Connection failed"
    fi
}

# Main command handling
case "${1:-start}" in
    start)
        log "Starting Health Agentic Workflow MVP..."
        check_env
        check_database
        stop_all
        
        log "Starting backend server..."
        cd backend
        npm start &
        cd ..
        
        log "Starting frontend server..."
        cd frontend
        npm start &
        cd ..
        
        log "Services starting..."
        log "Backend: http://localhost:3001"
        log "Frontend: http://localhost:3000"
        log ""
        log "To check status: ./scripts/dev-simple.sh status"
        log "To stop: ./scripts/dev-simple.sh stop"
        ;;
    stop)
        stop_all
        log "All services stopped"
        ;;
    status)
        check_status
        ;;
    *)
        echo "Usage: $0 [start|stop|status]"
        echo "  start   - Start all services (default)"
        echo "  stop    - Stop all services"
        echo "  status  - Check service status"
        exit 1
        ;;
esac
