# API Schema Consistency Rule

## Factory Rule: API Schema Consistency
Before building any component that uses multiple endpoints:

1. **Document ALL endpoint schemas being used**
2. **Verify field naming consistency across endpoints**
3. **Create field mapping documentation if names differ**
4. **Component must handle schema differences explicitly**

## Mandatory Pre-Development Steps

### 1. Schema Documentation
Document the exact field names and types for each endpoint:

```markdown
## API Endpoint Schemas

### GET /api/weekly
```json
{
  "week_start_monday": "2025-08-26T07:00:00.000Z",
  "days_in_week": "4",
  "avg_fat_mass_ema": "19.3250000000000000",
  "avg_net_kcal": "23.2500000000000000",
  "total_intake": "6681",
  "total_adj_exercise": "0",
  "imputed_days": "2",
  "params_version": "v2025_07_31",
  "computed_at": "2025-09-17T22:30:17.431Z"
}
```

### GET /api/daily/:startDate/:endDate
```json
{
  "fact_date": "2025-07-28T07:00:00.000Z",
  "day_of_week": "1",
  "day_name": "Monday   ",
  "fat_mass_ema_lbs": "47.17225414",
  "net_kcal": -554,
  "intake_kcal": "1457.00",
  "raw_exercise_kcal": 471,
  "compensated_exercise_kcal": 396,
  "intake_is_imputed": false,
  "imputation_method": null,
  "params_version_used": "v2025_01_01",
  "fat_mass_uncertainty_lbs": null,
  "raw_fat_mass_lbs": null,
  "bmr_kcal": 1615,
  "alpha_fm": "0.25",
  "compensation_factor": "0.15",
  "kcal_per_kg_fat": "9675"
}
```

### GET /api/parameters
```json
{
  "params_version": "v2025_07_31",
  "effective_start_date": "2025-07-31T07:00:00.000Z",
  "alpha_fm": "0.25",
  "alpha_lbm": "0.10",
  "c_exercise_comp": "0.15",
  "bmr0_kcal": "728",
  "k_lbm_kcal_per_kg": "12.1",
  "kcal_per_kg_fat": "9675"
}
```
```

### 2. Field Mapping Documentation
Document any field name differences between endpoints:

```markdown
## Field Mapping Differences

| Concept | Weekly Endpoint | Daily Endpoint | Parameters Endpoint |
|---------|----------------|----------------|-------------------|
| Parameter Version | `params_version` | `params_version_used` | `params_version` |
| Fat Mass | `avg_fat_mass_ema` (kg) | `fat_mass_ema_lbs` (lbs) | N/A |
| Imputed Days | `imputed_days` | `intake_is_imputed` (boolean) | N/A |
| Exercise | `total_adj_exercise` | `raw_exercise_kcal`, `compensated_exercise_kcal` | N/A |
```

### 3. Data Type Documentation
Document expected data types and conversion requirements:

```markdown
## Data Type Requirements

### String Fields (require parseFloat())
- All numeric fields from PostgreSQL are returned as strings
- Apply `parseFloat(field || 0)` before mathematical operations
- Apply `.toFixed(n)` for display formatting

### Nullable Fields
- `fat_mass_uncertainty_lbs` - can be null
- `raw_fat_mass_lbs` - can be null
- `imputation_method` - can be null

### Boolean Fields
- `intake_is_imputed` - boolean, no conversion needed
```

## Component Development Rules

### 1. Explicit Field Mapping
```javascript
// WRONG - assumes consistent field names
const fatMass = currentWeek.avg_fat_mass_ema_kg;

// CORRECT - explicit field mapping with documentation
const fatMass = parseFloat(currentWeek.avg_fat_mass_ema || 0); // Weekly: avg_fat_mass_ema (kg)
```

### 2. Type-Safe Data Access
```javascript
// WRONG - no type conversion
{day.fat_mass_ema_lbs?.toFixed(1)}

// CORRECT - explicit type conversion
{parseFloat(day.fat_mass_ema_lbs || 0).toFixed(1)}
```

### 3. Schema Difference Handling
```javascript
// Handle different field names for same concept
const paramVersion = weeklyData.params_version || dailyData.params_version_used;
const imputedCount = parseInt(weeklyData.imputed_days || 0);
const isImputed = dailyData.intake_is_imputed;
```

## Validation Checklist

Before deploying any component using multiple API endpoints:

- [ ] All endpoint schemas documented with actual field names
- [ ] Field mapping differences documented
- [ ] Data type conversion requirements documented
- [ ] Component handles all schema differences explicitly
- [ ] No assumptions about field name consistency
- [ ] All numeric fields use parseFloat() with null fallback
- [ ] Display formatting applied after type conversion

## Red Flags

Stop development if you see:
- Hardcoded field names without schema documentation
- Missing type conversion for numeric fields
- Assumptions about field name consistency
- Components that work with one endpoint but fail with others
- No explicit handling of schema differences

## Enforcement

This rule is mandatory for:
- Any component using 2+ API endpoints
- Data visualization components
- Form components with API integration
- Dashboard components with multiple data sources

## Example: HealthMVP Component

The HealthMVP component demonstrates proper schema consistency handling:

```javascript
// Weekly data fields (from /api/weekly)
const fatMass = parseFloat(currentWeek.avg_fat_mass_ema || 0); // kg
const netCalories = Math.round(parseFloat(currentWeek.avg_net_kcal || 0));
const imputedDays = parseInt(currentWeek.imputed_days || 0);
const paramVersion = currentWeek.params_version;

// Daily data fields (from /api/daily)
const fatMassLbs = parseFloat(day.fat_mass_ema_lbs || 0); // lbs
const netCal = Math.round(parseFloat(day.net_kcal || 0));
const intake = Math.round(parseFloat(day.intake_kcal || 0));
const rawExercise = Math.round(parseFloat(day.raw_exercise_kcal || 0));
const compensatedExercise = Math.round(parseFloat(day.compensated_exercise_kcal || 0));
const isImputed = day.intake_is_imputed;
const paramVersionUsed = day.params_version_used;

// Parameters data fields (from /api/parameters)
const alphaFm = parseFloat(parameters.alpha_fm || 0);
const compensationFactor = parseFloat(parameters.c_exercise_comp || 0);
const energyDensity = parseFloat(parameters.kcal_per_kg_fat || 0);
```

This approach ensures components work reliably across all API endpoints while maintaining clear documentation of schema differences.
