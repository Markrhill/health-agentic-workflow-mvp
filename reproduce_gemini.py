#!/usr/bin/env python3
"""
Reproduce Gemini parameter estimation analysis

This script replicates the stabilized parameter estimation that was used
to generate the Gemini parameters stored in model_params_timevarying.
"""

import pandas as pd
import numpy as np
from sklearn.linear_model import HuberRegressor, LinearRegression
from sklearn.preprocessing import StandardScaler

# ---------------------------
# Helpers
# ---------------------------

def robust_clean(series, window=7, k=3.0):
    s = series.astype(float).copy()
    med = s.rolling(window, center=True, min_periods=1).median()
    mad = (s - med).abs().rolling(window, center=True, min_periods=1).median()
    mad = mad.replace(0, np.nan).ffill().bfill()
    s[(s - med).abs() > k * mad] = np.nan
    return s

def build_windows(df, window_days=14):
    rows = []
    n = len(df)
    for i in range(n - window_days + 1):
        w = df.iloc[i:i+window_days]
        if (pd.notna(w.iloc[0]['fat_mass_kg']) and
            pd.notna(w.iloc[-1]['fat_mass_kg']) and
            w['fat_mass_kg'].notna().sum() >= 10 and
            w['fat_free_mass_kg'].notna().sum() >= 10):
            rows.append({
                'delta_fm_kg': float(w.iloc[-1]['fat_mass_kg'] - w.iloc[0]['fat_mass_kg']),
                'intake_sum': float(w['intake_kcal'].sum()),
                'workout_sum': float(w['workout_kcal'].sum()),
                'mean_lbm': float(w['fat_free_mass_kg'].mean()),
                'days': int(window_days)
            })
    return pd.DataFrame(rows)

def orthogonalize_workout(intake_sum, workout_sum):
    # regress workout on intake; return residuals (workout ⟂ intake)
    X = intake_sum.values.reshape(-1, 1)
    y = workout_sum.values
    lr = LinearRegression().fit(X, y)
    resid = y - lr.predict(X)
    return resid

def fit_parameters_corrected_robust(windows_df, epsilon=1.35, max_iter=1000, huber_alpha=1e-3):
    """
    Corrected & stabilized with two key upgrades:
    - workout_sum -> workout_resid (orthogonalized vs intake_sum)
    - days*mean_lbm -> days*(mean_lbm - global_mean_lbm)  (re-center)
    """
    if len(windows_df) < 8:
        raise ValueError("Not enough windows to fit (need >= 8).")

    # Build stabilized features
    w = windows_df.copy()
    w['workout_resid'] = orthogonalize_workout(w['intake_sum'], w['workout_sum'])
    global_mean_lbm = w['mean_lbm'].mean()
    w['days_lbm_centered'] = w['days'] * (w['mean_lbm'] - global_mean_lbm)

    y = w['delta_fm_kg'].values
    X = np.column_stack([
        w['days'].values,
        w['days_lbm_centered'].values,
        w['workout_resid'].values,
        w['intake_sum'].values
    ])

    scaler = StandardScaler(with_mean=True, with_std=True)
    Xs = scaler.fit_transform(X)

    huber = HuberRegressor(epsilon=epsilon, max_iter=max_iter, alpha=huber_alpha, fit_intercept=False)
    huber.fit(Xs, y)
    beta = huber.coef_ / scaler.scale_

    beta_days, beta_days_lbm_c, beta_workout_resid, beta_intake = beta

    # Map back to physiology
    if beta_intake <= 0:
        # This should not happen with orthogonalization + ridge; guardrail:
        beta_intake = np.nextafter(0, 1)

    alpha = 1.0 / beta_intake
    # Undo the orthogonalization: C is defined on true workout_sum, but the compensation term is driven by
    # the coefficient on the workout component orthogonal to intake, which is exactly what we fit.
    C = 1.0 + alpha * beta_workout_resid

    # Undo the centering on LBM:
    # days * mean_lbm = days * ( (mean_lbm - global_mean) + global_mean )
    # beta_days_lbm_c multiplies the centered part; the global_mean contribution moves into BMR0
    BMR0 = -alpha * (beta_days + beta_days_lbm_c * ( - global_mean_lbm ))

    k_lbm = -alpha * beta_days_lbm_c

    # Physiological non-negativity
    BMR0 = max(0.0, BMR0)
    k_lbm = max(0.0, k_lbm)

    return dict(alpha=alpha, C=C, BMR0=BMR0, k_lbm=k_lbm)

# ---------------------------
# Load & prep
# ---------------------------
df = pd.read_csv('daily_facts_no_NULL.csv')
df['workout_kcal'] = df['workout_kcal'].fillna(0)
df['fact_date'] = pd.to_datetime(df['fact_date'])
df = df.sort_values('fact_date').reset_index(drop=True)
df['fat_mass_kg'] = robust_clean(df['fat_mass_kg'])
df['fat_free_mass_kg'] = robust_clean(df['fat_free_mass_kg'])

print(f"Loaded {len(df)} rows from {df['fact_date'].min()} to {df['fact_date'].max()}")
print(f"Fat mass coverage: {(~df['fat_mass_kg'].isna()).mean():.1%}")
print(f"LBM coverage: {(~df['fat_free_mass_kg'].isna()).mean():.1%}")

# ---------------------------
# 1) FULL-PERIOD FIT (should match Gemini)
# ---------------------------
W = build_windows(df, 14)
print(f"Viable 14-day windows: {len(W)}")

p = fit_parameters_corrected_robust(W, epsilon=1.35, max_iter=1000, huber_alpha=1e-3)
print("\n--- FULL-PERIOD (orthogonalized + centered, stabilized) ---")
print(f"α (kcal/kg):      {p['alpha']:,.0f}")
print(f"C (comp):         {p['C']:.2f}")
print(f"BMR₀ (kcal/day):  {p['BMR0']:.0f}")
print(f"k_LBM (kcal/kg):  {p['k_lbm']:.1f}")

# Agreement check vs Gemini targets
target_full = dict(alpha=9710.0, C=0.16, BMR0=785.0, k_lbm=11.5)
tol_full = dict(alpha=200, C=0.02, BMR0=40, k_lbm=1.0)

print("\n--- AGREEMENT CHECK (full-period vs Gemini) ---")
ok_full = True
for k in target_full:
    got, tgt, tol = p[k], target_full[k], tol_full[k]
    ok = abs(got - tgt) <= tol
    ok_full &= ok
    print(f"{k:>5}: got {got:.3f}, tgt {tgt:.3f}, Δ={got-tgt:+.3f}  -> {'OK' if ok else 'OFF'} (±{tol})")

# ---------------------------
# 2) MONTHLY "Bayesian" UPDATES (12-week lookback, 0.9/0.1 blend)
# ---------------------------
def fit_recent(df_recent):
    w = build_windows(df_recent, 14)
    if len(w) < 8:
        return None
    return fit_parameters_corrected_robust(w, epsilon=1.35, max_iter=1000, huber_alpha=1e-3)

current = {
    'BMR Intercept': p['BMR0'],
    'BMR Scaling Factor': p['k_lbm'],
    'C (compensation)': p['C'],
    'α (kcal/kg)': p['alpha']
}

snapshots = ['2021-01-01','2022-01-01','2023-01-01','2024-01-01','2025-01-01','2025-07-31']
snap = {s: None for s in snapshots}
snap['2021-01-01'] = current.copy()

for month_end in pd.date_range(start=df['fact_date'].min(), end=df['fact_date'].max(), freq='M'):
    start_window = month_end - pd.DateOffset(weeks=12)
    recent = df[(df['fact_date'] > start_window) & (df['fact_date'] <= month_end)]
    est = fit_recent(recent)
    if est is not None:
        m = {'BMR Intercept': est['BMR0'], 'BMR Scaling Factor': est['k_lbm'], 'C (compensation)': est['C'], 'α (kcal/kg)': est['alpha']}
        for k in current:
            current[k] = 0.90 * current[k] + 0.10 * m[k]
    for d in snapshots:
        ts = pd.to_datetime(d)
        if month_end >= ts and snap[d] is None:
            snap[d] = current.copy()

print("\n--- SNAPSHOTS (Monthly updates with stabilized inner fit) ---")
print("Date         |  BMR₀   |  k_LBM  |   C   |   α")
for d in snapshots:
    p2 = snap[d]
    print(f"{d} | {p2['BMR Intercept']:6.0f} | {p2['BMR Scaling Factor']:6.1f} | {p2['C (compensation)']:5.2f} | {p2['α (kcal/kg)']:5.0f}")

# Gemini snapshot targets and tolerances
gemini_snap = {
    '2021-01-01': dict(BMR=747, k=12.1, C=0.15, a=9655),
    '2022-01-01': dict(BMR=745, k=12.1, C=0.16, a=9680),
    '2023-01-01': dict(BMR=738, k=12.2, C=0.18, a=9640),
    '2024-01-01': dict(BMR=735, k=12.2, C=0.17, a=9660),
    '2025-01-01': dict(BMR=731, k=12.1, C=0.16, a=9670),
    '2025-07-31': dict(BMR=728, k=12.1, C=0.15, a=9675),
}
snap_tol = dict(BMR=25, k=0.6, C=0.03, a=200)

print("\n--- AGREEMENT CHECK (snapshots vs Gemini) ---")
ok_snap = True
for d in snapshots:
    pp = snap[d]; tt = gemini_snap[d]
    flag = (
        abs(pp['BMR Intercept']      - tt['BMR']) <= snap_tol['BMR'] and
        abs(pp['BMR Scaling Factor'] - tt['k'])   <= snap_tol['k']   and
        abs(pp['C (compensation)']   - tt['C'])   <= snap_tol['C']   and
        abs(pp['α (kcal/kg)']        - tt['a'])   <= snap_tol['a']
    )
    ok_snap &= flag
    print(f"{d}: {'OK' if flag else 'OFF'}  "
          f"BMR Δ={pp['BMR Intercept']-tt['BMR']:+5.1f}, "
          f"k Δ={pp['BMR Scaling Factor']-tt['k']:+4.1f}, "
          f"C Δ={pp['C (compensation)']-tt['C']:+5.2f}, "
          f"α Δ={pp['α (kcal/kg)']-tt['a']:+5.0f}")

print("\n=== SUMMARY ===")
print(f"Full-period agreement: {'PASS' if ok_full else 'CHECK'}")
print(f"Snapshot agreement:    {'PASS' if ok_snap else 'CHECK'}")
