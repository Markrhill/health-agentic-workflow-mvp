#!/usr/bin/env python3
"""
Compare Parameter Estimation Methods

This script compares our current parameter estimation approach with the original Gemini script
to understand the differences and identify potential issues.
"""

import os
import sys
import pandas as pd
import numpy as np
from sklearn.linear_model import HuberRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import r2_score, mean_absolute_error
from sqlalchemy import create_engine, text

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def robust_clean(series: pd.Series, window: int = 7, k: float = 3.0) -> pd.Series:
    """Robustly clean BIA sensor data using rolling median and MAD-based outlier detection."""
    s = series.copy()
    med = s.rolling(window, center=True, min_periods=1).median()
    mad = (s - med).abs().rolling(window, center=True, min_periods=1).median()
    mad = mad.replace(0, np.nan).ffill().bfill()
    mask = (s - med).abs() > k * mad
    s[mask] = np.nan
    return s

def build_windows(data: pd.DataFrame, window_days: int = 14) -> pd.DataFrame:
    """Build analysis windows with eligibility criteria."""
    rows = []
    for i in range(len(data) - window_days + 1):
        w = data.iloc[i:i+window_days]
        
        # Eligibility criteria
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

def load_daily_data(engine, start_date: str = None, end_date: str = None) -> pd.DataFrame:
    """Load daily facts data from database."""
    query = """
        SELECT 
            fact_date,
            intake_kcal,
            workout_kcal,
            fat_mass_kg,
            fat_free_mass_kg,
            weight_kg
        FROM daily_facts
        WHERE fat_mass_kg IS NOT NULL
    """
    
    params = {}
    if start_date:
        query += " AND fact_date >= :start_date"
        params['start_date'] = start_date
    if end_date:
        query += " AND fact_date <= :end_date"
        params['end_date'] = end_date
    
    query += " ORDER BY fact_date"
    
    with engine.connect() as conn:
        if params:
            df = pd.read_sql(text(query), conn, params=params)
        else:
            df = pd.read_sql(text(query), conn)
    
    df['fact_date'] = pd.to_datetime(df['fact_date'])
    df['workout_kcal'] = df['workout_kcal'].fillna(0)
    
    return df

def method_original_gemini(windows: pd.DataFrame) -> dict:
    """Original Gemini method with 4 features."""
    print("🔬 Method 1: Original Gemini (4 features)")
    
    y = windows['delta_fm_kg'].values
    X = np.column_stack([
        windows['days'].values,                    # Feature 1: days
        (windows['days'] * windows['mean_lbm']).values,  # Feature 2: days * LBM
        windows['workout_sum'].values,             # Feature 3: workout calories
        windows['intake_sum'].values               # Feature 4: intake calories
    ])
    
    scaler = StandardScaler(with_mean=True, with_std=True)
    Xs = scaler.fit_transform(X)
    
    huber = HuberRegressor(epsilon=1.35, max_iter=500, alpha=1e-3, fit_intercept=False)
    huber.fit(Xs, y)
    
    # Unscale coefficients
    beta_scaled = huber.coef_
    std_X = scaler.scale_
    beta = beta_scaled / std_X
    
    beta_days, beta_days_lbm, beta_workout, beta_intake = beta
    
    # Convert to interpretable parameters
    alpha = 1.0 / beta_intake
    c = 1.0 + alpha * beta_workout
    BMR0 = -alpha * beta_days
    k_lbm = -alpha * beta_days_lbm
    
    y_pred = huber.predict(Xs)
    r2 = r2_score(y, y_pred)
    mae = mean_absolute_error(y, y_pred)
    
    return {
        'method': 'Original Gemini (4 features)',
        'alpha': alpha,
        'c': c,
        'BMR0': BMR0,
        'k_lbm': k_lbm,
        'r2': r2,
        'mae': mae,
        'coefficients': beta,
        'feature_names': ['days', 'days*LBM', 'workout_sum', 'intake_sum']
    }

def method_current_implementation(windows: pd.DataFrame) -> dict:
    """Our current implementation with 3 features."""
    print("🔬 Method 2: Current Implementation (3 features)")
    
    y = windows['delta_fm_kg'].values
    X = np.column_stack([
        (windows['days'] * windows['mean_lbm']).values,  # LBM-days interaction
        windows['workout_sum'].values,                  # Total workout calories
        windows['intake_sum'].values                     # Total intake calories
    ])
    
    scaler = StandardScaler(with_mean=True, with_std=True)
    Xs = scaler.fit_transform(X)
    
    huber = HuberRegressor(epsilon=1.35, max_iter=500, alpha=1e-3, fit_intercept=False)
    huber.fit(Xs, y)
    
    # Unscale coefficients
    beta_scaled = huber.coef_
    std_X = scaler.scale_
    beta = beta_scaled / std_X
    
    beta_days_lbm, beta_workout, beta_intake = beta
    
    # Convert to interpretable parameters
    alpha = 1.0 / beta_intake
    c = 1.0 + alpha * beta_workout
    k_lbm = -alpha * beta_days_lbm
    
    # Hardcode BMR0 as in current implementation
    BMR0 = 1600
    
    y_pred = huber.predict(Xs)
    r2 = r2_score(y, y_pred)
    mae = mean_absolute_error(y, y_pred)
    
    return {
        'method': 'Current Implementation (3 features)',
        'alpha': alpha,
        'c': c,
        'BMR0': BMR0,
        'k_lbm': k_lbm,
        'r2': r2,
        'mae': mae,
        'coefficients': beta,
        'feature_names': ['days*LBM', 'workout_sum', 'intake_sum']
    }

def method_no_standardization(windows: pd.DataFrame) -> dict:
    """Original Gemini method without standardization."""
    print("🔬 Method 3: Original Gemini (no standardization)")
    
    y = windows['delta_fm_kg'].values
    X = np.column_stack([
        windows['days'].values,
        (windows['days'] * windows['mean_lbm']).values,
        windows['workout_sum'].values,
        windows['intake_sum'].values
    ])
    
    # No standardization
    huber = HuberRegressor(epsilon=1.35, max_iter=500, alpha=1e-3, fit_intercept=False)
    huber.fit(X, y)
    
    beta = huber.coef_
    beta_days, beta_days_lbm, beta_workout, beta_intake = beta
    
    # Convert to interpretable parameters
    alpha = 1.0 / beta_intake
    c = 1.0 + alpha * beta_workout
    BMR0 = -alpha * beta_days
    k_lbm = -alpha * beta_days_lbm
    
    y_pred = huber.predict(X)
    r2 = r2_score(y, y_pred)
    mae = mean_absolute_error(y, y_pred)
    
    return {
        'method': 'Original Gemini (no standardization)',
        'alpha': alpha,
        'c': c,
        'BMR0': BMR0,
        'k_lbm': k_lbm,
        'r2': r2,
        'mae': mae,
        'coefficients': beta,
        'feature_names': ['days', 'days*LBM', 'workout_sum', 'intake_sum']
    }

def analyze_feature_correlations(windows: pd.DataFrame):
    """Analyze feature correlations to understand multicollinearity."""
    print("\n📊 Feature Correlation Analysis")
    print("=" * 50)
    
    features = pd.DataFrame({
        'days': windows['days'],
        'days*LBM': windows['days'] * windows['mean_lbm'],
        'workout_sum': windows['workout_sum'],
        'intake_sum': windows['intake_sum'],
        'mean_lbm': windows['mean_lbm']
    })
    
    corr_matrix = features.corr()
    print("Correlation Matrix:")
    print(corr_matrix.round(3))
    
    # Check for high correlations
    high_corr = []
    for i in range(len(corr_matrix.columns)):
        for j in range(i+1, len(corr_matrix.columns)):
            corr_val = corr_matrix.iloc[i, j]
            if abs(corr_val) > 0.8:
                high_corr.append((corr_matrix.columns[i], corr_matrix.columns[j], corr_val))
    
    if high_corr:
        print("\n⚠️  High correlations detected:")
        for feat1, feat2, corr in high_corr:
            print(f"  {feat1} ↔ {feat2}: {corr:.3f}")
    else:
        print("\n✅ No high correlations detected")

def main():
    # Database connection
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("ERROR: DATABASE_URL environment variable not set")
        sys.exit(1)
    
    engine = create_engine(database_url)
    
    print("🔬 Parameter Estimation Method Comparison")
    print("=" * 60)
    
    # Load data
    print("Loading daily facts data...")
    df = load_daily_data(engine, "2021-01-01", "2024-12-31")
    print(f"Loaded {len(df)} daily records")
    
    # Apply robust cleaning
    print("Applying robust cleaning to BIA sensor data...")
    df['fat_mass_kg'] = robust_clean(df['fat_mass_kg'])
    df['fat_free_mass_kg'] = robust_clean(df['fat_free_mass_kg'])
    
    # Build windows
    print("Building 14-day analysis windows...")
    windows = build_windows(df, window_days=14)
    print(f"Total viable 14-day windows: {len(windows)}")
    
    if len(windows) < 10:
        print("ERROR: Insufficient windows for analysis")
        sys.exit(1)
    
    # Analyze feature correlations
    analyze_feature_correlations(windows)
    
    # Run different methods
    methods = [
        method_original_gemini,
        method_current_implementation,
        method_no_standardization
    ]
    
    results = []
    for method in methods:
        try:
            result = method(windows)
            results.append(result)
        except Exception as e:
            print(f"❌ Method failed: {e}")
            continue
    
    # Display comparison
    print("\n📊 METHOD COMPARISON")
    print("=" * 80)
    print(f"{'Method':<35} {'α (kcal/kg)':<12} {'C':<8} {'BMR₀':<8} {'k_LBM':<8} {'R²':<6} {'MAE':<6}")
    print("-" * 80)
    
    for result in results:
        print(f"{result['method']:<35} "
              f"{result['alpha']:>11,.0f} "
              f"{result['c']:>7.3f} "
              f"{result['BMR0']:>7,.0f} "
              f"{result['k_lbm']:>7.1f} "
              f"{result['r2']:>5.3f} "
              f"{result['mae']:>5.3f}")
    
    # Analyze differences
    print("\n🔍 ANALYSIS")
    print("=" * 50)
    
    if len(results) >= 2:
        orig = results[0]
        current = results[1]
        
        print(f"Alpha difference: {orig['alpha']:,.0f} vs {current['alpha']:,.0f} "
              f"(ratio: {orig['alpha']/current['alpha']:.2f})")
        print(f"C difference: {orig['c']:.3f} vs {current['c']:.3f} "
              f"(diff: {orig['c']-current['c']:.3f})")
        print(f"BMR0 difference: {orig['BMR0']:,.0f} vs {current['BMR0']:,.0f} "
              f"(diff: {orig['BMR0']-current['BMR0']:,.0f})")
        print(f"k_LBM difference: {orig['k_lbm']:.1f} vs {current['k_lbm']:.1f} "
              f"(diff: {orig['k_lbm']-current['k_lbm']:.1f})")
        
        print(f"\nModel fit comparison:")
        print(f"  R²: {orig['r2']:.3f} vs {current['r2']:.3f}")
        print(f"  MAE: {orig['mae']:.3f} vs {current['mae']:.3f}")
    
    # Check for constant features
    print(f"\n🔍 Feature Analysis")
    print("=" * 30)
    print(f"Days range: {windows['days'].min()} - {windows['days'].max()}")
    print(f"Days std: {windows['days'].std():.3f}")
    print(f"Days unique values: {windows['days'].nunique()}")
    
    if windows['days'].nunique() == 1:
        print("⚠️  WARNING: 'days' feature is constant - this causes identifiability issues!")
    
    print(f"\nAnalysis complete: {len(windows)} windows from {len(df)} daily records")

if __name__ == '__main__':
    main()
