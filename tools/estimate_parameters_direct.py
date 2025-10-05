#!/usr/bin/env python3
"""
Direct Delta Fat Mass Model (Gemini Approach)
Estimates: α, c, BMR_avg simultaneously
Uses: 14-day windows, Kalman-filtered fat mass
"""

import pandas as pd
import numpy as np
from sklearn.linear_model import HuberRegressor, LinearRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import r2_score, mean_absolute_error

# Load 14-day windows
df = pd.read_csv('data/parameter_estimation/nonoverlapping_14day_windows_2025-10-02.csv')
df['window_days'] = 14  # All windows are 14 days

train = df[df['dataset_split'] == 'TRAIN'].copy()
test = df[df['dataset_split'] == 'TEST'].copy()

print("=" * 80)
print("DIRECT DELTA FAT MASS MODEL (GEMINI APPROACH)")
print("=" * 80)
print(f"\nTraining windows (14-day): {len(train)}")
print(f"Test windows (14-day): {len(test)}")

# ============================================================================
# ORTHOGONALIZATION: Intake on Workout (Exercise causes eating)
# ============================================================================
print("\n" + "=" * 80)
print("ORTHOGONALIZATION")
print("=" * 80)

ortho = LinearRegression()
ortho.fit(train['total_workout_kcal'].values.reshape(-1, 1), 
          train['total_intake_kcal'].values)

train['intake_ortho'] = train['total_intake_kcal'] - ortho.predict(
    train['total_workout_kcal'].values.reshape(-1, 1))
test['intake_ortho'] = test['total_intake_kcal'] - ortho.predict(
    test['total_workout_kcal'].values.reshape(-1, 1))

print(f"Correlation before: {train[['total_intake_kcal', 'total_workout_kcal']].corr().iloc[0,1]:.3f}")
print(f"Correlation after: {train[['intake_ortho', 'total_workout_kcal']].corr().iloc[0,1]:.3f}")
print(f"Refueling rate: {ortho.coef_[0]:.3f} kcal intake per kcal workout")

# ============================================================================
# DIRECT MODELING: delta_fm = f(days, workout, intake_ortho)
# ============================================================================
# Energy balance: ΔFat = (Intake - BMR*days - (1-c)*Workout) / α
# Rearranged: ΔFat = β_days*days + β_workout*workout + β_intake*intake_ortho
# Where: α = 1/β_intake, c = 1 + α*β_workout, BMR = -α*β_days

print("\n" + "=" * 80)
print("BUILDING DESIGN MATRIX FOR DIRECT MODELING")
print("=" * 80)

y_train = train['delta_fm_kg'].values
X_train = np.column_stack([
    train['window_days'].values,           # days term → BMR
    train['total_workout_kcal'].values,    # workout term → c
    train['intake_ortho'].values           # intake term → α
])

y_test = test['delta_fm_kg'].values
X_test = np.column_stack([
    test['window_days'].values,
    test['total_workout_kcal'].values,
    test['intake_ortho'].values
])

print(f"y = delta_fm_kg (direct modeling)")
print(f"X features: [days, workout, intake_orthogonal]")

# Standardize
print("\n" + "=" * 80)
print("STANDARDIZING FEATURES")
print("=" * 80)

scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)

print(f"Feature means: {scaler.mean_}")
print(f"Feature stds: {scaler.scale_}")

# Fit Huber regression
print("\n" + "=" * 80)
print("FITTING HUBER REGRESSION")
print("=" * 80)

huber = HuberRegressor(epsilon=1.35, alpha=1e-3, fit_intercept=False)
huber.fit(X_train_scaled, y_train)

# Unscale coefficients
beta_scaled = huber.coef_
beta = beta_scaled / scaler.scale_

beta_days, beta_workout, beta_intake = beta

print(f"\nScaled coefficients: {beta_scaled}")
print(f"Unscaled coefficients: {beta}")

print("\n" + "=" * 80)
print("RAW REGRESSION COEFFICIENTS")
print("=" * 80)
print(f"β_days:    {beta_days:.9f}")
print(f"β_workout: {beta_workout:.9f}")
print(f"β_intake:  {beta_intake:.9f}")

# ============================================================================
# EXTRACT PHYSIOLOGICAL PARAMETERS
# ============================================================================
# From energy balance equation:
# ΔFat = (1/α)*intake - (1/α)*BMR*days - ((1-c)/α)*workout
# Therefore:
if abs(beta_intake) < 1e-9:
    print("\n⚠️  WARNING: β_intake too small, cannot extract α")
    alpha = np.nan
    c = np.nan
    BMR_avg = np.nan
else:
    alpha = 1.0 / beta_intake
    c = 1.0 + alpha * beta_workout  
    BMR_avg = -alpha * beta_days / 14  # Divide by 14 for per-day BMR

print("\n" + "=" * 80)
print("ESTIMATED PHYSIOLOGICAL PARAMETERS")
print("=" * 80)
print(f"α (kcal/kg fat):     {alpha:,.0f}")
print(f"c (compensation):    {c:.3f}")
print(f"BMR_avg (kcal/day):  {BMR_avg:.1f}")

# ============================================================================
# EVALUATE PREDICTIONS
# ============================================================================
y_train_pred = huber.predict(X_train_scaled)
y_test_pred = huber.predict(X_test_scaled)

# Metrics
train_r2 = r2_score(y_train, y_train_pred)
test_r2 = r2_score(y_test, y_test_pred)
train_mae = mean_absolute_error(y_train, y_train_pred)
test_mae = mean_absolute_error(y_test, y_test_pred)

print("\n" + "=" * 80)
print("MODEL FIT")
print("=" * 80)
print(f"Training R²:  {train_r2:.3f}")
print(f"Training MAE: {train_mae:.3f} kg")
print(f"Test R²:      {test_r2:.3f}")
print(f"Test MAE:     {test_mae:.3f} kg")

# Residual analysis
train_residuals = y_train - y_train_pred
test_residuals = y_test - y_test_pred

print(f"\nTraining residuals:")
print(f"  Mean: {train_residuals.mean():+.3f} kg")
print(f"  Std:  {train_residuals.std():.3f} kg")

if len(test_residuals) > 0:
    print(f"\nTest residuals:")
    print(f"  Mean: {test_residuals.mean():+.3f} kg")
    print(f"  Std:  {test_residuals.std():.3f} kg")

# Plausibility checks
print("\n" + "=" * 80)
print("PLAUSIBILITY ASSESSMENT")
print("=" * 80)

if not np.isnan(alpha):
    alpha_ok = 7000 <= alpha <= 12000
    c_ok = 0.0 <= c <= 0.5
    bmr_ok = 1200 <= BMR_avg <= 2200

    print(f"α in [7,000, 12,000]:  {alpha:,.0f}  {'✓ PASS' if alpha_ok else '✗ FAIL'}")
    print(f"c in [0.0, 0.5]:       {c:.3f}   {'✓ PASS' if c_ok else '✗ FAIL'}")
    print(f"BMR in [1,200, 2,200]: {BMR_avg:.0f}   {'✓ PASS' if bmr_ok else '✗ FAIL'}")
    
    if alpha_ok and c_ok and bmr_ok:
        print("\n✓✓✓ ALL PARAMETERS PHYSIOLOGICALLY PLAUSIBLE!")
    else:
        print("\n⚠️  Some parameters outside physiological ranges")
else:
    print("⚠️  Cannot assess plausibility - invalid beta_intake")

# ============================================================================
# BOOTSTRAP CONFIDENCE INTERVALS
# ============================================================================
print("\n" + "=" * 80)
print("BOOTSTRAP CONFIDENCE INTERVALS (1000 iterations)")
print("=" * 80)

bootstrap_params = []
np.random.seed(42)

for i in range(1000):
    indices = np.random.choice(len(train), size=len(train), replace=True)
    X_boot = X_train_scaled[indices]
    y_boot = y_train[indices]
    
    try:
        huber_boot = HuberRegressor(epsilon=1.35, alpha=1e-3, fit_intercept=False)
        huber_boot.fit(X_boot, y_boot)
        
        beta_boot = huber_boot.coef_ / scaler.scale_
        beta_days_boot, beta_workout_boot, beta_intake_boot = beta_boot
        
        if abs(beta_intake_boot) > 1e-9:
            alpha_boot = 1.0 / beta_intake_boot
            c_boot = 1.0 + alpha_boot * beta_workout_boot
            bmr_boot = -alpha_boot * beta_days_boot / 14
            
            bootstrap_params.append({
                'alpha': alpha_boot,
                'c': c_boot,
                'bmr': bmr_boot
            })
    except:
        continue

if len(bootstrap_params) > 50:
    params_df = pd.DataFrame(bootstrap_params)
    
    print(f"\nSuccessful bootstrap iterations: {len(bootstrap_params)}")
    
    for param, label in [('alpha', 'α (kcal/kg)'), ('c', 'c (compensation)'), ('bmr', 'BMR (kcal/day)')]:
        mean_val = params_df[param].mean()
        ci_low = params_df[param].quantile(0.025)
        ci_high = params_df[param].quantile(0.975)
        print(f"\n{label}:")
        print(f"  Mean: {mean_val:,.1f}")
        print(f"  95% CI: [{ci_low:,.1f}, {ci_high:,.1f}]")
else:
    print("⚠️  Insufficient successful bootstrap iterations")

# ============================================================================
# SAMPLE PREDICTIONS
# ============================================================================
print("\n" + "=" * 80)
print("SAMPLE PREDICTIONS (first 5 training windows)")
print("=" * 80)

sample = train.head(5).copy()
sample['predicted_delta_fm'] = y_train_pred[:5]
sample['residual'] = y_train[:5] - y_train_pred[:5]

print(sample[['window_start', 'delta_fm_kg', 'predicted_delta_fm', 'residual']].to_string(index=False))

print("\n" + "=" * 80)
print("ANALYSIS COMPLETE")
print("=" * 80)

