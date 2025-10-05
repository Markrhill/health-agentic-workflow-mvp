#!/usr/bin/env python3
"""
Reproduce September 9th analysis from data1757445987065.csv

This script replicates the parameter estimation analysis that was performed
on September 9th, 2025, using 14-day windows and Huber regression.
"""

import pandas as pd
import numpy as np
from scipy import stats
from sklearn.linear_model import HuberRegressor

# Load and prep your data
df = pd.read_csv('data1757445987065.csv')
df['fact_date'] = pd.to_datetime(df['fact_date'])
df = df.sort_values('fact_date')

print(f"Loaded {len(df)} rows from {df['fact_date'].min()} to {df['fact_date'].max()}")

# Clean fat mass outliers (gentle Hampel)
fm = df['fat_mass_kg'].copy()
fm_median = fm.rolling(7, center=True, min_periods=1).median()
fm_mad = (fm - fm_median).abs().rolling(7, center=True, min_periods=1).median()
outliers = (fm - fm_median).abs() > 3 * fm_mad
df.loc[outliers, 'fat_mass_kg'] = np.nan

print(f"Fat mass coverage: {(~df['fat_mass_kg'].isna()).mean():.1%}")
print(f"Exercise zeros (rest days): {(df['workout_kcal'] == 0).mean():.1%}")

# Build 14-day windows for better SNR
windows = []
for i in range(0, len(df) - 13):
    window = df.iloc[i:i+14].copy()
    
    # Need start and end fat mass
    if pd.notna(window.iloc[0]['fat_mass_kg']) and pd.notna(window.iloc[-1]['fat_mass_kg']):
        # Need most days with data
        if window['fat_mass_kg'].notna().sum() >= 10:
            windows.append({
                'start_date': window.iloc[0]['fact_date'],
                'end_date': window.iloc[-1]['fact_date'],
                'delta_fm_kg': window.iloc[-1]['fat_mass_kg'] - window.iloc[0]['fat_mass_kg'],
                'intake_sum': window['intake_kcal'].sum(),
                'workout_sum': window['workout_kcal'].sum(),
                'days': 14,
                'intake_var': window['intake_kcal'].var(),
                'workout_var': window['workout_kcal'].var()
            })

windows_df = pd.DataFrame(windows)
print(f"Viable 14-day windows: {len(windows_df)}")

# Select high-information windows (high variance)
info_score = np.sqrt(windows_df['intake_var'] * windows_df['workout_var'])
high_info = windows_df[info_score > info_score.quantile(0.7)]
print(f"High-information windows: {len(high_info)}")

# Robust parameter fitting (Huber regression)
def fit_parameters(data):
    X = np.column_stack([
        data['days'],                    # BMR term
        data['workout_sum'],              # Exercise term  
        data['intake_sum']                # Intake term
    ])
    y = data['delta_fm_kg']
    
    # Huber regression (robust to outliers)
    huber = HuberRegressor(epsilon=1.35)
    huber.fit(X, y)
    
    # Extract parameters
    bmr_effect = huber.coef_[0]
    workout_effect = huber.coef_[1]
    intake_effect = huber.coef_[2]
    
    # Convert to interpretable params
    alpha = 1 / intake_effect  # kcal per kg fat
    compensation = 1 + (workout_effect * alpha)  # fraction compensated
    maintenance = -bmr_effect * alpha / 14  # daily maintenance
    
    return {
        'M_kcal_day': maintenance,
        'C_compensation': compensation,
        'alpha_kcal_kg': alpha
    }

# Fit on high-information windows
params = fit_parameters(high_info)

print("\n=== PARAMETERS FROM YOUR DATA ===")
print(f"M (maintenance): {params['M_kcal_day']:.0f} kcal/day")
print(f"C (compensation): {params['C_compensation']:.2f}")
print(f"α (kcal/kg fat): {params['alpha_kcal_kg']:.0f} kcal/kg")

# Bootstrap confidence intervals
n_bootstrap = 1000
bootstrap_params = []

for _ in range(n_bootstrap):
    sample = high_info.sample(n=len(high_info), replace=True)
    try:
        boot_params = fit_parameters(sample)
        bootstrap_params.append(boot_params)
    except:
        continue

params_df = pd.DataFrame(bootstrap_params)

print("\n=== 95% CONFIDENCE INTERVALS ===")
for col in params_df.columns:
    ci_low = params_df[col].quantile(0.025)
    ci_high = params_df[col].quantile(0.975)
    print(f"{col}: [{ci_low:.0f}, {ci_high:.0f}]")

# Validation: How well do these parameters predict 2025?
test_data = df[df['fact_date'] >= '2025-01-01'].copy()
test_windows = []

for i in range(0, len(test_data) - 13):
    window = test_data.iloc[i:i+14].copy()
    if pd.notna(window.iloc[0]['fat_mass_kg']) and pd.notna(window.iloc[-1]['fat_mass_kg']):
        test_windows.append({
            'delta_fm_actual': window.iloc[-1]['fat_mass_kg'] - window.iloc[0]['fat_mass_kg'],
            'intake_sum': window['intake_kcal'].sum(),
            'workout_sum': window['workout_kcal'].sum()
        })

if test_windows:
    test_df = pd.DataFrame(test_windows)
    
    # Predict using fitted parameters
    test_df['delta_fm_pred'] = (
        test_df['intake_sum'] - 
        (1 - params['C_compensation']) * test_df['workout_sum'] - 
        params['M_kcal_day'] * 14
    ) / params['alpha_kcal_kg']
    
    mae = np.abs(test_df['delta_fm_actual'] - test_df['delta_fm_pred']).mean()
    print(f"\n2025 Test MAE: {mae:.2f} kg over 14 days")
    
    # Calculate R² on training data
    train_pred = (
        high_info['intake_sum'] - 
        (1 - params['C_compensation']) * high_info['workout_sum'] - 
        params['M_kcal_day'] * 14
    ) / params['alpha_kcal_kg']
    
    ss_res = np.sum((high_info['delta_fm_kg'] - train_pred) ** 2)
    ss_tot = np.sum((high_info['delta_fm_kg'] - high_info['delta_fm_kg'].mean()) ** 2)
    r_squared = 1 - (ss_res / ss_tot)
    
    print(f"R² on training: {r_squared:.2f}")

print("\n=== COMPARISON TO EXPECTED RESULTS ===")
print("Expected from September 9th:")
print("M = 1647 kcal/day")
print("C = 0.21")
print("α = 9650 kcal/kg")
print("2025 Test MAE: 0.31 kg per 14-day window")
print("R² on training: 0.72")
