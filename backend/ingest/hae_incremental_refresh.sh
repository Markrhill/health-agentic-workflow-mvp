#!/bin/bash
# Incremental HAE refresh - imports only files updated since last refresh
# Usage: ./hae_incremental_refresh.sh [source: cron|manual|backfill]

set -e  # Exit on error

# Set up environment
export PATH="/Applications/Postgres.app/Contents/Versions/latest/bin:/opt/anaconda3/bin:/usr/local/bin:/usr/bin:/bin"
export PYTHONPATH="/opt/anaconda3/lib/python3.11/site-packages"

PROJECT_ROOT="/Users/markhill/Projects/health-agentic-workflow-mvp"
HAE_DIR="/Users/markhill/Library/CloudStorage/GoogleDrive-mark@buildwhatsmissing.com/My Drive/Health Auto Export/Apple Health Exports"

cd "${PROJECT_ROOT}"

# Load environment variables
set -a
source .env
set +a

# Get source parameter (defaults to 'manual')
SOURCE="${1:-manual}"

echo "$(date): Starting incremental HAE refresh (source: ${SOURCE})"

# Get last_updated timestamp from database
LAST_UPDATED=$(psql "${DATABASE_URL}" -t -c "SELECT last_updated_at FROM hae_last_updated WHERE id = 1;" | xargs)

if [ -z "$LAST_UPDATED" ]; then
    echo "$(date): ERROR: Could not read last_updated_at from database"
    exit 1
fi

echo "$(date): Last updated: ${LAST_UPDATED}"

# Convert last_updated to Unix timestamp for comparison
# Handle both timezone-aware and naive timestamps
LAST_UPDATED_UNIX=$(date -j -f "%Y-%m-%d %H:%M:%S" "$(echo $LAST_UPDATED | cut -d'+' -f1 | cut -d'-' -f1-3,4-)" "+%s" 2>/dev/null || echo "0")

if [ "$LAST_UPDATED_UNIX" = "0" ]; then
    echo "$(date): WARNING: Could not parse timestamp, importing all files"
fi

# Find all HAE JSON files newer than last_updated
FILES_TO_IMPORT=()
IMPORT_COUNT=0

while IFS= read -r -d '' file; do
    FILE_MTIME=$(stat -f "%m" "$file")
    if [ "$FILE_MTIME" -gt "$LAST_UPDATED_UNIX" ]; then
        FILES_TO_IMPORT+=("$file")
        FILENAME=$(basename "$file")
        FILE_DATE=$(date -r "$FILE_MTIME" "+%Y-%m-%d %H:%M:%S")
        echo "$(date):   Found newer file: ${FILENAME} (modified: ${FILE_DATE})"
        IMPORT_COUNT=$((IMPORT_COUNT + 1))
    fi
done < <(find "${HAE_DIR}" -name "HealthAutoExport-*.json" -print0)

if [ ${IMPORT_COUNT} -eq 0 ]; then
    echo "$(date): No files to import (all up to date)"
    exit 0
fi

echo "$(date): Found ${IMPORT_COUNT} file(s) to import"

# Import each file
SUCCESS_COUNT=0
FAIL_COUNT=0

for file in "${FILES_TO_IMPORT[@]}"; do
    FILENAME=$(basename "$file")
    echo "$(date): Importing ${FILENAME}..."
    
    if /opt/anaconda3/bin/python etl/hae_import.py "$file"; then
        echo "$(date):   ✓ ${FILENAME} imported successfully"
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
        
        # Extract date from filename and materialize
        DATE=$(echo "$FILENAME" | sed 's/HealthAutoExport-//' | sed 's/.json//')
        echo "$(date):   Materializing ${DATE}..."
        /opt/anaconda3/bin/python etl/materialize_daily_series.py --date "${DATE}" || echo "$(date):   WARNING: Materialization failed for ${DATE}"
    else
        echo "$(date):   ✗ ${FILENAME} import failed"
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
done

echo "$(date): Import complete: ${SUCCESS_COUNT} succeeded, ${FAIL_COUNT} failed"

# Update last_updated timestamp if at least one file succeeded
if [ ${SUCCESS_COUNT} -gt 0 ]; then
    psql "${DATABASE_URL}" -c "UPDATE hae_last_updated SET last_updated_at = NOW(), updated_by = '${SOURCE}', notes = 'Imported ${SUCCESS_COUNT} file(s)' WHERE id = 1;"
    echo "$(date): Updated last_updated_at timestamp"
fi

echo "$(date): Incremental refresh complete"
exit 0

