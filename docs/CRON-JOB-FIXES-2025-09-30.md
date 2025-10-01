# HAE Cron Job Fixes - 2025-09-30

## Problem Statement

Daily HAE import cron job was failing consistently with:
1. **Postgres.app authentication errors**
2. **File not found errors** (HAE file created after cron runs)

## Root Causes Identified

### Issue 1: Postgres.app Permissions
```
FATAL: Postgres.app failed to verify "trust" authentication
DETAIL: You did not confirm the permission dialog
```

**Cause**: Cron jobs run in restricted environment where Postgres.app requires explicit permission dialogs that cannot be confirmed in automated context.

**Solution**: Use `set -a` to properly export all environment variables from `.env`, ensuring `DATABASE_URL` is available to Python subprocess.

### Issue 2: File Timing Mismatch
- **Cron scheduled**: 5:00 AM daily
- **HAE file created**: ~7:56 AM (varies)
- **Result**: File doesn't exist when cron runs

**Solution**: 
1. Changed cron time from 5:00 AM → **8:00 AM**
2. Added retry logic (waits up to 1 hour in 5-minute intervals)

## Changes Made

### File: `backend/ingest/hae_daily_pipeline_wrapper.sh`

**Fixed:**
1. **macOS date command** - Removed Linux-specific `-d` flag, using `-v` for macOS
2. **Environment variable export** - Changed from `source .env` to `set -a && source .env && set +a`
3. **Removed database connection test** - Caused Postgres.app permission dialogs
4. **Added file wait logic** - Retries for up to 1 hour if file doesn't exist
5. **Added TEF calculation step** - Ensures TEF is calculated for newly imported data
6. **Better error handling** - Exit codes and logging for each step

**Key Code Changes:**
```bash
# OLD: source .env
# NEW: set -a && source .env && set +a  (exports all variables)

# OLD: No retry logic
# NEW: Wait for file with 12 retries (1 hour total)

# NEW: Automatic TEF calculation after import
```

### Crontab Update

**Old:**
```
0 5 * * * cd /Users/markhill/Projects/health-agentic-workflow-mvp && ./backend/ingest/hae_daily_pipeline_wrapper.sh >> /tmp/hae_import.log 2>&1
```

**New:**
```
0 8 * * * cd /Users/markhill/Projects/health-agentic-workflow-mvp && ./backend/ingest/hae_daily_pipeline_wrapper.sh >> /tmp/hae_import.log 2>&1
```

## Testing Results

**Manual test (2025-09-29):**
```
✅ HAE file found
✅ Environment variables loaded
✅ HAE import successful
✅ TEF calculation updated
✅ Pipeline complete
```

**Verification:**
- daily_facts record created for 2025-09-29
- TEF calculated: 225.11 kcal
- All nutrition data imported correctly

## Expected Behavior Going Forward

**Timeline:**
- **~7:00-8:00 AM**: HAE app exports yesterday's data to Google Drive
- **8:00 AM**: Cron job starts
- **8:00-9:00 AM**: Script waits for file if needed, then imports
- **Result**: daily_facts updated with yesterday's data by 9:00 AM

**Monitoring:**
- Check `/tmp/hae_import.log` for cron execution logs
- Verify `daily_facts` has record for yesterday
- Ensure `tef_kcal` is calculated (not NULL)

## Remaining Issues

**Postgres.app Permissions**: While the script now works when environment variables are properly exported, Postgres.app may still show permission dialogs in some scenarios. The current fix bypasses the connection test to avoid triggering these dialogs.

**Alternative Solution (if issues persist)**: Configure Postgres to use password authentication instead of "trust" for localhost connections.

## Manual Import Command

If automation fails, manually import with:
```bash
cd /Users/markhill/Projects/health-agentic-workflow-mvp
./backend/ingest/hae_daily_pipeline_wrapper.sh 2025-09-29  # or any date
```

