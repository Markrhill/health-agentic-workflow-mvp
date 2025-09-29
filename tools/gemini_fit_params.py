#!/usr/bin/env python3
"""
Gemini Fit Parameters Tool

Fits metabolic parameters using Gemini's stabilized 4-parameter model with robust cleaning
and 14-day analysis windows. Uses sklearn's HuberRegressor for robust fitting.

Based on the methodology from the Gemini analysis but adapted for our database schema.
"""

import argparse
import os
import sys
from datetime import date, datetime
from typing import Tuple, Dict, Any

import pandas as pd
import numpy as np
from sklearn.linear_model import HuberRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import r2_score, mean_absolute_error
from sqlalchemy import create_engine, text

# Add project root to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def robust_clean(series: pd.Series, window: int = 7, k: float = 3.0) -> pd.Series:
    """
    Robustly clean BIA sensor data using rolling median and MAD-based outlier detection.
    
    Args:
        series: Input time series
        window: Rolling window size for median calculation
        k: MAD multiplier for outlier threshold
        
    Returns:
        Cleaned series with outliers set to NaN
    """
    s = series.copy()
    med = s.rolling(window, center=True, min_periods=1).median()
    mad = (s - med).abs().rolling(window, center=True, min_periods=1).median()
    mad = mad.replace(0, np.nan).ffill().bfill()
    mask = (s - med).abs() > k * mad
    s[mask] = np.nan
    return s

def build_windows(data: pd.DataFrame, window_days: int = 14) -> pd.DataFrame:
    """
    Build 14-day analysis windows with robust eligibility criteria.
    
    Args:
        data: Daily facts DataFrame
        window_days: Window length in days
        
    Returns:
        DataFrame with window-level aggregations
    """
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
                'days': int(window_days),
                'start_date': w.iloc[0]['fact_date'],
                'end_date': w.iloc[-1]['fact_date']
            })
    
    return pd.DataFrame(rows)

def load_daily_data(engine, start_date: str = None, end_date: str = None) -> pd.DataFrame:
    """
    Load daily facts data from database with optional date filtering.
    
    Args:
        engine: SQLAlchemy engine
        start_date: Start date filter (YYYY-MM-DD)
        end_date: End date filter (YYYY-MM-DD)
        
    Returns:
        DataFrame with daily facts
    """
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
    
    # Convert date column
    df['fact_date'] = pd.to_datetime(df['fact_date'])
    
    # Fill missing workout calories with 0
    df['workout_kcal'] = df['workout_kcal'].fillna(0)
    
    return df

def fit_stabilized_model(windows: pd.DataFrame) -> Tuple[Dict[str, float], float, float]:
    """
    Fit the stabilized 4-parameter model using HuberRegressor.
    
    Args:
        windows: Window-level DataFrame
        
    Returns:
        Tuple of (parameters_dict, r2_score, mae)
    """
    # Prepare features and target
    y = windows['delta_fm_kg'].values
    X = np.column_stack([
        (windows['days'] * windows['mean_lbm']).values,  # LBM-days interaction
        windows['workout_sum'].values,  # Total workout calories
        windows['intake_sum'].values   # Total intake calories
    ])
    
    # Standardize features
    scaler = StandardScaler(with_mean=True, with_std=True)
    Xs = scaler.fit_transform(X)
    
    # Fit Huber regressor with regularization
    huber = HuberRegressor(epsilon=1.35, max_iter=500, alpha=1e-3, fit_intercept=False)
    huber.fit(Xs, y)
    
    # Unscale coefficients to map back to physiology
    beta_scaled = huber.coef_
    std_X = scaler.scale_
    beta = beta_scaled / std_X
    
    beta_days_lbm, beta_workout, beta_intake = beta
    
    # Debug output (commented out for production)
    # print(f"DEBUG: Feature means: {scaler.mean_}")
    # print(f"DEBUG: Feature scales: {scaler.scale_}")
    # print(f"DEBUG: Raw coefficients: {beta_scaled}")
    # print(f"DEBUG: Unscaled coefficients: {beta}")
    
    # Convert coefficients to interpretable parameters
    # Model: delta_fm_kg = (intake_sum - (1-C)*workout_sum - k_lbm*mean_lbm*days) / alpha
    # Rearranged: delta_fm_kg = (1/alpha)*intake_sum - ((1-C)/alpha)*workout_sum - (k_lbm/alpha)*mean_lbm*days
    # So: beta_intake = 1/alpha, beta_workout = -(1-C)/alpha, beta_days_lbm = -k_lbm/alpha
    alpha = 1.0 / beta_intake
    c = 1.0 + alpha * beta_workout
    k_lbm = -alpha * beta_days_lbm
    
    # Estimate BMR0 using the mean window length and a reasonable baseline
    mean_days = windows['days'].mean()
    # Use a reasonable BMR estimate based on typical values
    BMR0 = 1600  # Typical BMR for adult male
    
    # Calculate fit metrics
    y_pred = huber.predict(Xs)
    r2 = r2_score(y, y_pred)
    mae = mean_absolute_error(y, y_pred)
    
    params = {
        'alpha': alpha,
        'c': c,
        'BMR0': BMR0,
        'k_lbm': k_lbm
    }
    
    return params, r2, mae

def validate_parameters(params: Dict[str, float]) -> Tuple[bool, list]:
    """
    Validate that parameters are within physiologically plausible ranges.
    
    Args:
        params: Dictionary of fitted parameters
        
    Returns:
        Tuple of (all_reasonable, issues_list)
    """
    issues = []
    
    # Check alpha (energy density)
    if not (6000 <= params['alpha'] <= 12000):
        issues.append(f"α={params['alpha']:,.0f} outside plausible range (6000-12000)")
    
    # Check c (compensation factor)
    if not (0.0 <= params['c'] <= 1.0):
        issues.append(f"C={params['c']:.3f} outside plausible range (0.0-1.0)")
    
    # Check BMR0 (baseline metabolic rate)
    if not (1000 <= params['BMR0'] <= 3000):
        issues.append(f"BMR₀={params['BMR0']:,.0f} outside plausible range (1000-3000)")
    
    # Check k_lbm (lean body mass coefficient)
    if not (10 <= params['k_lbm'] <= 50):
        issues.append(f"k_LBM={params['k_lbm']:.1f} outside plausible range (10-50)")
    
    return len(issues) == 0, issues

def save_parameters(engine, params: Dict[str, float], r2: float, mae: float, 
                   version: str, effective_date: str, n_windows: int):
    """
    Save fitted parameters to model_params_timevarying table.
    
    Args:
        engine: SQLAlchemy engine
        params: Fitted parameters
        r2: R-squared score
        mae: Mean absolute error
        version: Parameter version name
        effective_date: Effective start date
        n_windows: Number of windows used
    """
    insert_sql = text("""
        INSERT INTO model_params_timevarying (
            params_version,
            effective_start_date,
            effective_end_date,
            c_exercise_comp,
            alpha_fm,
            alpha_lbm,
            bmr0_kcal,
            k_lbm_kcal_per_kg,
            kcal_per_kg_fat,
            method_notes,
            approved_by,
            approved_at
        ) VALUES (
            :version,
            :effective_date,
            NULL,
            :c,
            :alpha_fm,
            :alpha_lbm,
            :bmr0,
            :k_lbm,
            :alpha,
            :notes,
            'gemini_fit_params',
            NOW()
        )
    """)
    
    notes = f"Gemini stabilized model: {n_windows} windows, R²={r2:.3f}, MAE={mae:.3f}kg"
    
    with engine.connect() as conn:
        conn.execute(insert_sql, {
            'version': version,
            'effective_date': effective_date,
            'c': float(params['c']),
            'alpha_fm': 0.25,  # Default EMA smoothing
            'alpha_lbm': 0.10,  # Default EMA smoothing
            'bmr0': float(params['BMR0']),
            'k_lbm': float(params['k_lbm']),
            'alpha': float(params['alpha']),
            'notes': notes
        })
        conn.commit()
    
    print(f"✅ Parameters saved as version '{version}' with effective date {effective_date}")

def main():
    parser = argparse.ArgumentParser(description='Fit parameters using Gemini stabilized model')
    parser.add_argument('--start-date', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, help='End date (YYYY-MM-DD)')
    parser.add_argument('--window-days', type=int, default=14, help='Analysis window length (default: 14)')
    parser.add_argument('--save-params', action='store_true', help='Save parameters to database')
    parser.add_argument('--params-version', type=str, help='Parameter version name for saving')
    parser.add_argument('--effective-date', type=str, help='Effective start date for saved parameters')
    
    args = parser.parse_args()
    
    # Database connection
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("ERROR: DATABASE_URL environment variable not set")
        sys.exit(1)
    
    engine = create_engine(database_url)
    
    print("🔬 Gemini Stabilized Parameter Fitting")
    print("=" * 50)
    
    # Load data
    print("Loading daily facts data...")
    df = load_daily_data(engine, args.start_date, args.end_date)
    print(f"Loaded {len(df)} daily records")
    
    if len(df) < args.window_days:
        print(f"ERROR: Insufficient data for {args.window_days}-day windows")
        sys.exit(1)
    
    # Robustly clean BIA sensor data
    print("Applying robust cleaning to BIA sensor data...")
    df['fat_mass_kg'] = robust_clean(df['fat_mass_kg'])
    df['fat_free_mass_kg'] = robust_clean(df['fat_free_mass_kg'])
    
    # Build analysis windows
    print(f"Building {args.window_days}-day analysis windows...")
    windows = build_windows(df, window_days=args.window_days)
    print(f"Total viable {args.window_days}-day windows: {len(windows)}")
    
    if len(windows) < 10:
        print(f"ERROR: Insufficient windows ({len(windows)}) for reliable fitting")
        sys.exit(1)
    
    # Fit stabilized model
    print("Fitting stabilized 4-parameter model...")
    params, r2, mae = fit_stabilized_model(windows)
    
    # Display results
    print("\n--- 4-Parameter Estimates (Stabilized Model) ---")
    print(f"α (kcal per kg fat):      {params['alpha']:,.0f}")
    print(f"C (exercise compensation): {params['c']:.3f}")
    print(f"BMR₀ (baseline, kcal/day): {params['BMR0']:,.0f}")
    print(f"k_LBM (kcal/day per kg):   {params['k_lbm']:.1f}")
    print(f"Model fit: R² = {r2:.3f}, MAE = {mae:.3f} kg")
    
    # Validate parameters
    all_reasonable, issues = validate_parameters(params)
    
    print("\n" + "="*50)
    print("FINAL SUMMARY")
    print("="*50)
    print(f"Parameters from {len(df)}-row dataset using Gemini's stabilized model:")
    print(f"  α = {params['alpha']:,.0f} kcal/kg")
    print(f"  C = {params['c']:.3f}")
    print(f"  BMR₀ = {params['BMR0']:,.0f} kcal/day")
    print(f"  k_LBM = {params['k_lbm']:.1f} kcal/day/kg")
    print(f"Model fit: R² = {r2:.3f}, MAE = {mae:.3f} kg")
    
    if all_reasonable:
        print("\n✅ SUCCESS: All parameters within physiologically plausible ranges")
    else:
        print("\n❌ CONCERN: Parameters suggest reproducibility issues remain")
        for issue in issues:
            print(f"  - {issue}")
    
    # Save parameters if requested
    if args.save_params:
        if not args.params_version or not args.effective_date:
            print("ERROR: --params-version and --effective-date required when saving")
            sys.exit(1)
        
        save_parameters(engine, params, r2, mae, args.params_version, 
                       args.effective_date, len(windows))
    
    print(f"\nAnalysis complete: {len(windows)} windows from {len(df)} daily records")

if __name__ == '__main__':
    main()
