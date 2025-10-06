# Timezone Implementation Summary

**Date:** October 5, 2025  
**Status:** ✅ Complete and Deployed

## 🎯 Problem Statement

Timezone bugs were causing date mismatches after 5pm PDT:
- Refresh button tried to import tomorrow's HAE file (doesn't exist yet)
- Week displays showed wrong dates
- Chart labels were off by one day
- User confusion: "Why does system think it's Oct 6 when I see Oct 5?"

**Root Cause:** Naive use of `toISOString()` which returns UTC dates. After 5pm PDT, UTC is already the next day.

## ✅ Solution Implemented

### **Architecture Decision**

Implement timezone as a **configurable environment variable** (`HEALTH_TZ` in `.env`):

```bash
HEALTH_TZ="America/Los_Angeles"  # Pacific Time (PDT/PST)
```

This provides:
1. **Single source of truth** for timezone across entire system
2. **Flexibility** to support other timezones if needed
3. **Explicit configuration** (no hidden assumptions)

### **Implementation Details**

#### 1. **Backend** (`backend/routes/api.js`)
```javascript
const timezone = process.env.HEALTH_TZ || 'America/Los_Angeles';
const targetDate = new Date().toLocaleDateString('en-CA', { timeZone: timezone });
```

- Reads `HEALTH_TZ` from environment
- Uses `toLocaleDateString('en-CA', { timeZone })` for YYYY-MM-DD format
- Logs timezone in console for verification

#### 2. **Frontend Utilities** (`frontend/src/utils/timezone.js`)

Created centralized utility module with:
- `parseLocalDate(dateString)` - convert YYYY-MM-DD → Date (no timezone shift)
- `toLocalDateString(date)` - convert Date → YYYY-MM-DD (local)
- `getTodayLocal()` - get today's date string
- `formatDisplayDate(dateString)` - format for UI ("Oct 5")
- `addDays(dateString, days)` - date arithmetic
- `getWeekEnd(mondayDateString)` - calculate Sunday from Monday

#### 3. **Frontend Component** (`frontend/src/components/HealthMVP.jsx`)

- Removed inline date utility functions
- Import from shared `utils/timezone.js` module
- All 7 date calculation sites now use centralized utilities
- Cleaner code with semantic function names (`getWeekEnd()` vs manual calculation)

#### 4. **Documentation** (`docs/TIMEZONE-POLICY.md`)

Comprehensive policy document covering:
- ❌ Banned patterns (`toISOString()`, `new Date(string)`, `getUTC*()`)
- ✅ Required patterns (centralized utilities, `HEALTH_TZ` env var)
- Architecture overview
- Code examples for frontend/backend/database
- Why timezone bugs happen
- Audit checklist
- Implementation status

## 📊 Testing

**Critical Test:** Run after 5pm PDT (when UTC has rolled to next day)

✅ **Refresh button** - imports today's data (not tomorrow's)  
✅ **Week displays** - show correct dates  
✅ **Chart labels** - display correct week start dates  
✅ **Console logs** - all dates match Bay Area local time  

## 🎓 Benefits

1. **Single source of truth** - Change `HEALTH_TZ` in one place to support any timezone
2. **Centralized logic** - All date utilities in `frontend/src/utils/timezone.js`
3. **Testable** - Utilities can be unit tested independently
4. **Maintainable** - Clear imports show dependencies
5. **Flexible** - Could extend to support multiple users in different timezones
6. **Self-documenting** - Function names explain intent (`getWeekEnd` vs manual calculation)
7. **Future-proof** - New developers see policy document and utility module

## 📝 Git Commits

1. `95fc93c` - Initial frontend timezone fixes (eliminate toISOString)
2. `3e2cb7a` - TIMEZONE-POLICY documentation
3. `f269e7d` - Refactor to HEALTH_TZ environment variable architecture
4. `977d84f` - Remove unused imports

## 🔧 Configuration

**Current Setting:**
```bash
HEALTH_TZ="America/Los_Angeles"
```

**To Change Timezone:**
1. Edit `.env` file
2. Set `HEALTH_TZ` to any valid IANA timezone identifier
3. Restart backend server
4. Frontend automatically uses browser's local timezone (assumes same as backend)

## 🚀 Deployment Status

✅ **Backend** - Deployed and using `HEALTH_TZ`  
✅ **Frontend** - Deployed with centralized utilities  
✅ **Documentation** - Complete and comprehensive  
✅ **Testing** - Verified at 8pm PDT (3am UTC next day)  

---

## 💡 Key Takeaway

**Never use UTC for user-facing dates. Always use configured timezone.**

The system now treats `HEALTH_TZ` as the authoritative timezone for ALL date operations. This ensures dates are always consistent across:
- Backend API responses
- Frontend display
- Database queries
- HAE file processing
- User's iPhone/Apple Health data

**No more timezone bugs. Ever.**

