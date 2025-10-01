#!/usr/bin/env python3
"""
P2 Parameter Estimation - Weekly Energy Balance Model

Fits parameters (α, β₀, β₁, β₂, BMR) to weekly fat mass changes using:
ΔFM_week = (1/α) · [Σ(intake) - Σ(TEF) - 7·BMR - β₀ - β₁·Σ(workout) - β₂·(Σ(IF)/7)]

Models:
- simple: 3 params (α, C, BMR) where C = β₁, β₀=β₂=0
- complex: 5 params (α, β₀, β₁, β₂, BMR)
"""

import psycopg2
import numpy as np
from scipy.optimize import minimize
from datetime import datetime, timedelta
import pandas as pd
import os


def load_block_data(conn, start_date: str, end_date: str, block_days: int):
    """
    Load daily data and aggregate into blocks of specified days.
    
    Returns DataFrame with columns:
    - period_start, period_end
    - intake_sum, tef_sum, workout_sum, if_sum
    - delta_fm (from filtered fat mass)
    """
    
    query = f"""
    WITH daily AS (
        SELECT 
            df.fact_date,
            df.intake_kcal,
            df.tef_kcal,
            df.workout_kcal,
            df.intensity_factor,
            dff.fat_mass_kg_filtered,
            df.fat_free_mass_kg,  -- ADD THIS
            -- Create block groups based on days since epoch
            FLOOR(EXTRACT(EPOCH FROM df.fact_date) / (86400 * {block_days})) as block_id
        FROM daily_facts df
        LEFT JOIN daily_facts_filtered dff ON df.fact_date = dff.fact_date
        WHERE df.fact_date BETWEEN %s AND %s
            AND df.intake_kcal IS NOT NULL
            AND dff.fat_mass_kg_filtered IS NOT NULL
        ORDER BY df.fact_date
    ),
    blocks AS (
        SELECT 
            MIN(daily.fact_date)::date as period_start,
            MAX(daily.fact_date)::date as period_end,
            SUM(daily.intake_kcal) as intake_sum,
            SUM(COALESCE(daily.tef_kcal, 0)) as tef_sum,
            SUM(COALESCE(daily.workout_kcal, 0)) as workout_sum,
            SUM(COALESCE(daily.intensity_factor, 0)) as if_sum,
            COUNT(*) as days_present,
            AVG(daily.fat_free_mass_kg) as lbm_avg,  -- Average LBM for the block
            -- CORRECT: Get first and last day's fat mass, not min/max
            (ARRAY_AGG(daily.fat_mass_kg_filtered ORDER BY daily.fact_date))[1] as fm_start,
            (ARRAY_AGG(daily.fat_mass_kg_filtered ORDER BY daily.fact_date DESC))[1] as fm_end
        FROM daily
        GROUP BY daily.block_id
        HAVING COUNT(*) = {block_days}  -- Variable block size
    )
    SELECT 
        period_start,
        period_end,
        intake_sum,
        tef_sum,
        workout_sum,
        if_sum,
        lbm_avg,
        fm_end - fm_start as delta_fm
    FROM blocks
    ORDER BY period_start
    """
    
    return pd.read_sql(query, conn, params=[start_date, end_date])


def residual_function(params, model: str, alpha_fixed, df, block_days: int, return_predictions=False):
    """
    Calculate residuals for optimization.
    
    params order:
    - If alpha_fixed is None: [α, C, BMR₀, k_LBM]
    - If alpha_fixed provided: [C, BMR₀, k_LBM]
    """
    
    if alpha_fixed is None:
        alpha, C, bmr0, k_lbm = params
    else:
        alpha = alpha_fixed
        C, bmr0, k_lbm = params
    
    # Calculate predicted ΔFM for each block
    # CORRECT ENERGY BALANCE EQUATION:
    # ΔFM = (1/α) · [Σ(intake) - Σ(TEF) - block_days·BMR - Σ(workout_kcal·(1-C))]
    
    bmr_daily = bmr0 + k_lbm * df['lbm_avg']
    effective_workout = df['workout_sum'] * (1 - C)  # C is compensation factor
    
    net_energy = (
        df['intake_sum'] 
        - df['tef_sum'] 
        - block_days * bmr_daily
        - effective_workout
    )
    
    predicted_delta_fm = net_energy / alpha
    observed_delta_fm = df['delta_fm']
    
    residuals = predicted_delta_fm - observed_delta_fm
    
    if return_predictions:
        return predicted_delta_fm
    
    return residuals


def estimate_parameters(
    start_date: str,
    end_date: str,
    block_days: int = 7,
    model: str = 'simple',
    alpha_fixed: float = None
):
    """
    Estimate P2 parameters from energy balance data aggregated into blocks.
    
    Args:
        start_date: ISO format (YYYY-MM-DD)
        end_date: ISO format (YYYY-MM-DD)
        block_days: Number of days per aggregation block (7, 14, 28, etc.)
        model: 'simple' (3-param) or 'complex' (5-param)
        alpha_fixed: If provided, α is fixed at this value
    
    Returns:
        dict with keys: params, r_squared, rmse, predictions_df
    """
    
    # Connect to database
    conn = psycopg2.connect(os.getenv('DATABASE_URL'))
    
    try:
        # Load block data
        df = load_block_data(conn, start_date, end_date, block_days)
        
        print(f"\nLoaded {len(df)} complete {block_days}-day blocks from {start_date} to {end_date}")
        print(f"Date range: {df['period_start'].min()} to {df['period_end'].max()}")
        
        # Set up optimization - only simple model with 4 parameters
        if alpha_fixed is None:
            # Fit: α, C, BMR₀, k_LBM
            x0 = [9500, 0.5, 370, 21.6]  # Initial guess
            bounds = [(7700, 11000), (0, 1), (200, 600), (18, 25)]  # Wider α and BMR₀, k_LBM
            param_names = ['alpha', 'C', 'bmr0', 'k_lbm']
        else:
            # Fit: C, BMR₀, k_LBM
            x0 = [0.5, 370, 21.6]
            bounds = [(0, 1), (200, 600), (18, 25)]  # Wider BMR₀, k_LBM
            param_names = ['C', 'bmr0', 'k_lbm']
        
        # Minimize sum of squared residuals
        def objective(params):
            residuals = residual_function(params, model, alpha_fixed, df, block_days)
            return np.sum(residuals**2)
        
        result = minimize(
            objective,
            x0=x0,
            method='L-BFGS-B',
            bounds=bounds
        )
        
        if not result.success:
            print(f"WARNING: Optimization did not converge: {result.message}")
        
        # Extract fitted parameters
        fitted_params = {}
        for name, value in zip(param_names, result.x):
            fitted_params[name] = value
        
        if alpha_fixed is not None:
            fitted_params['alpha'] = alpha_fixed
        
        # Calculate diagnostics
        predictions = residual_function(result.x, model, alpha_fixed, df, block_days, return_predictions=True)
        residuals = predictions - df['delta_fm'].values
        
        # R²
        ss_res = np.sum(residuals**2)
        ss_tot = np.sum((df['delta_fm'] - df['delta_fm'].mean())**2)
        r_squared = 1 - (ss_res / ss_tot)
        
        # RMSE
        rmse = np.sqrt(np.mean(residuals**2))
        
        # Create predictions dataframe
        predictions_df = df.copy()
        predictions_df['predicted_delta_fm'] = predictions
        predictions_df['residual'] = residuals
        
        print(f"\n{'='*60}")
        print(f"MODEL: {model.upper()}")
        print(f"{'='*60}")
        print(f"\nFitted Parameters:")
        print(f"  α (kcal/kg):     {fitted_params['alpha']:.1f}")
        print(f"  C (compensation): {fitted_params['C']:.3f}")
        print(f"  BMR₀ (kcal/day): {fitted_params['bmr0']:.1f}")
        print(f"  k_LBM (kcal/kg): {fitted_params['k_lbm']:.1f}")
        
        # Calculate effective BMR for average LBM
        avg_lbm = df['lbm_avg'].mean()
        effective_bmr = fitted_params['bmr0'] + fitted_params['k_lbm'] * avg_lbm
        print(f"  Effective BMR:   {effective_bmr:.1f} kcal/day (for {avg_lbm:.1f} kg LBM)")
        
        print(f"\nDiagnostics:")
        print(f"  R²:              {r_squared:.4f}")
        print(f"  RMSE (kg):       {rmse:.4f}")
        print(f"  Mean |residual|: {np.abs(residuals).mean():.4f} kg")
        
        # Show sample predictions
        print(f"\nSample Predictions (first 5 blocks):")
        print(predictions_df[['period_start', 'delta_fm', 'predicted_delta_fm', 'residual']].head())
        
        return {
            'params': fitted_params,
            'r_squared': r_squared,
            'rmse': rmse,
            'predictions': predictions_df,
            'n_blocks': len(df),
            'block_days': block_days
        }
        
    finally:
        conn.close()


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Estimate P2 parameters from weekly energy balance')
    parser.add_argument('--start', default='2021-01-04', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', default='2024-10-09', help='End date (YYYY-MM-DD)')
    parser.add_argument('--model', default='simple', choices=['simple', 'complex'], 
                        help='Model form: simple (3-param) or complex (5-param)')
    parser.add_argument('--alpha', type=float, default=None, 
                        help='Fix alpha at this value (kcal/kg)')
    parser.add_argument('--block-days', type=int, default=7,
                        help='Number of days per aggregation block (7, 14, etc.)')
    args = parser.parse_args()
    
    results = estimate_parameters(
        start_date=args.start,
        end_date=args.end,
        block_days=args.block_days,
        model=args.model,
        alpha_fixed=args.alpha
    )
    
    # Optionally save results
    results['predictions'].to_csv(f'p2_predictions_{args.model}_{args.start}_{args.end}.csv', index=False)
    print(f"\nPredictions saved to p2_predictions_{args.model}_{args.start}_{args.end}.csv")
