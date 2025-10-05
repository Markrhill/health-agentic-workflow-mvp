#!/usr/bin/env python3
"""
Baseline Volume Parameter Estimation

Fits 3 parameters on low/mid volume windows (< 600 kcal/day) with LBM stability:
- BMR₀ (intercept, kcal/day)
- k_LBM (BMR per kg LBM, kcal/day/kg)  
- c_baseline (compensation factor, 0-1)

Model: y_deficit = 14×(BMR₀ + k_LBM×LBM) + c_baseline×workout

Where: y_deficit = intake - workout - ΔFM×9675
"""

import pandas as pd
import numpy as np
from sklearn.linear_model import HuberRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import r2_score, mean_absolute_error
import sys

def fit_baseline_parameters(csv_path: str):
    """
    Fit parameters using Huber regression on baseline/mid volume windows.
    
    Args:
        csv_path: Path to CSV with biweekly windows
        
    Returns:
        dict with fitted parameters and diagnostics
    """
    
    # Load data
    df = pd.read_csv(csv_path)
    train = df[df['dataset_split'] == 'TRAIN'].copy()
    test = df[df['dataset_split'] == 'TEST'].copy()
    
    print("=" * 80)
    print("BASELINE PARAMETER ESTIMATION")
    print("=" * 80)
    
    print(f"\nData loaded:")
    print(f"  Training windows: {len(train)} (2021-2024)")
    print(f"  Test windows: {len(test)} (2025)")
    print(f"  Workout range: {train['avg_daily_workout_kcal'].min():.0f} - {train['avg_daily_workout_kcal'].max():.0f} kcal/day")
    print(f"  LBM range: {train['lbm_avg_kg'].min():.1f} - {train['lbm_avg_kg'].max():.1f} kg")
    
    # Prepare features
    # Model: y = 14×b₀ + 14×b₁×LBM + c×workout
    
    y_train = train['y_deficit'].values
    
    X_train = np.column_stack([
        np.ones(len(train)),  # Intercept → 14×BMR₀
        train['lbm_avg_kg'].values,  # → 14×k_LBM
        train['total_workout_kcal'].values  # → c_baseline
    ])
    
    # Standardize features (except intercept)
    scaler = StandardScaler()
    X_train_scaled = X_train.copy()
    X_train_scaled[:, 1:] = scaler.fit_transform(X_train[:, 1:])
    
    # Fit Huber regressor
    print("\n" + "-" * 80)
    print("FITTING HUBER REGRESSOR")
    print("-" * 80)
    
    huber = HuberRegressor(epsilon=1.35, max_iter=500, alpha=1e-3, fit_intercept=False)
    huber.fit(X_train_scaled, y_train)
    
    # Unscale coefficients
    beta = huber.coef_.copy()
    beta[1:] = beta[1:] / scaler.scale_
    
    # Extract parameters
    bmr_intercept = beta[0] / 14  # Divide by days
    bmr_per_kg_lbm = beta[1] / 14  # Divide by days
    c_baseline = -beta[2]  # Negative because compensation reduces y_deficit
    
    print(f"Raw coefficients: {huber.coef_}")
    print(f"Unscaled coefficients: {beta}")
    
    # Calculate predictions
    y_train_pred = X_train @ beta
    y_test_pred = None
    
    if len(test) > 0:
        X_test = np.column_stack([
            np.ones(len(test)),
            test['lbm_avg_kg'].values,
            test['total_workout_kcal'].values
        ])
        y_test = test['y_deficit'].values
        y_test_pred = X_test @ beta
    
    # Model diagnostics
    r2_train = r2_score(y_train, y_train_pred)
    mae_train = mean_absolute_error(
        train['delta_fm_kg'].values, 
        (train['total_intake_kcal'].values - y_train_pred) / 9675
    )
    
    print("\n" + "=" * 80)
    print("FITTED PARAMETERS")
    print("=" * 80)
    
    print(f"\nBMR Model: BMR = {bmr_intercept:.1f} + {bmr_per_kg_lbm:.2f} × LBM_kg")
    print(f"\nCompensation Factor:")
    print(f"  c_baseline: {c_baseline:.3f}")
    
    # Calculate typical BMR
    mean_lbm = train['lbm_avg_kg'].mean()
    typical_bmr = bmr_intercept + bmr_per_kg_lbm * mean_lbm
    print(f"\nTypical BMR (at {mean_lbm:.1f} kg LBM): {typical_bmr:.0f} kcal/day")
    
    print("\n" + "-" * 80)
    print("MODEL FIT METRICS")
    print("-" * 80)
    
    print(f"\nTraining set (2021-2024):")
    print(f"  R² score: {r2_train:.3f}")
    print(f"  MAE (fat mass): {mae_train:.3f} kg")
    
    if len(test) > 0:
        r2_test = r2_score(y_test, y_test_pred)
        mae_test = mean_absolute_error(
            test['delta_fm_kg'].values,
            (test['total_intake_kcal'].values - y_test_pred) / 9675
        )
        print(f"\nTest set (2025):")
        print(f"  R² score: {r2_test:.3f}")
        print(f"  MAE (fat mass): {mae_test:.3f} kg")
    
    # Bootstrap confidence intervals
    print("\n" + "-" * 80)
    print("BOOTSTRAP CONFIDENCE INTERVALS (1000 iterations)")
    print("-" * 80)
    
    n_bootstrap = 1000
    bootstrap_params = []
    
    for _ in range(n_bootstrap):
        indices = np.random.choice(len(train), size=len(train), replace=True)
        X_boot = X_train_scaled[indices]
        y_boot = y_train[indices]
        
        try:
            huber_boot = HuberRegressor(epsilon=1.35, max_iter=500, alpha=1e-3, fit_intercept=False)
            huber_boot.fit(X_boot, y_boot)
            
            beta_boot = huber_boot.coef_.copy()
            beta_boot[1:] = beta_boot[1:] / scaler.scale_
            
            bmr0_boot = beta_boot[0] / 14
            k_lbm_boot = beta_boot[1] / 14
            c_boot = -beta_boot[2]
            
            bootstrap_params.append({
                'bmr_intercept': bmr0_boot,
                'bmr_per_kg_lbm': k_lbm_boot,
                'c_baseline': c_boot
            })
        except:
            continue
    
    params_df = pd.DataFrame(bootstrap_params)
    
    for col, label in [
        ('bmr_intercept', 'BMR intercept'),
        ('bmr_per_kg_lbm', 'BMR per kg LBM'),
        ('c_baseline', 'c_baseline')
    ]:
        value = params_df[col].mean()
        ci_low = params_df[col].quantile(0.025)
        ci_high = params_df[col].quantile(0.975)
        unit = 'kcal/day' if 'intercept' in col else 'kcal/day/kg' if 'kg' in col else ''
        print(f"\n{label}: {value:.3f} {unit}")
        print(f"  95% CI: [{ci_low:.3f}, {ci_high:.3f}]")
    
    # Physiological plausibility
    print("\n" + "=" * 80)
    print("PHYSIOLOGICAL PLAUSIBILITY ASSESSMENT")
    print("=" * 80)
    
    plausible = True
    
    if not (10 <= bmr_per_kg_lbm <= 30):
        print(f"⚠  BMR per kg LBM = {bmr_per_kg_lbm:.2f} outside range [10, 30]")
        plausible = False
    
    if not (0 <= c_baseline <= 1):
        print(f"⚠  c_baseline = {c_baseline:.3f} outside range [0, 1]")
        plausible = False
    
    if not (1200 <= typical_bmr <= 2200):
        print(f"⚠  Typical BMR = {typical_bmr:.0f} outside range [1200, 2200]")
        plausible = False
    
    if plausible:
        print("✓ All parameters within physiologically plausible ranges!")
    
    print("\n" + "=" * 80)
    print("ANALYSIS COMPLETE")
    print("=" * 80)
    
    return {
        'bmr_intercept': bmr_intercept,
        'bmr_per_kg_lbm': bmr_per_kg_lbm,
        'c_baseline': c_baseline,
        'typical_bmr': typical_bmr,
        'r2_train': r2_train,
        'mae_train': mae_train,
        'r2_test': r2_test if len(test) > 0 else None,
        'mae_test': mae_test if len(test) > 0 else None,
        'n_train': len(train),
        'n_test': len(test)
    }


if __name__ == '__main__':
    csv_path = 'data/parameter_estimation/biweekly_windows_baseline_2025-10-02_v1.3.csv'
    
    if len(sys.argv) > 1:
        csv_path = sys.argv[1]
    
    results = fit_baseline_parameters(csv_path)

