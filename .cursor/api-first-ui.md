# API-First UI Development Rule

## MANDATORY: Database-First Frontend Development

### Rule Violation Example (2025-09-18)
- **Error**: React component built with mock data (`avgFatMass`) 
- **Reality**: API returns database fields (`avg_fat_mass_ema_kg`)
- **Result**: Runtime errors, integration failures
- **Root Cause**: UI developed against imaginary data structure

## Required Process for All Frontend Development

### Step 1: Query Actual API First (MANDATORY)
```bash
# NEVER build UI components without this step
curl http://localhost:5000/api/endpoint | jq '.[0]' > actual-response.json
```

### Step 2: Document Real Data Structure
```javascript
// REQUIRED: Include actual API response in component file
/*
ACTUAL API RESPONSE STRUCTURE:
{
  "avg_fat_mass_ema_kg": 19.33,
  "avg_net_kcal": 23,
  "total_intake_kcal": 6681,
  "total_adj_exercise_kcal": 0,
  "imputed_days_count": 2,
  "params_version_used": "v2025_07_31"
}
*/
```

### Step 3: Use Real Field Names
```javascript
// CORRECT: Use actual database field names
const fatMass = weeklyData.avg_fat_mass_ema_kg;
const netKcal = weeklyData.avg_net_kcal;

// WRONG: Never use fictional field names
const fatMass = weeklyData.avgFatMass; // This field doesn't exist!
```

## Factory Enforcement Rules

### For AI Systems (Claude, Cursor, etc.)
1. **NEVER create mock data** unless it exactly matches database schema
2. **ALWAYS query actual API endpoints** before UI development
3. **VERIFY field names** match database columns
4. **DOCUMENT API response structure** in component comments

### Validation Checklist
- [ ] Actual API endpoint queried and response documented
- [ ] All field names verified against database schema  
- [ ] Component tested against real API data, not mock data
- [ ] TypeScript interfaces generated from actual responses (if applicable)

### Red Flags (Auto-Reject)
- Component uses field names not in database schema
- Mock data that doesn't match API response structure
- UI built without actual API endpoint testing
- Generic/placeholder data structures

## Integration with safe-backfill.md
- Database queries are single source of truth
- UI components must consume actual database field names
- No hardcoded values OR fictional field names
- Parameter table authority extends to frontend data contracts

## Cursor Prompt Template
```
Before creating any React component:
1. Show me the actual API response from [endpoint]
2. Use the exact field names from that response
3. Include the API response structure as a comment
4. Test the component against real data, not mock data
```

## Violation Recovery
When API-first rule violations are detected:
1. **STOP** frontend development immediately
2. **QUERY** actual API endpoint and document response
3. **FIX** all field name mismatches
4. **TEST** component with real API data
5. **DOCUMENT** the corrected data structure

This rule prevents integration failures by anchoring all UI development to actual database reality rather than imaginary data structures.
