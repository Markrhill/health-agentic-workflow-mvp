# Parameter Estimation Method Analysis

## Executive Summary

Our parameter estimation script produces **identical results** to the original Gemini script when using the same methodology. The key differences are:

1. **Identical Core Parameters**: α, C, and k_LBM are exactly the same
2. **BMR₀ Difference**: Only difference is BMR₀ (0 vs 1600) due to identifiability issues
3. **Model Fit**: Identical R² = 0.027 and MAE = 0.836 kg
4. **Root Cause**: Constant 'days' feature (14) causes multicollinearity and identifiability problems

## Detailed Comparison

### Method Comparison Results

| Method | α (kcal/kg) | C | BMR₀ | k_LBM | R² | MAE |
|--------|-------------|---|------|-------|----|----|
| **Original Gemini (4 features)** | 28,416 | -0.847 | -0 | -178.8 | 0.027 | 0.836 |
| **Current Implementation (3 features)** | 28,416 | -0.847 | 1,600 | -178.8 | 0.027 | 0.836 |
| **Original Gemini (no standardization)** | 35,189 | -1.479 | 0 | 6.1 | 0.019 | 0.838 |

### Key Findings

#### 1. **Identical Core Parameters**
- **α (Energy Density)**: 28,416 kcal/kg (both methods)
- **C (Exercise Compensation)**: -0.847 (both methods)  
- **k_LBM (LBM Coefficient)**: -178.8 kcal/day/kg (both methods)

#### 2. **BMR₀ Identifiability Issue**
- **Original Gemini**: BMR₀ = 0 (unidentifiable due to constant 'days' feature)
- **Our Implementation**: BMR₀ = 1,600 (hardcoded reasonable value)
- **Root Cause**: 'days' feature is constant (14) across all windows

#### 3. **Feature Correlation Analysis**
```
days*LBM ↔ mean_lbm: 1.000 (perfect correlation)
```
This perfect correlation indicates that `days*LBM` and `mean_lbm` are essentially the same feature when days=14.

#### 4. **Model Performance**
- **R² = 0.027**: Very low explanatory power
- **MAE = 0.836 kg**: High prediction error
- **Issue**: Model struggles to explain fat mass changes

## Technical Analysis

### Identifiability Problem

The core issue is that the `days` feature is constant (14) across all windows:

```python
# All windows have exactly 14 days
windows['days'].unique()  # [14]
windows['days'].std()     # 0.000
```

This creates several problems:

1. **Perfect Multicollinearity**: `days*LBM` = 14 × `mean_lbm`
2. **Unidentifiable BMR₀**: The coefficient for `days` cannot be estimated
3. **Redundant Features**: `days*LBM` and `mean_lbm` are perfectly correlated

### Mathematical Explanation

The original model is:
```
delta_fm_kg = (intake_sum - (1-C)*workout_sum - BMR₀*days - k_LBM*mean_lbm*days) / α
```

When `days = 14` (constant), this becomes:
```
delta_fm_kg = (intake_sum - (1-C)*workout_sum - 14*BMR₀ - 14*k_LBM*mean_lbm) / α
```

The terms `14*BMR₀` and `14*k_LBM*mean_lbm` are indistinguishable, leading to:
- BMR₀ coefficient becomes unidentifiable
- k_LBM coefficient absorbs the BMR₀ effect

## Recommendations

### 1. **Immediate Fix: Use Variable Window Lengths**
```python
# Instead of fixed 14-day windows, use variable lengths
window_lengths = [7, 10, 14, 21, 28]  # Different window sizes
```

### 2. **Alternative Approach: Remove Constant Features**
```python
# Remove 'days' feature entirely and use only:
X = np.column_stack([
    windows['mean_lbm'].values,      # LBM
    windows['workout_sum'].values,   # Workout calories  
    windows['intake_sum'].values     # Intake calories
])
```

### 3. **Physiological Validation**
The current parameters suggest issues:
- **α = 28,416 kcal/kg**: Too high (should be ~7,700)
- **C = -0.847**: Negative compensation (physiologically implausible)
- **k_LBM = -178.8**: Negative LBM effect (implausible)

### 4. **Data Quality Investigation**
- **R² = 0.027**: Model explains only 2.7% of variance
- **MAE = 0.836 kg**: High prediction error
- **Investigate**: Data quality, measurement noise, model assumptions

## Conclusion

Our implementation is **mathematically equivalent** to the original Gemini script. The parameter estimation issues are not due to implementation differences but rather:

1. **Identifiability problems** from constant window lengths
2. **Data quality issues** (low R², high MAE)
3. **Model assumptions** that may not hold for this dataset

The next steps should focus on:
1. Using variable window lengths
2. Investigating data quality
3. Validating model assumptions
4. Considering alternative modeling approaches

## Files Created

- `tools/compare_parameter_methods.py` - Comparison script
- `docs/PARAMETER-ESTIMATION-ANALYSIS.md` - This analysis document
