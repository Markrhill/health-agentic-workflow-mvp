#!/bin/bash
set -e

# Set up environment for cron
export PATH="/opt/anaconda3/bin:/usr/local/bin:/usr/bin:/bin"
export PYTHONPATH="/opt/anaconda3/lib/python3.11/site-packages"

# Calculate yesterday's date (works in both cron and interactive shells)
if [ -z "$1" ]; then
    # Get yesterday's date
    DATE=$(date -v-1d +%Y-%m-%d 2>/dev/null || date -d "yesterday" +%Y-%m-%d 2>/dev/null || date +%Y-%m-%d)
else
    DATE="$1"
fi

HAE_DIR="/Users/markhill/Library/CloudStorage/GoogleDrive-mark@buildwhatsmissing.com/My Drive/Health Auto Export/Apple Health Exports"
HAE_FILE="${HAE_DIR}/HealthAutoExport-${DATE}.json"
PROJECT_ROOT="/Users/markhill/Projects/health-agentic-workflow-mvp"

echo "$(date): Starting HAE pipeline for ${DATE}"

if [ ! -f "${HAE_FILE}" ]; then
    echo "ERROR: File not found: ${HAE_FILE}"
    exit 1
fi

cd "${PROJECT_ROOT}"

# Source environment variables
source .env

# Use full Python path with conda environment
echo "Step 1: Import HAE JSON"
/opt/anaconda3/bin/python etl/hae_import.py "${HAE_FILE}"

echo "Step 2: Materialize daily series"
/opt/anaconda3/bin/python etl/materialize_daily_series.py --date "${DATE}"

echo "$(date): Pipeline complete for ${DATE}"
