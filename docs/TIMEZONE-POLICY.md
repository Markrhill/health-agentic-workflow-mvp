# Timezone Policy: Configurable Timezone (Default: Pacific)

## 🎯 **Core Principle**

**This application uses a single timezone configured via `.env`:**

```bash
HEALTH_TZ="America/Los_Angeles"  # Pacific Time (PDT/PST)
```

All dates must be consistent across:
- Backend API responses
- Frontend display
- Database queries
- HAE file processing
- User's iPhone/Apple Health data

## ❌ **NEVER Use These**

```javascript
// ❌ BANNED - Returns UTC date
new Date().toISOString().split('T')[0]

// ❌ BANNED - Uses UTC date
new Date('2025-10-05')  // Parses as UTC midnight, shifts to Oct 4 in Pacific

// ❌ BANNED - UTC methods
date.getUTCFullYear()
date.getUTCMonth()
date.getUTCDate()
date.toISOString()  // Unless you really need UTC for API timestamps
```

## ✅ **ALWAYS Use These**

### **Frontend (React)**

```javascript
// ✅ Import timezone utilities
import { parseLocalDate, toLocalDateString, formatDisplayDate, getWeekEnd, getTodayLocal } from '../utils/timezone';

// ✅ Parse YYYY-MM-DD as local date
const date = parseLocalDate('2025-10-05');

// ✅ Convert Date to YYYY-MM-DD (local)
const dateString = toLocalDateString(new Date());

// ✅ Get today's date (local)
const today = getTodayLocal();

// ✅ Format for display
const displayDate = formatDisplayDate('2025-10-05'); // "Oct 5"

// ✅ Calculate week end (Monday + 6 days)
const sunday = getWeekEnd('2025-09-30'); // "2025-10-06"
```

**See:** `frontend/src/utils/timezone.js` for all available utilities.

### **Backend (Node.js)**

```javascript
// ✅ Get today's date using configured timezone
const timezone = process.env.HEALTH_TZ || 'America/Los_Angeles';
const today = new Date().toLocaleDateString('en-CA', { timeZone: timezone }); // "2025-10-05"

// ✅ For API timestamps (UTC is OK here - it's for logging, not user-facing dates)
timestamp: new Date().toISOString()
```

**Configuration:** Set `HEALTH_TZ` in `.env` to control timezone across all backend operations.

### **Database (PostgreSQL)**

```sql
-- ✅ Dates are stored as DATE type (no timezone)
-- These are interpreted as local dates by the application

-- ✅ Get today's date (server timezone should match Pacific)
SELECT CURRENT_DATE;

-- ✅ Date arithmetic
SELECT fact_date + INTERVAL '7 days' FROM daily_facts;
```

## 🏗️ **Architecture**

### **Environment Configuration**

```bash
# .env
HEALTH_TZ="America/Los_Angeles"  # IANA timezone identifier
```

All timezone-sensitive operations reference this single source of truth.

### **Component Responsibilities**

1. **Backend API** (`backend/routes/api.js`)
   - Reads `HEALTH_TZ` from environment
   - Uses `toLocaleDateString('en-CA', { timeZone })` for date calculations
   - Passes dates to shell scripts and Python ETL

2. **Frontend** (`frontend/src/utils/timezone.js`)
   - Provides centralized date utilities
   - Assumes browser is in same timezone as backend (Bay Area)
   - No API call needed for timezone (reduces latency)

3. **Database**
   - Stores dates as `DATE` type (no timezone info)
   - Application interprets all dates in configured timezone

## 🐛 **Why This Matters**

### **The Problem**

UTC is 7-8 hours ahead of Pacific Time:
- **4pm PDT** = **11pm UTC** (same day)
- **5pm PDT** = **12am UTC** (**next day**)

After 4-5pm PDT, naive UTC usage causes:
- `toISOString().split('T')[0]` returns **tomorrow's date**
- Refresh button tries to import non-existent HAE file for tomorrow
- Week calculations show wrong dates
- User sees Oct 5, system thinks Oct 6

### **The Solution**

1. **Single source of truth:** `HEALTH_TZ` in `.env`
2. **Centralized utilities:** `frontend/src/utils/timezone.js`
3. **Explicit timezone handling:** `toLocaleDateString('en-CA', { timeZone })`
4. **No UTC for dates:** Reserve UTC for API timestamps only

## 📋 **Audit Checklist**

When adding date logic, verify:

- [ ] No `toISOString()` for date calculations
- [ ] No `new Date(string)` for YYYY-MM-DD strings
- [ ] Use `parseLocalDate()` / `toLocalDateString()` utilities
- [ ] Test after 5pm PDT (when UTC rolls over)
- [ ] Check browser console for correct dates
- [ ] Verify refresh button uses correct date

## 🎓 **For Future Developers**

If you see a date bug after 4-5pm:
1. It's probably a timezone issue
2. Search for `toISOString` or `getUTC`
3. Replace with local date utilities
4. Test at 8pm PDT (3am UTC) to verify fix

## 📝 **Implementation Status**

✅ **Environment Configuration**
- `.env` already had `HEALTH_TZ="America/Los_Angeles"`

✅ **Backend** - Refactored (Oct 5, 2025)
- `/api/refresh` endpoint uses `HEALTH_TZ` from `.env`
- Uses `toLocaleDateString('en-CA', { timeZone })` for proper timezone handling

✅ **Frontend** - Refactored (Oct 5, 2025)
- Created `frontend/src/utils/timezone.js` with centralized utilities
- All components import from shared utility module
- Week calculations use `getWeekEnd()` helper
- Chart date labels use `formatDisplayDate()` helper

✅ **Database** - No changes needed
- DATE columns are timezone-agnostic
- Queries treat dates as local

✅ **Documentation** - Complete
- `docs/TIMEZONE-POLICY.md` provides comprehensive guidance

---

## 🎓 **Benefits of This Architecture**

1. **Single source of truth** - Change `HEALTH_TZ` in one place to support any timezone
2. **Centralized utilities** - All date logic in `frontend/src/utils/timezone.js`
3. **Testable** - Utilities can be unit tested independently
4. **Maintainable** - Future developers see imports and know where to look
5. **Flexible** - Could extend to support multiple timezones if needed

**Configured timezone: `America/Los_Angeles` (Pacific Time)**

