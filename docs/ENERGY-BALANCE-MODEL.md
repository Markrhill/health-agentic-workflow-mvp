# 4-Parameter Energy Balance Model

## Overview

The 4-Parameter Energy Balance Model is a comprehensive tool for estimating physiological parameters from body composition and energy data using robust statistical methods. It implements the energy balance equation:

```
delta_fm_kg = (intake_sum - (1-C)*workout_sum - BMR₀*days - k_LBM*mean_lbm*days) / α
```

Where:
- **α**: Energy density of fat tissue (kcal/kg)
- **C**: Exercise compensation factor (unitless)
- **BMR₀**: Baseline metabolic rate (kcal/day)
- **k_LBM**: Lean body mass metabolic coefficient (kcal/day/kg)

## Key Features

### 1. **Robust Data Processing**
- PostgreSQL database integration
- Configurable date range filtering
- Robust outlier detection using rolling median + MAD
- Comprehensive data quality validation

### 2. **Flexible Window Analysis**
- Configurable window lengths (default: 14 days)
- Strict eligibility criteria for window quality
- Sliding window approach for maximum data utilization
- Configurable minimum valid days per window

### 3. **Advanced Statistical Modeling**
- Huber regression for outlier robustness
- Feature standardization for numerical stability
- 4-parameter linear model with physiological interpretation
- Comprehensive fit metrics (R², MAE, RMSE)

### 4. **Parameter Validation**
- Physiological plausibility checks
- Configurable parameter ranges
- Detailed warning system for implausible results
- Comprehensive result reporting

## Usage Examples

### Basic Analysis
```bash
python tools/energy_balance_model.py
```

### Custom Date Range
```bash
python tools/energy_balance_model.py --start-date 2022-01-01 --end-date 2023-12-31
```

### Different Window Lengths
```bash
# 7-day windows
python tools/energy_balance_model.py --window-days 7 --min-valid-days 5

# 21-day windows  
python tools/energy_balance_model.py --window-days 21 --min-valid-days 15
```

### Custom Robust Cleaning
```bash
python tools/energy_balance_model.py --robust-k 2.5 --robust-window 5
```

### Save Results
```bash
python tools/energy_balance_model.py --output results.csv --verbose
```

## Configuration Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `start_date` | 2021-01-01 | Analysis start date |
| `end_date` | 2024-12-31 | Analysis end date |
| `window_days` | 14 | Window length in days |
| `robust_window` | 7 | Outlier detection window |
| `robust_k` | 3.0 | MAD threshold multiplier |
| `min_valid_days` | 10 | Minimum valid days per window |
| `huber_epsilon` | 1.35 | Huber regression parameter |
| `huber_alpha` | 1e-3 | Regularization parameter |

## Results Analysis

### Sample Output
```
================================================================================
4-PARAMETER ENERGY BALANCE MODEL ESTIMATION RESULTS
================================================================================

📊 DATA SUMMARY
----------------------------------------
Daily records: 1,094
Analysis windows: 828
Date range: 2021-01-01 to 2024-12-31
Window length: 14 days

🔬 RAW REGRESSION COEFFICIENTS
----------------------------------------
β₁ (days):               0.000000
β₂ (days × LBM):        0.006293
β₃ (workout_sum):      -0.000065
β₄ (intake_sum):        0.000035

⚖️  PHYSIOLOGICAL PARAMETERS
----------------------------------------
α (energy density):        28,416 kcal/kg fat
C (exercise compensation):   -0.847
BMR₀ (baseline metabolism):       -0 kcal/day
k_LBM (LBM coefficient):     -178.8 kcal/day/kg

📈 MODEL FIT METRICS
----------------------------------------
R² (coefficient of determination):    0.027
MAE (mean absolute error):            0.836 kg
RMSE (root mean square error):        1.084 kg

✅ PARAMETER VALIDATION
----------------------------------------
⚠️  Parameters outside plausible ranges:
   - α=28,416 outside plausible range (8000-10000 kcal/kg)
   - C=-0.847 outside plausible range (0.0-0.5)
   - BMR₀=-0 outside plausible range (200-1000 kcal/day)
   - k_LBM=-178.8 outside plausible range (2-25 kcal/day/kg)
```

### Parameter Validation Ranges

| Parameter | Plausible Range | Description |
|-----------|----------------|-------------|
| **α** | 8,000-10,000 kcal/kg | Fat tissue energy density (DLW studies) |
| **C** | 0.0-0.5 | Exercise compensation factor |
| **BMR₀** | 200-1000 kcal/day | Baseline metabolism when LBM=0 |
| **k_LBM** | 2-25 kcal/day/kg | Lean body mass metabolic coefficient |

## Window Length Comparison

| Window Length | Windows | α (kcal/kg) | C | BMR₀ (kcal/day) | k_LBM | R² |
|---------------|---------|-------------|---|-----------------|-------|-----|
| **7 days** | 831 | 24,899 | -0.743 | 0 | -220.9 | 0.017 |
| **14 days** | 828 | 28,416 | -0.847 | 0 | -178.8 | 0.027 |
| **21 days** | 824 | 49,472 | -2.379 | 0 | -190.1 | 0.065 |

## Key Findings

### 1. **Identifiability Issues**
- **BMR₀ = 0**: Cannot be estimated due to constant window lengths
- **Perfect Multicollinearity**: `days*LBM` and `mean_lbm` are perfectly correlated
- **Unidentifiable Parameters**: Model cannot distinguish between BMR₀ and k_LBM effects

### 2. **Data Quality Issues**
- **Low R²**: Model explains only 2-6% of variance
- **High Prediction Error**: MAE ~0.8 kg (large relative to fat mass changes)
- **Implausible Parameters**: All parameters outside physiological ranges

### 3. **Window Length Effects**
- **Shorter Windows**: More windows, slightly better parameters
- **Longer Windows**: Higher R² but more extreme parameters
- **Consistent Issues**: Identifiability problems persist across all window lengths

## Recommendations

### 1. **Address Identifiability Issues**
- Use variable window lengths: [7, 10, 14, 21, 28] days
- Remove constant `days` feature from model
- Consider alternative model formulations

### 2. **Improve Data Quality**
- Investigate measurement accuracy
- Validate data preprocessing steps
- Consider different outlier detection methods

### 3. **Model Validation**
- Test model assumptions (linearity, independence)
- Consider non-linear approaches
- Validate against known physiological relationships

### 4. **Parameter Estimation**
- Use constrained optimization with physiological bounds
- Consider Bayesian approaches with informative priors
- Implement cross-validation for model stability

## Files Created

- **`tools/energy_balance_model.py`** - Main implementation
- **`tests/test_energy_balance_model.py`** - Test suite
- **`docs/ENERGY-BALANCE-MODEL.md`** - This documentation

## Dependencies

- pandas >= 1.3.0
- numpy >= 1.21.0
- scikit-learn >= 1.0.0
- sqlalchemy >= 1.4.0
- python >= 3.8

## Error Handling

The model includes comprehensive error handling for:
- Database connection failures
- Insufficient data (< 20 windows)
- Regression convergence issues
- Invalid parameter ranges
- Data quality problems

## Future Enhancements

- Cross-validation for model stability
- Bootstrap confidence intervals
- Alternative robust regression methods
- Seasonal/trend decomposition
- Multiple window lengths comparison
- Parameter sensitivity analysis
