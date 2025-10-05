#!/usr/bin/env python3
"""
2-Parameter Model with Orthogonalization
Fixed: α = 9,675 kcal/kg
Estimate: BMR_avg (constant), c_baseline
Uses: 14-day non-overlapping windows with Kalman-filtered fat mass
Better signal-to-noise ratio than 7-day windows
"""

import pandas as pd
import numpy as np
from sklearn.linear_model import HuberRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import r2_score, mean_absolute_error

df = pd.read_csv('data/parameter_estimation/nonoverlapping_14day_windows_2025-10-02.csv')
train = df[df['dataset_split'] == 'TRAIN'].copy()
test = df[df['dataset_split'] == 'TEST'].copy()

# ============================================================================
# ORTHOGONALIZATION: Remove exercise-driven intake component
# ============================================================================
# Causal structure: Exercise → Intake (eating to replenish glycogen)
# Therefore: Regress INTAKE on WORKOUT, then use residuals

from sklearn.linear_model import LinearRegression

print("\n" + "=" * 80)
print("ORTHOGONALIZATION: INTAKE ~ WORKOUT")
print("=" * 80)

# Fit on training data only
ortho_model = LinearRegression()
X_ortho = train['total_workout_kcal'].values.reshape(-1, 1)
y_ortho = train['total_intake_kcal'].values

ortho_model.fit(X_ortho, y_ortho)

# Calculate orthogonalized intake for BOTH train and test
train['intake_orthogonal'] = train['total_intake_kcal'] - ortho_model.predict(
    train['total_workout_kcal'].values.reshape(-1, 1)
)
test['intake_orthogonal'] = test['total_intake_kcal'] - ortho_model.predict(
    test['total_workout_kcal'].values.reshape(-1, 1)
)

# Report orthogonalization results
print(f"Intake-Workout correlation BEFORE: {train[['total_intake_kcal', 'total_workout_kcal']].corr().iloc[0,1]:.3f}")
print(f"Intake_ortho-Workout correlation AFTER: {train[['intake_orthogonal', 'total_workout_kcal']].corr().iloc[0,1]:.3f}")
print(f"Orthogonalization slope: {ortho_model.coef_[0]:.3f} kcal intake per kcal workout")

print("=" * 80)
print("2-PARAMETER MODEL (FIXED α = 9,675 kcal/kg)")
print("=" * 80)

print(f"\nTraining windows: {len(train)}")
print(f"Test windows: {len(test)}")

# Recalculate y_deficit using orthogonalized intake
ALPHA_FIXED = 9675
train['y_deficit_ortho'] = train['intake_orthogonal'] - ALPHA_FIXED * train['delta_fm_kg']
test['y_deficit_ortho'] = test['intake_orthogonal'] - ALPHA_FIXED * test['delta_fm_kg']

# Model: y = 14×BMR_avg - c×Exercise
y_train = train['y_deficit_ortho'].values
X_train = np.column_stack([
    np.ones(len(train)),  # BMR constant term
    train['total_workout_kcal'].values  # Exercise term
])

y_test = test['y_deficit_ortho'].values
X_test = np.column_stack([
    np.ones(len(test)),
    test['total_workout_kcal'].values
])

# Standardize
scaler = StandardScaler()
X_train_scaled = X_train.copy()
X_train_scaled[:, 1:] = scaler.fit_transform(X_train[:, 1:])

X_test_scaled = X_test.copy()
X_test_scaled[:, 1:] = scaler.transform(X_test[:, 1:])

# Fit
print("\n" + "-" * 80)
print("FITTING HUBER REGRESSOR")
print("-" * 80)

huber = HuberRegressor(epsilon=1.35, alpha=1e-3, fit_intercept=False)
huber.fit(X_train_scaled, y_train)

# Extract parameters
beta = huber.coef_.copy()
beta[1] = beta[1] / scaler.scale_[0]

bmr_avg = beta[0] / 14
c_baseline = -beta[1]

print(f"Raw coefficients: {huber.coef_}")
print(f"Unscaled coefficients: {beta}")

print("\n" + "=" * 80)
print("FITTED PARAMETERS")
print("=" * 80)

print(f"\nAverage BMR: {bmr_avg:.1f} kcal/day")
print(f"c_baseline: {c_baseline:.3f}")

# Predictions
y_train_pred = huber.predict(X_train_scaled)
y_test_pred = huber.predict(X_test_scaled)

train_r2 = r2_score(y_train, y_train_pred)
test_r2 = r2_score(y_test, y_test_pred)

# Calculate MAE in terms of fat mass
train_mae = mean_absolute_error(
    train['delta_fm_kg'].values,
    (train['intake_orthogonal'].values - y_train_pred) / 9675
)
test_mae = mean_absolute_error(
    test['delta_fm_kg'].values,
    (test['intake_orthogonal'].values - y_test_pred) / 9675
)

print("\n" + "-" * 80)
print("MODEL FIT METRICS")
print("-" * 80)

print(f"\nTraining set (2021-2024):")
print(f"  R² score: {train_r2:.3f}")
print(f"  MAE (fat mass): {train_mae:.3f} kg")

print(f"\nTest set (2025):")
print(f"  R² score: {test_r2:.3f}")
print(f"  MAE (fat mass): {test_mae:.3f} kg")

# Bootstrap CI
print("\n" + "-" * 80)
print("BOOTSTRAP CONFIDENCE INTERVALS (1000 iterations)")
print("-" * 80)

bootstrap_params = []
np.random.seed(42)
for i in range(1000):
    indices = np.random.choice(len(train), size=len(train), replace=True)
    X_boot = X_train_scaled[indices]
    y_boot = y_train[indices]
    
    try:
        huber_boot = HuberRegressor(epsilon=1.35, alpha=1e-3, fit_intercept=False)
        huber_boot.fit(X_boot, y_boot)
        
        beta_boot = huber_boot.coef_.copy()
        beta_boot[1] = beta_boot[1] / scaler.scale_[0]
        
        bootstrap_params.append([beta_boot[0]/14, -beta_boot[1]])
    except:
        continue

bootstrap_params = np.array(bootstrap_params)
ci_lower = np.percentile(bootstrap_params, 2.5, axis=0)
ci_upper = np.percentile(bootstrap_params, 97.5, axis=0)

print(f"\nBMR_avg: {bmr_avg:.1f} kcal/day")
print(f"  95% CI: [{ci_lower[0]:.1f}, {ci_upper[0]:.1f}]")

print(f"\nc_baseline: {c_baseline:.3f}")
print(f"  95% CI: [{ci_lower[1]:.3f}, {ci_upper[1]:.3f}]")

# Physiological plausibility
print("\n" + "=" * 80)
print("PHYSIOLOGICAL PLAUSIBILITY ASSESSMENT")
print("=" * 80)

plausible = True

if not (1200 <= bmr_avg <= 2200):
    print(f"⚠  BMR_avg = {bmr_avg:.1f} outside range [1200, 2200]")
    plausible = False

if not (0 <= c_baseline <= 1):
    print(f"⚠  c_baseline = {c_baseline:.3f} outside range [0, 1]")
    plausible = False

if plausible:
    print("✓ All parameters within physiologically plausible ranges!")

# Show sample predictions
print("\n" + "-" * 80)
print("SAMPLE PREDICTIONS (first 5 training windows)")
print("-" * 80)

sample = train.head(5).copy()
sample['y_pred'] = y_train_pred[:5]
sample['residual'] = y_train[:5] - y_train_pred[:5]
sample['fm_pred'] = (sample['intake_orthogonal'] - sample['y_pred']) / 9675

print(sample[['window_start', 'delta_fm_kg', 'fm_pred', 'residual']].to_string(index=False))

print("\n" + "=" * 80)
print("ANALYSIS COMPLETE")
print("=" * 80)

