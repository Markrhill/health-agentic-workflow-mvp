#!/usr/bin/env python3
"""
Parameter Estimation - 2-Tranche Model
Created: 2025-10-02
Input: data/parameter_estimation/biweekly_windows_2025-10-02_v1.1.csv
Output: Fitted BMR and compensation parameters with confidence intervals

Model: y = b₀×days + b₁×(days×LBM) + c_baseline×Exercise×I(baseline) + c_high×Exercise×I(high) + ε
Where:
  - c_baseline applies to <500 kcal/day avg workout (LOW+MID combined)
  - c_high applies to ≥500 kcal/day avg workout (HIGH volume)
  
Method: HuberRegressor (epsilon=1.35, alpha=1e-3) for robust fitting
"""

import pandas as pd
import numpy as np
from sklearn.linear_model import HuberRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import r2_score, mean_absolute_error
import matplotlib.pyplot as plt
from scipy import stats

# Load data
df = pd.read_csv('data/parameter_estimation/biweekly_windows_2025-10-02_v1.1.csv')

# Convert date columns
df['window_start'] = pd.to_datetime(df['window_start'])
df['window_end'] = pd.to_datetime(df['window_end'])

# Create 2-tranche indicators
df['is_high_volume'] = (df['avg_daily_workout_kcal'] >= 500).astype(int)
df['is_baseline_volume'] = (df['avg_daily_workout_kcal'] < 500).astype(int)

# Split train/test
train = df[df['dataset_split'] == 'TRAIN'].copy()
test = df[df['dataset_split'] == 'TEST'].copy()

print("=" * 70)
print("PARAMETER ESTIMATION - 2-TRANCHE MODEL")
print("=" * 70)
print(f"\nData loaded:")
print(f"  Training windows: {len(train)} (2021-2024)")
print(f"    - Baseline volume (<500 kcal/day): {train['is_baseline_volume'].sum()}")
print(f"    - High volume (≥500 kcal/day): {train['is_high_volume'].sum()}")
print(f"  Test windows: {len(test)} (2025)")
print(f"    - Baseline volume: {test['is_baseline_volume'].sum()}")
print(f"    - High volume: {test['is_high_volume'].sum()}")

# Prepare regression inputs
# Since days = 14 is constant, absorb it into the coefficients
# Model: y = 14×b₀ + 14×b₁×LBM - c_baseline×Ex_base - c_high×Ex_high

y_train = train['y_deficit'].values
X_train = np.column_stack([
    np.ones(len(train)),  # Intercept (will capture 14×b₀)
    train['lbm_avg_kg'].values,  # Will capture 14×b₁
    train['total_workout_kcal'].values * train['is_baseline_volume'].values,  # c_baseline
    train['total_workout_kcal'].values * train['is_high_volume'].values  # c_high
])

y_test = test['y_deficit'].values
X_test = np.column_stack([
    np.ones(len(test)),  # Intercept
    test['lbm_avg_kg'].values,  # LBM
    test['total_workout_kcal'].values * test['is_baseline_volume'].values,
    test['total_workout_kcal'].values * test['is_high_volume'].values
])

# Standardize ONLY the non-constant features
scaler = StandardScaler()
X_train_scaled = X_train.copy()
X_train_scaled[:, 1:] = scaler.fit_transform(X_train[:, 1:])  # Skip intercept column

X_test_scaled = X_test.copy()
X_test_scaled[:, 1:] = scaler.transform(X_test[:, 1:])  # Skip intercept column

# Fit Huber regressor
print("\n" + "-" * 70)
print("FITTING HUBER REGRESSOR")
print("-" * 70)
huber = HuberRegressor(epsilon=1.35, max_iter=500, alpha=1e-3, fit_intercept=False)
huber.fit(X_train_scaled, y_train)

# Unscale coefficients
beta = huber.coef_
beta[0] = beta[0]  # Intercept stays as-is
beta[1:] = beta[1:] / scaler.scale_  # Unscale the rest

print(f"Raw coefficients: {huber.coef_}")
print(f"Unscaled coefficients: {beta}")

# Extract parameters
# Model: y = 14×BMR₀ + 14×BMR₁×LBM - c_baseline×Ex_base - c_high×Ex_high
# Where beta[0] = 14×BMR₀, beta[1] = 14×BMR₁
# And beta[2] = -c_baseline, beta[3] = -c_high

bmr_intercept = beta[0] / 14  # Divide by days
bmr_per_kg_lbm = beta[1] / 14  # Divide by days
c_baseline = -beta[2]
c_high = -beta[3]

print("\n" + "=" * 70)
print("FITTED PARAMETERS")
print("=" * 70)
print(f"\nBMR Model: BMR = {bmr_intercept:.1f} + {bmr_per_kg_lbm:.2f} × LBM_kg")
print(f"\nCompensation Factors:")
print(f"  c_baseline (<500 kcal/day): {c_baseline:.3f}")
print(f"  c_high (≥500 kcal/day): {c_high:.3f}")

# Calculate predictions
y_train_pred = huber.predict(X_train_scaled)
y_test_pred = huber.predict(X_test_scaled)

# Convert back to fat mass predictions
train['fm_pred_kg'] = -(y_train_pred - train['total_intake_kcal'] + train['total_workout_kcal']) / 9675
test['fm_pred_kg'] = -(y_test_pred - test['total_intake_kcal'] + test['total_workout_kcal']) / 9675

# Metrics
train_r2 = r2_score(y_train, y_train_pred)
test_r2 = r2_score(y_test, y_test_pred)
train_mae = mean_absolute_error(train['delta_fm_kg'], train['fm_pred_kg'])
test_mae = mean_absolute_error(test['delta_fm_kg'], test['fm_pred_kg'])

print("\n" + "-" * 70)
print("MODEL FIT METRICS")
print("-" * 70)
print(f"\nTraining set (2021-2024):")
print(f"  R² score: {train_r2:.3f}")
print(f"  MAE (fat mass): {train_mae:.3f} kg")
print(f"\nTest set (2025):")
print(f"  R² score: {test_r2:.3f}")
print(f"  MAE (fat mass): {test_mae:.3f} kg")

# Bootstrap confidence intervals
print("\n" + "-" * 70)
print("BOOTSTRAP CONFIDENCE INTERVALS (1000 iterations)")
print("-" * 70)

n_bootstrap = 1000
bootstrap_params = []

np.random.seed(42)
for i in range(n_bootstrap):
    # Resample with replacement
    indices = np.random.choice(len(train), size=len(train), replace=True)
    X_boot = X_train_scaled[indices]
    y_boot = y_train[indices]
    
    # Fit model
    huber_boot = HuberRegressor(epsilon=1.35, max_iter=500, alpha=1e-3, fit_intercept=False)
    huber_boot.fit(X_boot, y_boot)
    
    # Unscale and extract parameters
    beta_boot = huber_boot.coef_.copy()
    beta_boot[0] = beta_boot[0]  # Intercept stays as-is
    beta_boot[1:] = beta_boot[1:] / scaler.scale_  # Unscale the rest
    
    bootstrap_params.append([
        beta_boot[0] / 14,  # BMR intercept
        beta_boot[1] / 14,  # BMR per kg
        -beta_boot[2],  # c_baseline
        -beta_boot[3]  # c_high
    ])

bootstrap_params = np.array(bootstrap_params)

# Calculate 95% CI
ci_lower = np.percentile(bootstrap_params, 2.5, axis=0)
ci_upper = np.percentile(bootstrap_params, 97.5, axis=0)

print(f"\nBMR intercept: {bmr_intercept:.1f} kcal/day")
print(f"  95% CI: [{ci_lower[0]:.1f}, {ci_upper[0]:.1f}]")
print(f"\nBMR per kg LBM: {bmr_per_kg_lbm:.2f} kcal/day/kg")
print(f"  95% CI: [{ci_lower[1]:.2f}, {ci_upper[1]:.2f}]")
print(f"\nc_baseline: {c_baseline:.3f}")
print(f"  95% CI: [{ci_lower[2]:.3f}, {ci_upper[2]:.3f}]")
print(f"\nc_high: {c_high:.3f}")
print(f"  95% CI: [{ci_lower[3]:.3f}, {ci_upper[3]:.3f}]")

# Physiological plausibility checks
print("\n" + "=" * 70)
print("PHYSIOLOGICAL PLAUSIBILITY ASSESSMENT")
print("=" * 70)

issues = []

# Check BMR per kg LBM
if not (10 <= bmr_per_kg_lbm <= 30):
    issues.append(f"BMR per kg LBM = {bmr_per_kg_lbm:.2f} outside range [10, 30]")
else:
    print(f"✓ BMR per kg LBM = {bmr_per_kg_lbm:.2f} (literature: 15-25 for athletes)")

# Check compensation factors
if not (0 <= c_baseline <= 1):
    issues.append(f"c_baseline = {c_baseline:.3f} outside range [0, 1]")
else:
    print(f"✓ c_baseline = {c_baseline:.3f} (literature: 0.10-0.30 typical)")

if not (0 <= c_high <= 1):
    issues.append(f"c_high = {c_high:.3f} outside range [0, 1]")
else:
    print(f"✓ c_high = {c_high:.3f} (literature: 0.25-0.40 for sustained training)")

# Check if c_high > c_baseline
if c_high <= c_baseline:
    issues.append(f"c_high ({c_high:.3f}) should exceed c_baseline ({c_baseline:.3f})")
else:
    print(f"✓ c_high > c_baseline: {c_high:.3f} > {c_baseline:.3f}")

# Display any issues
if issues:
    print("\n⚠ PLAUSIBILITY WARNINGS:")
    for issue in issues:
        print(f"  - {issue}")
else:
    print("\n✓ All parameters within physiologically plausible ranges")

print("\n" + "=" * 70)
print("ANALYSIS COMPLETE")
print("=" * 70)

