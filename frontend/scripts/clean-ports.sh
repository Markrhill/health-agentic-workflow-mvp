#!/bin/bash

# Clean Ports Script
# Kills any existing processes on ports 3000 and 3001

echo "🧹 Cleaning ports 3000 and 3001..."

# Kill processes on port 3000 (frontend)
if lsof -ti:3000 > /dev/null 2>&1; then
    echo "  Killing processes on port 3000..."
    lsof -ti:3000 | xargs kill -9 2>/dev/null || true
    sleep 1
fi

# Kill processes on port 3001 (backend)
if lsof -ti:3001 > /dev/null 2>&1; then
    echo "  Killing processes on port 3001..."
    lsof -ti:3001 | xargs kill -9 2>/dev/null || true
    sleep 1
fi

# Verify ports are clean
if lsof -ti:3000 > /dev/null 2>&1; then
    echo "❌ Port 3000 still in use"
    exit 1
fi

if lsof -ti:3001 > /dev/null 2>&1; then
    echo "❌ Port 3001 still in use"
    exit 1
fi

echo "✅ Ports 3000 and 3001 are clean"
