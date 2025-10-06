# Idempotent Import Principle: Freshest Data Wins

**Status:** ✅ Implemented (October 5, 2025)

---

## 🎯 Core Principle

> **"Updated HAE data with a more recent timestamp always overwrites prior data."**

The system automatically detects when an HAE file has been updated since the last import and **forces an overwrite** to ensure we always use the freshest data.

---

## 🏗️ Architecture

### **Automatic Freshness Detection**

The `hae_import.py` script compares:
1. **File modification time** (`st_mtime` from filesystem)
2. **Last import timestamp** (`ingested_at` from `hae_raw` table)

**Decision logic:**

```python
if file_mtime > ingested_at:
    # File has been updated - force overwrite
    overwrite_mode = 'overwrite'
    print("📁 File updated since last import")
    print("🔄 Forcing overwrite to use freshest data")
```

### **User Override Behavior**

- **User specifies `overwrite`**: Always overwrites (as before)
- **User specifies `update_nulls`**: Checks freshness first, upgrades to `overwrite` if file is newer
- **User specifies `skip_existing`**: Checks freshness first, upgrades to `overwrite` if file is newer

**Result:** Users don't need to remember to use `overwrite` mode - the system does it automatically when needed.

---

## 🔄 Import Modes

### **1. `update_nulls` (Default)**

- Only fills in missing (`NULL`) values
- **Upgraded to `overwrite` if file is newer**

```bash
# These are equivalent if file is fresh:
python etl/hae_import.py file.json
python etl/hae_import.py file.json update_nulls
python etl/hae_import.py file.json overwrite  # (when file is newer)
```

### **2. `overwrite` (Explicit)**

- Always replaces all data
- Use when you want to force re-import regardless of timestamp

```bash
python etl/hae_import.py file.json overwrite
```

### **3. `skip_existing` (Rarely Used)**

- Don't touch existing records
- **Upgraded to `overwrite` if file is newer**

```bash
python etl/hae_import.py file.json skip_existing
```

---

## 📊 Behavior Examples

### **Example 1: File Updated Since Last Import**

```bash
# Initial import at 2:00pm
$ python etl/hae_import.py HealthAutoExport-2025-10-05.json
Loading HealthAutoExport-2025-10-05.json...
Imported HealthAutoExport-2025-10-05.json as import_id 19

# HAE refreshes file at 7:23pm with updated nutrition data
# User runs import again (or cron job runs at 8:00am next day)
$ python etl/hae_import.py HealthAutoExport-2025-10-05.json
Loading HealthAutoExport-2025-10-05.json...
📁 File HealthAutoExport-2025-10-05.json updated since last import 
   (file: 2025-10-05 19:23:00, last import: 2025-10-05 14:00:00)
🔄 Forcing overwrite to use freshest data (import_id 19)
Cleared existing metrics for import_id 19
Imported HealthAutoExport-2025-10-05.json as import_id 19 ✅
```

**Result:** Automatically detects newer data and overwrites.

### **Example 2: File Unchanged**

```bash
# Import at 2:00pm
$ python etl/hae_import.py HealthAutoExport-2025-10-05.json
Imported HealthAutoExport-2025-10-05.json as import_id 19

# Run again at 3:00pm (file hasn't changed)
$ python etl/hae_import.py HealthAutoExport-2025-10-05.json
Loading HealthAutoExport-2025-10-05.json...
File HealthAutoExport-2025-10-05.json already imported as import_id 19 (no newer data) ✅
```

**Result:** Skips re-import (idempotent - no duplicate work).

### **Example 3: Cron Job (Automatic)**

```bash
# Cron job runs daily at 8:00am
# Uses default mode (update_nulls) which auto-detects freshness
$ bash backend/ingest/hae_daily_pipeline_wrapper.sh 2025-10-05

# If HAE file was updated overnight → automatic overwrite ✅
# If HAE file unchanged → skip re-import ✅
```

**Result:** Cron job is idempotent and always uses freshest data.

---

## 🎓 Why This Matters

### **Problem Solved**

**Before:** Users had to manually specify `overwrite` mode when they knew data was stale:
```bash
# User checks file timestamp
# User notices it's newer
# User remembers to use overwrite mode
python etl/hae_import.py file.json overwrite
```

**After:** System automatically detects and handles it:
```bash
# User just runs the import
python etl/hae_import.py file.json
# System: "File is newer, I'll overwrite automatically"
```

### **Benefits**

1. ✅ **Idempotent imports** - Safe to run multiple times
2. ✅ **Always fresh data** - Newer files always overwrite
3. ✅ **No manual intervention** - Users don't need to check timestamps
4. ✅ **Cron job safe** - Daily runs automatically handle updated files
5. ✅ **Refresh button works** - Frontend refresh always gets latest data

---

## 🔍 Implementation Details

### **File Modified Time**

```python
from pathlib import Path
from datetime import datetime

file_mtime = datetime.fromtimestamp(Path(file_path).stat().st_mtime)
```

- Uses filesystem metadata (`st_mtime`)
- Returns naive datetime (local timezone)
- Updated when file content changes

### **Database Import Timestamp**

```sql
SELECT import_id, ingested_at 
FROM hae_raw 
WHERE file_name = %s
```

- `ingested_at`: Timestamp of last import (timezone-aware)
- Updated via `CURRENT_TIMESTAMP` on insert/update
- Stored in PostgreSQL `TIMESTAMP WITH TIME ZONE` column

### **Timezone Handling**

```python
# Convert ingested_at to naive datetime for comparison (assumes both are local time)
ingested_at_naive = ingested_at.replace(tzinfo=None) if ingested_at.tzinfo else ingested_at
if file_mtime > ingested_at_naive:
    overwrite_mode = 'overwrite'
```

- Both timestamps are in local time (Pacific)
- Strip timezone from DB timestamp for comparison
- Safe because both represent local time

---

## 🧪 Testing

### **Manual Test**

```bash
# Import a file
python etl/hae_import.py HealthAutoExport-2025-10-05.json

# Touch the file to update mtime
touch '/path/to/HealthAutoExport-2025-10-05.json'

# Import again - should auto-overwrite
python etl/hae_import.py HealthAutoExport-2025-10-05.json
# Expected: "📁 File updated since last import"
# Expected: "🔄 Forcing overwrite to use freshest data"
```

### **Cron Job Test**

```bash
# Run the daily pipeline
bash backend/ingest/hae_daily_pipeline_wrapper.sh 2025-10-05

# Check logs
# Expected: Auto-overwrite if file is newer
# Expected: Skip if file unchanged
```

### **Refresh Button Test**

1. Click "Refresh Data" in frontend
2. Check backend logs
3. Verify auto-overwrite if file is newer

---

## 📝 Related Files

- `etl/hae_import.py` - Core import logic with freshness detection
- `backend/ingest/hae_daily_pipeline_wrapper.sh` - Cron job wrapper
- `backend/routes/api.js` - Manual refresh endpoint (`/api/refresh`)
- `docs/HAE-DATA-REFRESH-PROCEDURE.md` - Manual refresh procedures

---

## 🔗 Commit History

- **Initial implementation**: [This commit]
- **Timezone fix**: [This commit]
- **Documentation**: [This commit]

---

## 💡 Future Enhancements

1. **Multi-file freshness check**: If HAE exports multiple files per day, check all for freshness
2. **Checksum validation**: Compare file content hash in addition to timestamp
3. **Audit trail**: Log when automatic overwrites occur for debugging
4. **Notification**: Alert user when stale data is detected and overwritten

---

**Last Updated:** October 5, 2025  
**Status:** ✅ Production Ready

