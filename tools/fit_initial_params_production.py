#!/usr/bin/env python3
"""
Fit initial parameters using production windows data.

Replicates P1 parameter fitting methodology using production train/test windows.
Fits α (energy density), c (compensation), BMR parameters using Huber loss optimization.
"""

import os
import numpy as np
import pandas as pd
from pathlib import Path
from math import isfinite
from sqlalchemy import create_engine, text
import argparse
from datetime import datetime

# Database connection
DB = os.environ.get("DATABASE_URL")
assert DB, "Set DATABASE_URL in your .env"

eng = create_engine(DB)

parser = argparse.ArgumentParser(description="Fit initial parameters using production windows")
parser.add_argument("--include-all-days", action="store_true", help="Use all curated windows (7/14/21/28); by default, only is_7d=true")
parser.add_argument("--use-test-data", action="store_true", help="Use test windows instead of train windows")
# Bounds for BMR (M)
parser.add_argument("--M-min", type=int, default=1400, help="Minimum BMR (kcal/day)")
parser.add_argument("--M-max", type=int, default=2200, help="Maximum BMR (kcal/day)")
parser.add_argument("--M-step", type=int, default=50, help="BMR grid step size")
# Bounds for compensation factor (C)
parser.add_argument("--C-min", type=float, default=0.00, help="Minimum compensation factor")
parser.add_argument("--C-max", type=float, default=0.50, help="Maximum compensation factor")
parser.add_argument("--C-step", type=float, default=0.05, help="Compensation factor grid step size")
# Bounds for energy density (alpha)
parser.add_argument("--A-min", type=int, default=7000, help="Minimum energy density (kcal/kg)")
parser.add_argument("--A-max", type=int, default=9500, help="Maximum energy density (kcal/kg)")
parser.add_argument("--A-step", type=int, default=250, help="Energy density grid step size")
# Huber loss parameters
parser.add_argument("--huber-delta", type=float, default=0.5, help="Huber loss delta parameter")
# Output options
parser.add_argument("--save-params", action="store_true", help="Save fitted parameters to model_params_timevarying table")
parser.add_argument("--params-version", type=str, help="Version identifier for saved parameters (default: auto-generated)")
parser.add_argument("--effective-date", type=str, help="Effective date for parameters (default: today)")
args = parser.parse_args()

def load_windows_data():
    """Load window data from production views."""
    if args.use_test_data:
        table_name = "prod_test_windows"
        print("Using test windows data")
    else:
        table_name = "prod_train_windows"
        print("Using train windows data")
    
    base_sql = f"""
        SELECT end_date, days, intake_kcal_sum, workout_kcal_sum, delta_fm_kg 
        FROM {table_name}
    """
    
    if not args.include_all_days:
        q = base_sql + " WHERE is_7d = true ORDER BY end_date;"
    else:
        q = base_sql + " ORDER BY end_date;"
    
    df = pd.read_sql(q, eng, parse_dates=["end_date"])
    print(f"Loaded {len(df)} windows from {table_name} (include_all_days={args.include_all_days})")
    
    return df

def huber_loss(residuals, delta):
    """Huber loss function for robust parameter fitting."""
    abs_res = np.abs(residuals)
    return np.where(abs_res <= delta, 0.5 * abs_res**2, delta * (abs_res - 0.5 * delta))

def objective_function(M, C, alpha, df):
    """Objective function for parameter optimization."""
    # Model: Δfm = (intake - (1-C)*workout - M*days) / alpha
    predicted = (df.intake_kcal_sum - (1 - C) * df.workout_kcal_sum - M * df.days) / alpha
    residuals = df.delta_fm_kg.values - predicted
    return np.nanmean(huber_loss(residuals, delta=args.huber_delta))

def grid_search(df):
    """Two-stage grid search: coarse then fine."""
    print(f"🔍 Coarse grid search:")
    print(f"   BMR: {args.M_min} to {args.M_max} step {args.M_step}")
    print(f"   C: {args.C_min} to {args.C_max} step {args.C_step}")
    print(f"   α: {args.A_min} to {args.A_max} step {args.A_step}")
    
    # Coarse grid search
    Ms = np.arange(args.M_min, args.M_max + 1, args.M_step)
    Cs = np.arange(args.C_min, args.C_max + 1e-12, args.C_step)
    As = np.arange(args.A_min, args.A_max + 1, args.A_step)
    
    best_loss = 1e9
    best_params = None
    
    for M in Ms:
        for C in Cs:
            for A in As:
                loss = objective_function(M, C, A, df)
                if isfinite(loss) and loss < best_loss:
                    best_loss = loss
                    best_params = (M, C, A)
    
    if best_params is None:
        raise ValueError("No valid parameters found in coarse grid search")
    
    M0, C0, A0 = best_params
    print(f"   Best coarse: M={M0:.0f}, C={C0:.3f}, α={A0:.0f} (loss={best_loss:.4f})")
    
    # Fine grid search around best coarse result
    print(f"🔍 Fine grid search around best coarse result:")
    Ms_fine = np.arange(max(args.M_min, M0 - 100), min(args.M_max, M0 + 100) + 1, 10)
    Cs_fine = np.arange(max(args.C_min, C0 - 0.08), min(args.C_max, C0 + 0.08) + 1e-12, 0.01)
    As_fine = np.arange(max(args.A_min, A0 - 300), min(args.A_max, A0 + 300) + 1, 50)
    
    print(f"   BMR: {Ms_fine[0]:.0f} to {Ms_fine[-1]:.0f} step 10")
    print(f"   C: {Cs_fine[0]:.3f} to {Cs_fine[-1]:.3f} step 0.01")
    print(f"   α: {As_fine[0]:.0f} to {As_fine[-1]:.0f} step 50")
    
    best_loss = 1e9
    best_params = None
    
    for M in Ms_fine:
        for C in Cs_fine:
            for A in As_fine:
                loss = objective_function(M, C, A, df)
                if isfinite(loss) and loss < best_loss:
                    best_loss = loss
                    best_params = (M, C, A)
    
    return best_loss, best_params

def calculate_residuals(df, M, C, alpha):
    """Calculate residuals for the fitted parameters."""
    predicted = (df.intake_kcal_sum - (1 - C) * df.workout_kcal_sum - M * df.days) / alpha
    residuals = df.delta_fm_kg.values - predicted
    return residuals

def save_parameters(M, C, alpha, loss, df):
    """Save fitted parameters to model_params_timevarying table."""
    if not args.save_params:
        return
    
    # Generate version and effective date
    if args.params_version:
        version = args.params_version
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        version = f"prod_fit_{timestamp}"
    
    if args.effective_date:
        effective_date = args.effective_date
    else:
        effective_date = datetime.now().strftime("%Y-%m-%d")
    
    # Calculate additional metrics
    residuals = calculate_residuals(df, M, C, alpha)
    mae = np.mean(np.abs(residuals))
    rmse = np.sqrt(np.mean(residuals**2))
    bias = np.mean(residuals)
    
    # Insert parameters
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
            'fit_initial_params_production',
            NOW()
        )
    """)
    
    notes = f"Production fit: {len(df)} windows, Huber loss={loss:.4f}, MAE={mae:.3f}kg, RMSE={rmse:.3f}kg, bias={bias:.3f}kg"
    
    with eng.connect() as conn:
        conn.execute(insert_sql, {
            'version': version,
            'effective_date': effective_date,
            'c': float(C),
            'alpha_fm': 0.25,  # Default EMA smoothing
            'alpha_lbm': 0.10,  # Default EMA smoothing
            'bmr0': float(M),
            'k_lbm': 20.0,  # Default LBM coefficient
            'alpha': float(alpha),
            'notes': notes
        })
        conn.commit()
    
    print(f"✅ Parameters saved as version '{version}' with effective date {effective_date}")

def validate_parameters(df, M, C, alpha):
    """Validate fitted parameters with summary statistics."""
    residuals = calculate_residuals(df, M, C, alpha)
    
    print(f"\n📊 Parameter Validation:")
    print(f"   BMR (M): {M:.0f} kcal/day")
    print(f"   Compensation (C): {C:.3f}")
    print(f"   Energy Density (α): {alpha:.0f} kcal/kg")
    
    print(f"\n📈 Fit Statistics:")
    print(f"   Huber Loss: {np.nanmean(huber_loss(residuals, args.huber_delta)):.4f}")
    print(f"   MAE: {np.mean(np.abs(residuals)):.3f} kg")
    print(f"   RMSE: {np.sqrt(np.mean(residuals**2)):.3f} kg")
    print(f"   Bias: {np.mean(residuals):.3f} kg")
    print(f"   Std Dev: {np.std(residuals):.3f} kg")
    
    print(f"\n📋 Residual Distribution:")
    print(f"   Min: {np.min(residuals):.3f} kg")
    print(f"   25th percentile: {np.nanpercentile(residuals, 25):.3f} kg")
    print(f"   50th percentile: {np.nanpercentile(residuals, 50):.3f} kg")
    print(f"   75th percentile: {np.nanpercentile(residuals, 75):.3f} kg")
    print(f"   Max: {np.max(residuals):.3f} kg")
    
    # Check for outliers
    outlier_threshold = 2.0  # kg
    outliers = np.abs(residuals) > outlier_threshold
    outlier_count = np.sum(outliers)
    outlier_pct = 100 * outlier_count / len(residuals)
    
    print(f"\n🚨 Outlier Analysis (|residual| > {outlier_threshold} kg):")
    print(f"   Count: {outlier_count}/{len(residuals)} ({outlier_pct:.1f}%)")
    
    if outlier_count > 0:
        outlier_indices = np.where(outliers)[0]
        print(f"   Outlier windows:")
        for idx in outlier_indices[:5]:  # Show first 5 outliers
            row = df.iloc[idx]
            print(f"     {row.end_date}: ΔFM={row.delta_fm_kg:.3f}kg, predicted={row.delta_fm_kg - residuals[idx]:.3f}kg, residual={residuals[idx]:.3f}kg")

def main():
    """Main function."""
    print("🚀 Fitting Initial Parameters from Production Windows")
    print("="*60)
    
    try:
        # Load data
        df = load_windows_data()
        
        if len(df) == 0:
            print("❌ No windows data found")
            return 1
        
        # Fit parameters
        print(f"\n🔧 Fitting parameters using {len(df)} windows...")
        loss, (M, C, alpha) = grid_search(df)
        
        # Display results
        print(f"\n✅ Best Parameters Found:")
        print(f"   BMR (M): {M:.0f} kcal/day")
        print(f"   Compensation (C): {C:.3f}")
        print(f"   Energy Density (α): {alpha:.0f} kcal/kg")
        print(f"   Huber Loss: {loss:.4f}")
        
        # Validate parameters
        validate_parameters(df, M, C, alpha)
        
        # Save parameters if requested
        if args.save_params:
            save_parameters(M, C, alpha, loss, df)
        else:
            print(f"\n💡 Use --save-params to save these parameters to the database")
        
        print(f"\n🎯 Parameter Fitting Complete!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
