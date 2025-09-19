# API Schema Documentation

## Overview
This document provides the complete schema for all Health Agentic Workflow MVP API endpoints. Use this as the single source of truth for frontend development.

## Base URL
- **Development**: `http://localhost:3001/api`
- **Production**: TBD

## Authentication
Currently no authentication required. All endpoints are publicly accessible.

---

## Endpoints

### 1. GET /api/parameters
Get current model parameters.

**Response Schema:**
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

**Field Descriptions:**
- `params_version`: String - Version identifier for parameters
- `effective_start_date`: ISO 8601 date - When these parameters became effective
- `alpha_fm`: String (numeric) - Fat mass EMA smoothing factor
- `alpha_lbm`: String (numeric) - Lean body mass EMA smoothing factor
- `c_exercise_comp`: String (numeric) - Exercise compensation factor
- `bmr0_kcal`: String (numeric) - Base metabolic rate in kcal
- `k_lbm_kcal_per_kg`: String (numeric) - LBM metabolic rate coefficient
- `kcal_per_kg_fat`: String (numeric) - Energy density of fat tissue

---

### 2. GET /api/weekly
Get weekly aggregated health data.

**Query Parameters:**
- `limit` (optional): Number of weeks to return (default: 10)

**Response Schema:**
```json
[
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
]
```

**Field Descriptions:**
- `week_start_monday`: ISO 8601 date - Monday of the week
- `days_in_week`: String (numeric) - Number of days with data in this week
- `avg_fat_mass_ema`: String (numeric) - Average fat mass EMA in kg
- `avg_net_kcal`: String (numeric) - Average net calories per day
- `total_intake`: String (numeric) - Total calories consumed in week
- `total_adj_exercise`: String (numeric) - Total compensated exercise calories
- `imputed_days`: String (numeric) - Number of days with imputed data
- `params_version`: String - Parameter version used for calculations
- `computed_at`: ISO 8601 timestamp - When data was computed

---

### 3. GET /api/daily/:startDate/:endDate
Get daily health data for a date range.

**Path Parameters:**
- `startDate`: YYYY-MM-DD format start date
- `endDate`: YYYY-MM-DD format end date

**Response Schema:**
```json
[
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
]
```

**Field Descriptions:**
- `fact_date`: ISO 8601 date - Date of the measurement
- `day_of_week`: String (numeric) - Day of week (0=Sunday, 1=Monday, etc.)
- `day_name`: String - Human-readable day name
- `fat_mass_ema_lbs`: String (numeric) - Fat mass EMA in pounds
- `net_kcal`: Number - Net calories (intake - compensated_exercise - bmr)
- `intake_kcal`: String (numeric) - Calories consumed
- `raw_exercise_kcal`: Number - Raw Garmin exercise calories
- `compensated_exercise_kcal`: Number - Compensated exercise calories
- `intake_is_imputed`: Boolean - Whether intake data was imputed
- `imputation_method`: String|null - Method used for imputation
- `params_version_used`: String - Parameter version used for calculations
- `fat_mass_uncertainty_lbs`: String|null - Fat mass uncertainty estimate
- `raw_fat_mass_lbs`: String|null - Raw fat mass measurement
- `bmr_kcal`: Number - Basal metabolic rate
- `alpha_fm`: String (numeric) - Fat mass EMA smoothing factor
- `compensation_factor`: String (numeric) - Exercise compensation factor
- `kcal_per_kg_fat`: String (numeric) - Energy density of fat tissue

---

### 4. GET /api/summary
Get health metrics summary (currently failing - needs debugging).

**Response Schema:**
```json
{
  "error": "Failed to fetch health summary"
}
```

---

## Data Type Conversion Requirements

### String Fields Requiring parseFloat()
All numeric fields from PostgreSQL are returned as strings and require conversion:

```javascript
// Weekly endpoint
parseFloat(week.avg_fat_mass_ema || 0)
parseFloat(week.avg_net_kcal || 0)
parseFloat(week.total_intake || 0)
parseFloat(week.total_adj_exercise || 0)
parseInt(week.days_in_week || 0)
parseInt(week.imputed_days || 0)

// Daily endpoint
parseFloat(day.fat_mass_ema_lbs || 0)
parseFloat(day.intake_kcal || 0)
parseFloat(day.fat_mass_uncertainty_lbs || 0)
parseFloat(day.raw_fat_mass_lbs || 0)

// Parameters endpoint
parseFloat(params.alpha_fm || 0)
parseFloat(params.alpha_lbm || 0)
parseFloat(params.c_exercise_comp || 0)
parseFloat(params.bmr0_kcal || 0)
parseFloat(params.k_lbm_kcal_per_kg || 0)
parseFloat(params.kcal_per_kg_fat || 0)
```

### Display Formatting
```javascript
// For display with decimal places
parseFloat(value || 0).toFixed(1)  // 1 decimal place
parseFloat(value || 0).toFixed(2)  // 2 decimal places

// For display as whole numbers
Math.round(parseFloat(value || 0))

// For display with thousands separators
parseFloat(value || 0).toLocaleString()
```

## Field Mapping Differences

| Concept | Weekly Endpoint | Daily Endpoint | Parameters Endpoint |
|---------|----------------|----------------|-------------------|
| Parameter Version | `params_version` | `params_version_used` | `params_version` |
| Fat Mass | `avg_fat_mass_ema` (kg) | `fat_mass_ema_lbs` (lbs) | N/A |
| Imputed Data | `imputed_days` (count) | `intake_is_imputed` (boolean) | N/A |
| Exercise | `total_adj_exercise` | `raw_exercise_kcal`, `compensated_exercise_kcal` | N/A |
| Net Calories | `avg_net_kcal` | `net_kcal` | N/A |

## Error Handling

All endpoints may return errors. Handle them gracefully:

```javascript
try {
  const data = await apiRequest('/endpoint');
  // Process data
} catch (error) {
  if (error instanceof ApiError) {
    console.error(`API Error ${error.status}: ${error.message}`);
  } else {
    console.error('Network error:', error.message);
  }
}
```

## Version History

- **v1.0.0** (2025-09-18): Initial API schema documentation
- Schema based on actual API responses from development environment
