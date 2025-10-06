# HAE Data Refresh Procedure

**Purpose:** Document the proper procedure for refreshing Health Auto Export (HAE) data when files are updated.

---

## 🎯 When to Use This

- HAE file was updated after initial import
- Data looks incorrect or incomplete
- Nutrition data is missing for recent days
- "Refresh Data" button doesn't fix the issue

---

## ⚠️ Problem: HAE Files Contain 2 Days

**Critical Issue:** Each HAE file contains data for **2 days**:
1. The date in the filename (e.g., `HealthAutoExport-2025-10-05.json` → Oct 5)
2. The **previous day** (Oct 4)

When you import a file in `overwrite` mode, it **clears data for both days** from the previous import, which can cascade and clear data from adjacent days.

---

## ✅ Correct Refresh Procedure

### **Option 1: Refresh Multiple Days (Recommended)**

When you know data is stale for a range of days:

```bash
# Import all files in sequence (oldest to newest)
# This ensures each file's 2-day window overlaps correctly

python etl/hae_import.py \
  '/path/to/HealthAutoExport-2025-10-02.json' overwrite

python etl/hae_import.py \
  '/path/to/HealthAutoExport-2025-10-03.json' overwrite

python etl/hae_import.py \
  '/path/to/HealthAutoExport-2025-10-04.json' overwrite

python etl/hae_import.py \
  '/path/to/HealthAutoExport-2025-10-05.json' overwrite

# Then materialize the entire range
python etl/materialize_daily_series.py --date-range 2025-10-02 2025-10-05
```

### **Option 2: Refresh Single Day (Risky)**

Only when you're certain just one day needs updating:

```bash
# Import the file
python etl/hae_import.py \
  '/path/to/HealthAutoExport-2025-10-05.json' overwrite

# Materialize
python etl/materialize_daily_series.py --date 2025-10-05

# Check adjacent days for NULL values
psql -d markhill -c "SELECT fact_date, intake_kcal FROM daily_facts 
                      WHERE fact_date BETWEEN '2025-10-04' AND '2025-10-06' 
                      ORDER BY fact_date;"
```

---

## 🔍 Verification Steps

### 1. **Check Raw Data**

```bash
psql -d markhill -c "SELECT fact_date, intake_kcal, protein_g, carbs_g, fat_g 
                      FROM daily_facts 
                      WHERE fact_date BETWEEN '2025-09-29' AND '2025-10-05' 
                      ORDER BY fact_date;"
```

**Look for:**
- ✅ All days have values (not NULL)
- ✅ Values match HAE JSON files
- ✅ No obvious gaps or zeros

### 2. **Check Materialized View**

```bash
psql -d markhill -c "SELECT fact_date, bmr_kcal, net_kcal, fat_mass_ema_kg 
                      FROM daily_series_materialized 
                      WHERE fact_date >= '2025-10-02' 
                      ORDER BY fact_date DESC LIMIT 7;"
```

**Look for:**
- ✅ All days are present
- ✅ `net_kcal` is calculated
- ✅ `fat_mass_ema_kg` is not NULL

### 3. **Check Weekly API**

```bash
curl -s 'http://localhost:3001/api/weekly?weeks=1' | python3 -m json.tool | head -15
```

**Look for:**
- ✅ `total_intake` is reasonable (not 0, not suspiciously low)
- ✅ `days_in_week` = 7
- ✅ `avg_net_kcal` makes sense

### 4. **Check Daily API**

```bash
curl -s 'http://localhost:3001/api/daily/2025-09-29/2025-10-05' | 
  python3 -c "import sys, json; d=json.load(sys.stdin); print(f\"Days: {len(d)}\"); [print(f\"{x['fact_date']}: {x['intake_kcal']} kcal\") for x in d]"
```

**Look for:**
- ✅ 7 days returned
- ✅ All intake values present

---

## 🐛 Troubleshooting

### **Problem: Day X shows NULL intake after refresh**

**Cause:** HAE file overwrote data for that day, but the file doesn't contain that day's data.

**Solution:** Import the HAE file that contains that day (usually the file named for that day or the next day).

### **Problem: Data doesn't match HAE JSON**

**Cause:** Wrong file imported, or file hasn't synced from Google Drive.

**Solution:**
1. Check file timestamp: `ls -lh '/path/to/file.json'`
2. If old, force Google Drive sync or check "local storage full" error
3. Re-import with `overwrite` mode

### **Problem: Frontend shows old data after refresh**

**Cause:** Weekly summary query was returning hardcoded placeholders (fixed in commit `620f70d`).

**Solution:**
1. Restart backend: `lsof -ti:3001 | xargs kill -9 && cd backend && npm start`
2. Hard refresh browser: Cmd+Shift+R
3. Check API directly: `curl http://localhost:3001/api/weekly?weeks=1`

### **Problem: Cascading NULLs after overwrites**

**Cause:** Each HAE file contains 2 days, so overwriting clears both days.

**Solution:** Import all affected files in chronological order (see Option 1 above).

---

## 📝 HAE File Path (macOS)

```bash
HAE_DIR='/Users/markhill/Library/CloudStorage/GoogleDrive-mark@buildwhatsmissing.com/My Drive/Health Auto Export/Apple Health Exports'

# List recent files
ls -lt "$HAE_DIR" | grep 2025-10 | head -10

# Import a file
python etl/hae_import.py "$HAE_DIR/HealthAutoExport-2025-10-05.json" overwrite
```

---

## 🎓 Best Practices

1. **Always import in chronological order** (oldest to newest)
2. **Import at least 2 consecutive days** to avoid gaps
3. **Check for NULLs** after each import
4. **Materialize immediately** after import
5. **Verify via API** before trusting frontend display

---

## 🔗 Related Issues

- **Commit `620f70d`** - Fixed hardcoded `total_intake: 0` in weekly query
- **Timezone issues** - See `docs/TIMEZONE-POLICY.md`
- **Cron job failures** - See `docs/CRON-JOB-FIXES-2025-09-30.md`

---

**Last Updated:** October 5, 2025

