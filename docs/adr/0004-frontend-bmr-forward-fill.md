# ADR-0004: Frontend BMR Forward-Fill for Net Calorie Resilience

**Status**: Accepted  
**Date**: 2025-10-03  
**Decision Makers**: System Architect  
**Related**: Daily series materialization, Weekly metrics display

---

## Context

The system displays daily net calories in the Weekly Metrics UI, calculated as:

```
Net Calories = Intake - Compensated Exercise - BMR
```

### Problem

When body composition data is missing (no weigh-in), the backend skips materialization for that day, resulting in:
- `daily_series_materialized` has no row for that date
- Backend query returns `NULL` for `bmr_kcal`
- Frontend displays **0 net calories** (misleading)

This creates fragility because:
1. **Withings API is unreliable** (token expires every 3 hours, no working refresh)
2. **HAE may be delayed** (Google Drive sync, file timing)
3. **User may forget to weigh in** occasionally
4. **BMR changes slowly** (~2-4 kcal/day for typical LBM changes of 0.1-0.2 kg/day)

### Key Insight

Unlike body composition (which responds slowly to sustained discipline), **intake and exercise are highly controllable daily behaviors**. Users need immediate feedback on these controllable metrics, even when body comp data is temporarily missing.

---

## Decision

**Forward-fill BMR in the React frontend** when calculating net calories for display purposes only.

### Implementation

In `HealthMVP.jsx`, during the `dailyData` transformation:

```javascript
// Forward-fill BMR when missing (due to missing body comp) to calculate net_kcal
let lastKnownBmr = null;

return dailyData.map(day => {
  const bmr = day.bmr_kcal || lastKnownBmr;
  if (day.bmr_kcal) lastKnownBmr = day.bmr_kcal;
  
  // Calculate net_kcal if missing but we have intake and BMR
  let netKcal = day.net_kcal;
  if (!netKcal && day.intake_kcal && bmr) {
    netKcal = day.intake_kcal - (day.compensated_exercise_kcal || 0) - bmr;
  }
  
  return {
    ...day,
    netKcal: netKcal ? Math.round(parseFloat(netKcal)) : null
  };
});
```

---

## Rationale

### Why Frontend, Not Backend?

**Separation of concerns:**
- **Backend = Source of truth**: Stores only actual observed data
  - No body comp → No materialization
  - Clean, auditable data pipeline
  - Clear data provenance
  
- **Frontend = Display logic**: Handles presentation and user experience
  - Forward-fill BMR for net calorie calculation
  - Provides immediate feedback on controllable behaviors
  - Keeps backend clean and simple

### Why Not Store Imputed BMR in Database?

**Rejected alternatives:**

1. **Backend forward-fill with `body_comp_imputed` flag**
   - ❌ Comingles actual vs. estimated data in materialized table
   - ❌ Adds schema complexity
   - ❌ Blurs intake imputation vs. BMR estimation
   
2. **Separate `daily_bmr_estimates` table**
   - ❌ Major architectural change
   - ❌ More complex maintenance
   - ❌ Overkill for ~2-4 kcal error

3. **Query-time COALESCE with subquery**
   - ❌ Complex SQL (nested subqueries for last known LBM)
   - ❌ Performance impact
   - ❌ Still doesn't help with missing fat_mass_ema display

### Why This Works

- **BMR is stable**: 0.1-0.2 kg LBM change/day → ~2-4 kcal BMR error (0.1% of typical 1,600 kcal BMR)
- **Controllable feedback**: Users see immediate net calorie impact of their daily intake/exercise choices
- **Simple implementation**: 8 lines of code in one file
- **No schema changes**: Backend remains clean
- **Transparent**: Frontend calculates from known data, doesn't fabricate measurements

---

## Consequences

### Positive

✅ **Resilient to missing weigh-ins**: System continues to provide useful feedback  
✅ **Clean architecture**: Backend stores actuals, frontend handles display  
✅ **Immediate feedback**: Users see net calories for controllable behaviors (intake/exercise)  
✅ **Accurate enough**: ~2-4 kcal error negligible vs. typical 100+ kcal daily measurement noise  
✅ **Simple to maintain**: All logic in one place (React component)  
✅ **No data pollution**: Backend materialized table stays clean  

### Negative

⚠️ **Net calories displayed with stale BMR** (but error is physiologically negligible)  
⚠️ **Fat mass still shows as missing** (correctly - we don't forward-fill it)  
⚠️ **Frontend calculation duplicates backend logic** (Intake - Exercise - BMR)  

### Trade-offs Accepted

We accept that:
- Net calories displayed may use slightly stale BMR (acceptable: ~2-4 kcal error)
- Frontend duplicates the net calorie calculation formula (simple formula, low maintenance risk)
- Fat mass gaps remain visible (correct: we only forward-fill BMR, not body comp)

---

## Validation

### Test Scenarios

1. **Normal operation**: All data present → Net calories from backend materialization
2. **Missing weigh-in**: No body comp → Net calories calculated with forward-filled BMR
3. **Multi-day gap**: Multiple days without weigh-in → BMR forward-fills across gap
4. **Missing intake**: No intake → Net calories shows as NULL (correct: can't calculate)

### Success Criteria

- Weekly Metrics shows meaningful net calories even with occasional missing weigh-ins
- All actual measurements (intake, exercise, protein, fiber, fat mass) remain unimputed
- Backend materialized table contains only actual observed data

---

## Related Decisions

- **ADR-0001**: Parameter materialized series pattern (backend stores actuals only)
- **ADR-0003**: Kalman filter for body composition smoothing (separates signal from noise)
- **Future**: If BMR estimation becomes more complex (e.g., incorporating activity level, temperature, etc.), consider moving to backend with explicit estimation table

---

## Notes

- BMR formula: `BMR = bmr0 + k_lbm * lbm_ema` where `lbm_ema = weight - fat_mass_ema`
- Typical user BMR: ~1,600 kcal/day
- Typical LBM change: 0.1-0.2 kg/day max → 2-4 kcal BMR change
- This decision prioritizes **actionable daily feedback** over perfect data completeness

