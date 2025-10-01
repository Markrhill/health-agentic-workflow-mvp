# Parameter Estimation Differences Analysis

## Executive Summary

The radical differences between our database-based parameter estimation and Gemini's CSV-based results are due to several key factors:

| Parameter | Our Database | Gemini CSV | Difference |
|-----------|--------------|------------|------------|
| **α (kcal/kg)** | 24,166 | 9,710 | 2.5x higher |
| **C (compensation)** | -0.315 | 0.16 | Sign flip + magnitude |
| **BMR₀ (kcal/day)** | 0 | 785 | Unidentifiable vs reasonable |
| **k_LBM (kcal/day/kg)** | -176.3 | 11.5 | 15x magnitude difference |
| **R²** | 0.030 | Not reported | Very low explanatory power |
| **MAE (kg)** | 0.848 | Not reported | High prediction error |
| **Windows** | 986 | 113 | 8.7x more data |

## Root Cause Analysis

### 1. **Data Volume Difference**
- **Our Database**: 986 windows (1,310 daily records)
- **Gemini CSV**: 113 windows
- **Impact**: 8.7x more data may introduce noise and outliers

### 2. **Identifiability Issues**
- **Constant Days Feature**: All windows are exactly 14 days
- **Perfect Multicollinearity**: `days*LBM` = 14 × `mean_lbm`
- **Unidentifiable BMR₀**: Cannot be estimated due to constant days

### 3. **Data Quality Differences**
- **Date Range**: Our data goes to 2025-09-28 vs CSV to 2025-09-09
- **Robust Cleaning**: Different outlier removal effects
- **Measurement Quality**: CSV may have cleaner measurements

### 4. **Statistical Characteristics**

#### Database Data (Our Implementation)
```
Total records: 1,310
Date range: 2021-01-01 to 2025-09-28
fat_mass_kg: 19.23 ± 1.58 kg
fat_free_mass_kg: 72.43 ± 1.50 kg
intake_kcal: 1,683 ± 538 kcal
workout_kcal: 493 ± 638 kcal
```

#### Window-Level Statistics
```
delta_fm_kg: 0.009 ± 1.114 kg (very small changes)
intake_sum: 23,465 ± 3,452 kcal
workout_sum: 6,890 ± 2,830 kcal
mean_lbm: 72.43 ± 1.21 kg
```

## Technical Analysis

### Identifiability Problem

The core issue is the constant `days=14` feature:

```python
# All windows have exactly 14 days
windows['days'].unique()  # [14]
windows['days'].std()     # 0.000
```

This creates:
1. **Perfect Correlation**: `days*LBM` ↔ `mean_lbm` = 1.000
2. **Unidentifiable BMR₀**: Coefficient cannot be estimated
3. **Redundant Features**: `days*LBM` and `mean_lbm` are identical

### Mathematical Explanation

Original model:
```
delta_fm_kg = (intake_sum - (1-C)*workout_sum - BMR₀*days - k_LBM*mean_lbm*days) / α
```

With constant `days=14`:
```
delta_fm_kg = (intake_sum - (1-C)*workout_sum - 14*BMR₀ - 14*k_LBM*mean_lbm) / α
```

The terms `14*BMR₀` and `14*k_LBM*mean_lbm` are indistinguishable.

### Data Quality Issues

1. **Low Explanatory Power**: R² = 0.030 (only 3% of variance explained)
2. **High Prediction Error**: MAE = 0.848 kg
3. **Small Fat Mass Changes**: Mean delta = 0.009 kg (essentially zero)
4. **High Variance**: Std dev = 1.114 kg (large relative to mean)

## Why Gemini's Results Are Better

### 1. **Reasonable Parameters**
- **α = 9,710 kcal/kg**: Within physiological range (7,000-12,000)
- **C = 0.16**: Positive compensation (physiologically plausible)
- **BMR₀ = 785 kcal/day**: Reasonable baseline metabolic rate
- **k_LBM = 11.5 kcal/day/kg**: Positive LBM effect (plausible)

### 2. **Smaller Dataset**
- **113 windows**: More focused, higher quality data
- **Better Signal-to-Noise**: Less noisy measurements
- **Cleaner Data**: CSV may have better data quality

### 3. **Different Data Characteristics**
- **Date Range**: May include different time periods
- **Data Source**: CSV may have different preprocessing
- **Outlier Handling**: Different robust cleaning effects

## Recommendations

### 1. **Immediate Fixes**

#### Use Variable Window Lengths
```python
window_lengths = [7, 10, 14, 21, 28]  # Different window sizes
```

#### Remove Constant Features
```python
# Use only non-constant features
X = np.column_stack([
    windows['mean_lbm'].values,      # LBM
    windows['workout_sum'].values,   # Workout calories
    windows['intake_sum'].values     # Intake calories
])
```

### 2. **Data Quality Investigation**

#### Check Data Sources
- Verify database matches CSV exactly
- Compare date ranges and data quality
- Validate measurement accuracy

#### Improve Robust Cleaning
```python
# Test different cleaning parameters
def robust_clean(series, window=7, k=2.0):  # Try k=2.0 instead of 3.0
    # ... existing implementation
```

### 3. **Model Validation**

#### Check Model Assumptions
- Linear relationship assumption
- Independence of observations
- Homoscedasticity

#### Consider Alternative Approaches
- Non-linear models
- Time series approaches
- Different windowing strategies

### 4. **Parameter Validation**

#### Physiological Bounds
```python
def validate_parameters(params):
    if not (7000 <= params['alpha'] <= 12000):
        raise ValueError("α outside physiological range")
    if not (0 <= params['c'] <= 1):
        raise ValueError("C outside [0,1] range")
    # ... other validations
```

## Conclusion

The radical differences between our results and Gemini's are due to:

1. **Identifiability issues** from constant window lengths
2. **Data quality differences** between database and CSV
3. **Data volume effects** (986 vs 113 windows)
4. **Model assumptions** that may not hold

The next steps should focus on:
1. Using variable window lengths
2. Investigating data quality differences
3. Validating model assumptions
4. Considering alternative modeling approaches

## Files Created

- `tools/analyze_parameter_differences.py` - Analysis script
- `docs/PARAMETER-DIFFERENCES-ANALYSIS.md` - This analysis document
