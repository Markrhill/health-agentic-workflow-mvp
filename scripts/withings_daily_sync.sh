#!/bin/bash
# Withings Daily Sync Script
# Runs daily to extract new weight measurements from Withings API

set -e

# Set up environment for cron
export PATH="/opt/anaconda3/bin:/usr/local/bin:/usr/bin:/bin"
export PYTHONPATH="/opt/anaconda3/lib/python3.11/site-packages"

# Project root
PROJECT_ROOT="/Users/markhill/Projects/health-agentic-workflow-mvp"

# Log file
LOG_FILE="/tmp/withings_sync.log"

echo "$(date): Starting Withings daily sync" >> "$LOG_FILE"

# Change to project directory
cd "$PROJECT_ROOT"

# Source environment variables
if [ -f .env ]; then
    source .env
    echo "$(date): Environment variables loaded" >> "$LOG_FILE"
else
    echo "$(date): ERROR: .env file not found" >> "$LOG_FILE"
    exit 1
fi

# Test database connection
echo "Testing database connection..." >> "$LOG_FILE"
if ! pg_isready -h localhost -p 5432 -U markhill > /dev/null 2>&1; then
    echo "$(date): WARNING: Database connection test failed, but continuing..." >> "$LOG_FILE"
    echo "$(date): This is expected in cron environment due to Postgres.app permissions" >> "$LOG_FILE"
fi
echo "$(date): Proceeding with Withings sync..." >> "$LOG_FILE"

# Run the extraction script
echo "$(date): Starting Withings data extraction" >> "$LOG_FILE"
if env DATABASE_URL="$DATABASE_URL" /opt/anaconda3/bin/python scripts/extract_withings_raw.py --limit 100 >> "$LOG_FILE" 2>&1; then
    echo "$(date): Withings sync completed successfully" >> "$LOG_FILE"
else
    echo "$(date): ERROR: Withings sync failed" >> "$LOG_FILE"
    exit 1
fi

echo "$(date): Withings daily sync complete" >> "$LOG_FILE"
