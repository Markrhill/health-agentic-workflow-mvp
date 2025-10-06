# Timezone Policy: Pacific Time ONLY

## 🎯 **Core Principle**

**This application operates EXCLUSIVELY in Pacific Time (PDT/PST).**

The user lives in the Bay Area. All dates must match what they see on their iPhone, calendar, and life.

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
// ✅ Parse YYYY-MM-DD as LOCAL date
const parseLocalDate = (dateString) => {
  const [year, month, day] = dateString.split('-').map(Number);
  return new Date(year, month - 1, day);
};

// ✅ Convert Date to YYYY-MM-DD (local)
const toLocalDateString = (date) => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

// ✅ Get today's date (local)
const today = toLocalDateString(new Date());
```

### **Backend (Node.js)**

```javascript
// ✅ Get today's date (local)
const now = new Date();
const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;

// ✅ For API timestamps (UTC is OK here)
timestamp: new Date().toISOString()
```

### **Database (PostgreSQL)**

```sql
-- ✅ Dates are stored as DATE type (no timezone)
-- These are interpreted as local dates by the application

-- ✅ Get today's date (server timezone should match Pacific)
SELECT CURRENT_DATE;

-- ✅ Date arithmetic
SELECT fact_date + INTERVAL '7 days' FROM daily_facts;
```

## 🐛 **Why This Matters**

### **The Problem**

UTC is 7-8 hours ahead of Pacific Time:
- **4pm PDT** = **11pm UTC** (same day)
- **5pm PDT** = **12am UTC** (**next day**)

After 4-5pm PDT:
- `toISOString().split('T')[0]` returns **tomorrow's date**
- Refresh button tries to import non-existent HAE file for tomorrow
- Week calculations show wrong dates
- User sees Oct 5, system thinks Oct 6

### **The Solution**

**Use local date methods everywhere.**

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

✅ **Backend** - Fixed in commit `9792441` (Oct 5, 2025)
- `/api/refresh` endpoint uses local date

✅ **Frontend** - Fixed in commit `95fc93c` (Oct 5, 2025)
- All date parsing/formatting uses local utilities
- Week calculations use local dates
- Chart date labels use local dates

✅ **Database** - No changes needed
- DATE columns are timezone-agnostic
- Queries treat dates as local

---

**Remember: The user is in the Bay Area. Pacific Time is the ONLY time.**

