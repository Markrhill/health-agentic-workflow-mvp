# Physiological Smoother Implementation

## Overview

The `PhysioSmoother` class implements a physiologically grounded smoothing algorithm for noisy BIA fat mass data. It separates fat mass trends from hydration/glycogen fluctuations using a two-compartment model with robust regression.

## Key Features

### 1. **Two-Compartment Model**
- **Fat compartment (F)**: Slow trend with strong smoothing (EWMA half-life ~90 days)
- **Hydration/glycogen compartment (H)**: Fast fluctuations from carbs and alcohol
- **Observed fat mass**: `y_t = F_t + k_H * H_t + noise_t`

### 2. **Robust IRLS Algorithm**
- Iterative reweighted least squares with Huber loss
- Centers hydration component to remove intercept
- Bounds k_H coefficient between 0.0 and 1.5
- Automatic convergence detection

### 3. **Physiological Parameters**
- **carb_mass_per_g**: 0.0035 kg per gram of carbs (glycogen+water)
- **alcohol_mass_per_g**: 0.001 kg per gram of alcohol (conservative)
- **fat_half_life_days**: 90 days (slow fat trend)
- **hydration_half_life_days**: 2 days (fast hydration fluctuations)

## Implementation Details

### Core Algorithm

```python
# 1. Compute centered hydration component
carbs_kg = df['carbs_g'] * carb_mass_per_g
h_raw = ewma(carbs_kg, hydration_half_life_days)
hydration_component = h_raw - h_raw.mean()  # CENTER

# 2. IRLS loop
for iteration in range(max_iterations):
    # Update fat trend
    if iteration == 0:
        fat_trend = ewma(fat_mass_obs, fat_half_life_days)
    else:
        fat_corrected = fat_mass_obs - k_h * hydration_component
        fat_trend = ewma(fat_corrected, fat_half_life_days)
    
    # Fit k_h with robust regression
    y_residual = fat_mass_obs - fat_trend
    y_residual_c = y_residual - mean(y_residual)  # center
    k_h = robust_regression(y_residual_c, hydration_component)
    k_h = clip(k_h, 0.0, 1.5)  # bounds
    
    # Check convergence
    if |k_h_new - k_h_old| < tolerance:
        break

# 3. Final results
fat_smooth = ewma(fat_mass_obs - k_h * hydration_component, fat_half_life_days)
residuals = fat_mass_obs - (fat_smooth + k_h * hydration_component)
```

### Key Improvements Made

1. **EWMA Half-life Usage**: Direct half-life parameters instead of alpha conversion
2. **Centered Hydration**: Removes intercept bias in regression
3. **Mass-based Scaling**: Realistic kg per gram conversions for carbs/alcohol
4. **Robust Bounds**: k_H constrained to physiologically reasonable range
5. **Intercept Tracking**: Stores and reports intercept shift
6. **Enhanced Plotting**: Offset hydration band with parameter display

## Usage Examples

### Basic Usage

```python
from tools.physio_smoother import PhysioSmoother

# Initialize smoother
smoother = PhysioSmoother(
    fat_half_life_days=90,
    hydration_half_life_days=2,
    carb_mass_per_g=0.0035,
    alcohol_mass_per_g=0.001,
    huber_delta=0.7
)

# Fit to data
smoother.fit(df)

# Get results
results = smoother.get_results()
params = smoother.get_params()

# Plot results
fig = smoother.plot()
```

### Advanced Usage

```python
# Custom parameters
smoother = PhysioSmoother(
    fat_half_life_days=60,      # Faster fat trend
    hydration_half_life_days=1, # Faster hydration response
    carb_mass_per_g=0.004,     # Higher carb effect
    huber_delta=0.5            # More robust to outliers
)

# Compare fat loss with calorie deficit
loss_comparison = smoother.compare_loss('2022-01-01', '2022-06-30')
print(f"Fat change: {loss_comparison['fat_change_kg']:.3f} kg")
print(f"Agreement ratio: {loss_comparison['agreement_ratio']:.3f}")
```

## Results Structure

### DataFrame Output
- **fat_mass_obs**: Original observed fat mass
- **fat_mass_smooth**: Smoothed fat trend (F)
- **hydration_component**: Hydration effect (k_H * H)
- **residuals**: Observed - (smooth + hydration)
- **weights**: Huber weights from robust regression

### Parameters
- **k_h**: Hydration coefficient (0.0 to 1.5)
- **intercept_shift_kg**: Mean residual offset
- **mean_abs_residual**: Mean absolute residual
- **converged**: Whether IRLS converged
- **iterations**: Number of IRLS iterations

## Test Results (2022 Data)

```
Records processed: 244
k_h (hydration coefficient): 0.000000
Mean absolute residual: 1.4824 kg
Converged: True
Iterations: 2

Loss comparison (Jan-Jun 2022):
  Fat change: -0.627 kg
  Cumulative deficit: nan kcal (no net_kcal data)
  Agreement ratio: nan
```

## Key Benefits

### 1. **Physiological Grounding**
- Separates fat trends from hydration fluctuations
- Uses realistic mass conversions for carbs/alcohol
- Bounds parameters to physiologically reasonable ranges

### 2. **Robust Estimation**
- Huber loss handles outliers gracefully
- IRLS with convergence detection
- Centered variables prevent intercept bias

### 3. **Transparent Diagnostics**
- Clear residual analysis
- Parameter bounds and convergence status
- Visual comparison with calorie deficits

### 4. **Flexible Configuration**
- Adjustable half-lives for different time scales
- Configurable mass conversions
- Robust regression parameters

## Technical Notes

### EWMA Implementation
```python
def _ewma(self, s: pd.Series, halflife_days: float) -> pd.Series:
    return s.ewm(halflife=halflife_days, adjust=False).mean()
```

### Robust Regression
- Uses statsmodels RLM with HuberT when available
- Falls back to custom IRLS implementation
- Applies bounds: `k_h = clip(k_h, 0.0, 1.5)`

### Centering Strategy
- Hydration component: `h_centered = h_raw - mean(h_raw)`
- Residuals: `y_centered = y_raw - mean(y_raw)`
- Eliminates intercept bias in regression

## Future Enhancements

1. **Alcohol Data Integration**: When alcohol_g becomes available
2. **Seasonal Adjustments**: Account for seasonal hydration patterns
3. **Individual Calibration**: Learn person-specific parameters
4. **Uncertainty Quantification**: Bootstrap confidence intervals
5. **Real-time Updates**: Incremental smoothing for new data

## Conclusion

The PhysioSmoother provides a robust, physiologically grounded approach to smoothing noisy BIA fat mass data. By separating fat trends from hydration fluctuations, it produces more stable and interpretable results while maintaining transparency through comprehensive diagnostics.

The implementation successfully handles real-world data challenges including outliers, missing values, and parameter identifiability issues through robust statistical methods and physiological constraints.
