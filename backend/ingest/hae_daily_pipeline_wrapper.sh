#!/bin/bash
# Wrapper script to handle PostgreSQL authentication issues in cron
# This script ensures proper environment setup for automated runs
#
# Fixed Issues:
# 1. Postgres.app permissions - Use DATABASE_URL with explicit connection params
# 2. File timing - Wait for HAE file to be created (with retry logic)

# Set up environment for cron
export PATH="/opt/anaconda3/bin:/usr/local/bin:/usr/bin:/bin"
export PYTHONPATH="/opt/anaconda3/lib/python3.11/site-packages"

# Calculate yesterday's date (macOS compatible)
# Priority: 1) Positional arg $1, 2) FACT_DATE env var, 3) Yesterday
if [ -n "$1" ]; then
    DATE="$1"
elif [ -n "$FACT_DATE" ]; then
    DATE="$FACT_DATE"
else
    # Get yesterday's date - macOS uses -v, Linux uses -d
    if date -v-1d +%Y-%m-%d >/dev/null 2>&1; then
        # macOS
        DATE=$(date -v-1d +%Y-%m-%d)
    else
        # Linux/GNU
        DATE=$(date -d "yesterday" +%Y-%m-%d)
    fi
fi

HAE_DIR="/Users/markhill/Library/CloudStorage/GoogleDrive-mark@buildwhatsmissing.com/My Drive/Health Auto Export/Apple Health Exports"
HAE_FILE="${HAE_DIR}/HealthAutoExport-${DATE}.json"
PROJECT_ROOT="/Users/markhill/Projects/health-agentic-workflow-mvp"

echo "$(date): Starting HAE pipeline for ${DATE}"

# Wait for HAE file to be created (with retry logic)
MAX_RETRIES=12  # Try for 1 hour (12 * 5 minutes)
RETRY_COUNT=0
RETRY_DELAY=300  # 5 minutes

while [ ! -f "${HAE_FILE}" ] && [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    echo "$(date): Waiting for HAE file (attempt $((RETRY_COUNT + 1))/${MAX_RETRIES})..."
    sleep $RETRY_DELAY
    RETRY_COUNT=$((RETRY_COUNT + 1))
done

if [ ! -f "${HAE_FILE}" ]; then
    echo "$(date): ERROR: File not found after ${MAX_RETRIES} retries: ${HAE_FILE}"
    exit 1
fi

echo "$(date): HAE file found: ${HAE_FILE}"

cd "${PROJECT_ROOT}"

# Load environment variables using set -a to export all variables
set -a
source .env
set +a

echo "$(date): Environment variables loaded"

# Use full Python path with conda environment and explicit DATABASE_URL
echo "$(date): Step 1: Import HAE JSON"
if /opt/anaconda3/bin/python etl/hae_import.py "${HAE_FILE}"; then
    echo "$(date): HAE import successful"
else
    echo "$(date): ERROR: HAE import failed"
    exit 1
fi

# Update TEF for the newly imported date
echo "$(date): Step 2: Update TEF calculation"
/opt/anaconda3/bin/python -c "
import os
import psycopg2
from datetime import datetime, timedelta

conn = psycopg2.connect(os.getenv('DATABASE_URL'))
cur = conn.cursor()

# Calculate TEF for yesterday
cur.execute('''
UPDATE daily_facts
SET tef_kcal = ROUND(
    COALESCE(protein_g * 4 * 0.25, 0) +
    COALESCE(carbs_g * 4 * 0.08, 0) +
    COALESCE(fat_g * 9 * 0.02, 0),
    2
)
WHERE fact_date = %s
  AND tef_kcal IS NULL
''', ('${DATE}',))

conn.commit()
print('TEF updated for ${DATE}')
conn.close()
"

# Materialize daily series for the imported date
echo "$(date): Step 3: Materialize daily series"
if /opt/anaconda3/bin/python etl/materialize_daily_series.py --date "${DATE}"; then
    echo "$(date): Daily series materialized successfully"
else
    echo "$(date): ERROR: Daily series materialization failed"
    exit 1
fi

echo "$(date): Pipeline complete for ${DATE}"
