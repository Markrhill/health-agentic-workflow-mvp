#!/usr/bin/env python3
"""
2-Parameter Direct Delta Fat Mass Model
Fixed: BMR = 1,944 kcal/day (Katch-McArdle)
Estimate: α (kcal/kg fat), c (exercise compensation)
Uses: 14-day non-overlapping windows, Kalman-filtered fat mass, orthogonalized intake
"""

import pandas as pd
import numpy as np
from sklearn.linear_model import HuberRegressor, LinearRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import r2_score, mean_absolute_error

# Constants
BMR_FIXED = 1944  # Katch-McArdle formula result

# Load data
df = pd.read_csv('data/parameter_estimation/nonoverlapping_14day_windows_2025-10-02.csv')
train = df[df['dataset_split'] == 'TRAIN'].copy()
test = df[df['dataset_split'] == 'TEST'].copy()

print("=" * 80)
print("2-PARAMETER DIRECT MODEL (FIXED BMR = 1,944 kcal/day)")
print("=" * 80)
print(f"Training windows: {len(train)}")
print(f"Test windows: {len(test)}")

# ============================================================================
# STEP 1: ORTHOGONALIZE INTAKE ON WORKOUT
# ============================================================================
print("\n" + "-" * 80)
print("ORTHOGONALIZATION: INTAKE ~ WORKOUT")
print("-" * 80)

ortho = LinearRegression()
ortho.fit(train['total_workout_kcal'].values.reshape(-1, 1), 
          train['total_intake_kcal'].values)

train['intake_ortho'] = train['total_intake_kcal'] - ortho.predict(
    train['total_workout_kcal'].values.reshape(-1, 1))
test['intake_ortho'] = test['total_intake_kcal'] - ortho.predict(
    test['total_workout_kcal'].values.reshape(-1, 1))

corr_before = train[['total_intake_kcal', 'total_workout_kcal']].corr().iloc[0,1]
corr_after = train[['intake_ortho', 'total_workout_kcal']].corr().iloc[0,1]

print(f"Correlation before: {corr_before:.3f}")
print(f"Correlation after: {corr_after:.3f}")
print(f"Glycogen refueling rate: {ortho.coef_[0]:.3f} kcal intake per kcal workout")

# ============================================================================
# STEP 2: BUILD DESIGN MATRIX FOR DIRECT DELTA_FM MODELING
# ============================================================================
# Energy balance: ΔFat = (Intake - BMR*days - (1-c)*Workout) / α
# With fixed BMR: ΔFat = (Intake - BMR_fixed*days) / α - ((1-c)/α)*Workout
# Rearranged: ΔFat = β_intake * Intake - β_workout * Workout - (BMR_fixed*days)/α
# Where: α = 1/β_intake, c = 1 + α*β_workout

print("\n" + "-" * 80)
print("DESIGN MATRIX")
print("-" * 80)

# Target: observed fat mass change
y_train = train['delta_fm_kg'].values
y_test = test['delta_fm_kg'].values

# Predictors: intake_ortho, workout, bmr_deficit
# Note: BMR contribution is (BMR_FIXED * 14 days) kcal consumed
# This must be subtracted from available energy
train['bmr_contribution_kg'] = (BMR_FIXED * 14) / 9000  # Rough α for scaling
test['bmr_contribution_kg'] = (BMR_FIXED * 14) / 9000

X_train = np.column_stack([
    train['intake_ortho'].values,
    train['total_workout_kcal'].values,
    np.ones(len(train))  # Intercept for BMR offset
])

X_test = np.column_stack([
    test['intake_ortho'].values,
    test['total_workout_kcal'].values,
    np.ones(len(test))
])

# ============================================================================
# STEP 3: STANDARDIZE AND FIT
# ============================================================================
print("\n" + "-" * 80)
print("FITTING HUBER REGRESSOR")
print("-" * 80)

scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)

huber = HuberRegressor(epsilon=1.35, alpha=1e-3, fit_intercept=False)
huber.fit(X_train_scaled, y_train)

# Unscale coefficients
beta_scaled = huber.coef_
beta = beta_scaled / scaler.scale_

beta_intake, beta_workout, beta_intercept = beta

print(f"β_intake (scaled): {beta_intake:.9f}")
print(f"β_workout (scaled): {beta_workout:.9f}")
print(f"β_intercept: {beta_intercept:.6f}")

# ============================================================================
# STEP 4: EXTRACT PHYSIOLOGICAL PARAMETERS
# ============================================================================
print("\n" + "=" * 80)
print("ESTIMATED PARAMETERS")
print("=" * 80)

# From energy balance with fixed BMR:
# ΔFat = (Intake - BMR_fixed*days - (1-c)*Workout) / α
α = 1.0 / beta_intake
c = 1.0 + α * beta_workout

print(f"\nBMR (fixed): {BMR_FIXED:,.0f} kcal/day")
print(f"α (kcal/kg fat): {α:,.0f}")
print(f"c (compensation): {c:.3f}")

# ============================================================================
# STEP 5: EVALUATE PREDICTIONS
# ============================================================================
print("\n" + "-" * 80)
print("MODEL PERFORMANCE")
print("-" * 80)

y_train_pred = huber.predict(X_train_scaled)
y_test_pred = huber.predict(X_test_scaled)

train_r2 = r2_score(y_train, y_train_pred)
test_r2 = r2_score(y_test, y_test_pred)
train_mae = mean_absolute_error(y_train, y_train_pred)
test_mae = mean_absolute_error(y_test, y_test_pred)

print(f"\nTraining (2021-2024):")
print(f"  R²: {train_r2:.3f}")
print(f"  MAE: {train_mae:.3f} kg per 14 days")

print(f"\nTest (2025):")
print(f"  R²: {test_r2:.3f}")
print(f"  MAE: {test_mae:.3f} kg per 14 days")

# ============================================================================
# STEP 6: PLAUSIBILITY CHECKS
# ============================================================================
print("\n" + "=" * 80)
print("PLAUSIBILITY ASSESSMENT")
print("=" * 80)

alpha_ok = 7000 <= α <= 12000
c_ok = 0.0 <= c <= 0.5

print(f"α in [7,000-12,000]: {'✓' if alpha_ok else '✗ FAIL'}")
print(f"c in [0.0-0.5]: {'✓' if c_ok else '✗ FAIL'}")
print(f"Test MAE < 0.5 kg: {'✓' if test_mae < 0.5 else '✗ FAIL'}")

if alpha_ok and c_ok and test_mae < 0.5:
    print("\n✓ MODEL READY FOR PRODUCTION")
else:
    print("\n✗ MODEL NEEDS REFINEMENT")

# ============================================================================
# STEP 7: SAMPLE PREDICTIONS
# ============================================================================
print("\n" + "-" * 80)
print("SAMPLE PREDICTIONS (First 5 Train, First 5 Test)")
print("-" * 80)

sample_train = train.head(5).copy()
sample_train['pred_delta_kg'] = y_train_pred[:5]
sample_train['error_kg'] = sample_train['delta_fm_kg'] - sample_train['pred_delta_kg']

print("\nTraining:")
print(sample_train[['window_start', 'delta_fm_kg', 'pred_delta_kg', 'error_kg']].to_string(index=False))

if len(test) >= 5:
    sample_test = test.head(5).copy()
    sample_test['pred_delta_kg'] = y_test_pred[:5]
    sample_test['error_kg'] = sample_test['delta_fm_kg'] - sample_test['pred_delta_kg']
    
    print("\nTest:")
    print(sample_test[['window_start', 'delta_fm_kg', 'pred_delta_kg', 'error_kg']].to_string(index=False))

print("\n" + "=" * 80)
print("ANALYSIS COMPLETE")
print("=" * 80)

