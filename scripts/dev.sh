#!/bin/bash
# Unified development startup script
# Usage: ./scripts/dev.sh [start|stop|restart|status]

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
BACKEND_PORT=3001
FRONTEND_PORT=3000
BACKEND_PID_FILE="$PROJECT_ROOT/.backend.pid"
FRONTEND_PID_FILE="$PROJECT_ROOT/.frontend.pid"

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
    
    # Check critical environment variables
    if ! grep -q "DATABASE_URL=" .env; then
        error "DATABASE_URL not found in .env"
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

# Start backend
start_backend() {
    log "Starting backend server..."
    cd backend
    npm start > ../.backend.log 2>&1 &
    BACKEND_PID=$!
    echo $BACKEND_PID > "$BACKEND_PID_FILE"
    cd ..
    
    # Wait for backend to start
    sleep 3
    if curl -s "http://localhost:$BACKEND_PORT/api/health" >/dev/null 2>&1; then
        log "Backend started successfully on port $BACKEND_PORT"
    else
        warn "Backend may not be fully ready yet"
    fi
}

# Start frontend
start_frontend() {
    log "Starting frontend server..."
    cd frontend
    nohup npm start > ../.frontend.log 2>&1 &
    FRONTEND_PID=$!
    echo $FRONTEND_PID > "$FRONTEND_PID_FILE"
    cd ..
    
    log "Frontend starting on port $FRONTEND_PORT (check logs with: tail -f .frontend.log)"
}

# Stop services
stop_services() {
    log "Stopping services..."
    
    # Stop backend
    if [[ -f "$BACKEND_PID_FILE" ]]; then
        BACKEND_PID=$(cat "$BACKEND_PID_FILE")
        if kill -0 "$BACKEND_PID" 2>/dev/null; then
            kill "$BACKEND_PID"
            log "Backend stopped"
        fi
        rm -f "$BACKEND_PID_FILE"
    fi
    
    # Stop frontend
    if [[ -f "$FRONTEND_PID_FILE" ]]; then
        FRONTEND_PID=$(cat "$FRONTEND_PID_FILE")
        if kill -0 "$FRONTEND_PID" 2>/dev/null; then
            kill "$FRONTEND_PID"
            log "Frontend stopped"
        fi
        rm -f "$FRONTEND_PID_FILE"
    fi
    
    # Kill any remaining processes
    pkill -f "node.*server.js" 2>/dev/null || true
    pkill -f "react-scripts start" 2>/dev/null || true
}

# Check service status
check_status() {
    log "Checking service status..."
    
    # Check backend
    if curl -s "http://localhost:$BACKEND_PORT/api/health" >/dev/null 2>&1; then
        log "✅ Backend: Running on port $BACKEND_PORT"
    else
        warn "❌ Backend: Not responding on port $BACKEND_PORT"
    fi
    
    # Check frontend
    if curl -s "http://localhost:$FRONTEND_PORT" >/dev/null 2>&1; then
        log "✅ Frontend: Running on port $FRONTEND_PORT"
    else
        warn "❌ Frontend: Not responding on port $FRONTEND_PORT"
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
        stop_services  # Clean up any existing processes
        start_backend
        start_frontend
        log "Development environment started!"
        log "Backend: http://localhost:$BACKEND_PORT"
        log "Frontend: http://localhost:$FRONTEND_PORT"
        ;;
    stop)
        stop_services
        log "All services stopped"
        ;;
    restart)
        log "Restarting services..."
        stop_services
        sleep 2
        $0 start
        ;;
    status)
        check_status
        ;;
    *)
        echo "Usage: $0 [start|stop|restart|status]"
        echo "  start   - Start all services (default)"
        echo "  stop    - Stop all services"
        echo "  restart - Restart all services"
        echo "  status  - Check service status"
        exit 1
        ;;
esac