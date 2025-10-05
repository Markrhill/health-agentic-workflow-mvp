# Energy Balance Parameter Estimation Challenge

## The Problem

We're trying to estimate parameters for a simple energy balance model:

```
ΔFat (kg) = [Intake (kcal) - BMR (kcal/day) × days - (1-c) × Workout (kcal)] / α
```

Where:
- **α** (alpha): Energy density of fat tissue (expected: 7,000-12,000 kcal/kg)
- **c**: Exercise compensation factor (expected: 0.0-0.5, i.e., 0-50% eaten back)
- **BMR**: Basal metabolic rate (expected: 1,200-2,200 kcal/day)

## What We've Tried

1. **7-day windows**: Too noisy (R² ≈ 0.01)
2. **14-day windows**: Better (R² ≈ 0.15) but still poor
3. **2022 only**: Best fit (R² ≈ 0.49) but parameters implausible:
   - α = 19,651 kcal/kg (too high)
   - c = -0.725 (negative compensation - impossible!)
4. **Fixed BMR**: Doesn't help - α still negative
5. **Orthogonalization**: Removes intake-workout correlation but doesn't fix parameters
6. **Kalman filtering**: Successfully removes BIA measurement noise

## Current Status

- **Best predictive performance**: 2022 data, MAE = 0.232 kg per 14 days
- **Problem**: Even when model predicts well, parameters are physiologically implausible
- **Hypothesis**: Parameters are time-varying (non-stationary) or model is mis-specified

## The Data

**File**: `comprehensive_daily_data_for_analysis.csv`

### Coverage (2021-01-01 to 2025-09-29)
- **1,733 days** total
- **100% intake coverage** (imputation metadata included)
- **75.6% fat mass coverage** (raw BIA measurements)
- **99.9% Kalman-filtered fat mass** (smoothed to remove measurement noise)
- **54% workout days** (rest days = 0 kcal, not NULL)

### Key Variables

**Energy Balance Inputs:**
- `intake_kcal`: Daily calorie intake
- `protein_g`, `carbs_g`, `fat_g`, `fiber_g`: Macronutrients
- `tef_kcal`: Thermic effect of food (pre-calculated)
- `workout_kcal`: Exercise energy expenditure (0 = rest day)

**Body Composition:**
- `fat_mass_raw_kg`: Raw BIA fat mass (noisy, 75% coverage)
- `fat_mass_kalman_kg`: Kalman-filtered fat mass (smoothed, 99.9% coverage)
- `fat_mass_kalman_variance`: Uncertainty in Kalman estimate
- `lean_mass_kg`: Fat-free mass (muscle + bone + water)
- `weight_kg`: Total body weight

**Data Quality Flags:**
- `is_intake_imputed`: Whether intake was imputed (False = observed)
- `nutrition_is_observed`: Whether macros were logged
- `has_fat_mass`: Whether raw BIA measurement exists
- `has_workout`: Whether exercise occurred that day

### Data Quality by Year

| Year | Days | Intake | Fat Mass | Workouts |
|------|------|--------|----------|----------|
| 2021 | 365  | 100%   | 72%      | 44%      |
| 2022 | 365  | 100%   | 67%      | 64%      |
| 2023 | 365  | 100%   | 77%      | 56%      |
| 2024 | 366  | 100%   | 83%      | 59%      |
| 2025 | 272  | 100%   | 80%      | 47%      |

**2022 shows the best model fit** - most consistent training/diet period.

## What We Need

A data scientist who can:

1. **Diagnose why the simple linear model fails** to produce plausible parameters
2. **Identify if there are systematic measurement errors** (intake under-reporting? workout over-estimation?)
3. **Determine if parameters are time-varying** and how to model that
4. **Suggest alternative model structures** (non-linear? mixed effects? state-space?)
5. **Quantify uncertainty** in parameter estimates

## Questions to Answer

1. **Is the energy balance equation fundamentally correct** for this individual?
2. **Are the parameters stationary** or do they vary over time/training phases?
3. **What's the signal-to-noise ratio** in the fat mass changes?
4. **Can we identify the source of model mis-specification?**
   - Missing variables (NEAT, metabolic adaptation)?
   - Non-linear relationships?
   - Measurement error structure?
5. **What window length optimizes signal-to-noise vs stationarity trade-off?**

## Success Criteria

A successful analysis would:

1. **Extract physiologically plausible parameters** OR explain why they can't be extracted
2. **Quantify uncertainty** in parameter estimates with confidence intervals
3. **Validate predictions** on held-out 2025 data (MAE < 0.5 kg per 14 days)
4. **Provide recommendations** for:
   - Model structure improvements
   - Data collection changes
   - Practical coaching applications

## Technical Context

**Tools used so far:**
- Kalman filtering (Q=0.0196, R=2.89) for fat mass smoothing
- Huber regression (epsilon=1.35) for robust parameter estimation
- Feature orthogonalization to remove exercise-induced eating confounding
- Non-overlapping windows to ensure statistical independence

**Kalman Filter Details:**
- Process noise Q = 0.0196 kg² (max physiological daily change)
- Measurement noise R = 2.89 kg² (BIA sensor error from literature)
- Successfully reduces noise 3× (0.79 → 0.26 kg stddev)

## Contact

For questions about:
- Data provenance: Check `schema.manifest.yaml` in project root
- Kalman filter: See `etl/kalman_filter.py` and `docs/adr/0003-kalman-filter-bia-smoothing.md`
- Previous attempts: See `tools/` directory for 10+ different modeling approaches

---

*This dataset represents 4.75 years of meticulous daily tracking. The goal is to extract actionable metabolic insights that can inform evidence-based coaching decisions.*

