#!/usr/bin/env python3
"""
Bayesian parameter updater for monthly alpha & c parameter updates.

This module provides pure, testable functions for Bayesian updating of metabolic
parameters based on weekly fat mass change observations.
"""

import argparse
import os
import sys
import textwrap
from datetime import datetime, date, timedelta
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text

# Set random seed for reproducibility
np.random.seed(42)

@dataclass
class Priors:
    version: str
    bmr0: float
    k_lbm: float
    c0: float
    alpha0: float
    alpha_fm: float
    alpha_lbm: float

def emit_proposal(engine, asof: date, priors: Priors,
                  alpha_hat: float, c_hat: float, bias_kg: float, mae: float,
                  alpha_new: float, c_new: float, cap: float,
                  weeks_df: pd.DataFrame,
                  capped_reason: str) -> str:
    """Insert one PENDING proposal row and return the proposal_id."""
    # alpha implied stats (from current params_version) for reviewer context
    implied = weeks_df.loc[weeks_df['alpha_implied_kcal_per_kg'].notna(), 'alpha_implied_kcal_per_kg']
    stats = (implied.min() if not implied.empty else None,
             implied.median() if not implied.empty else None,
             implied.max() if not implied.empty else None)
    n_weeks = int(len(weeks_df))

    sql = text("""
      insert into proposed_model_param_updates (
        asof_date, base_params_version,
        prior_c_exercise_comp, prior_kcal_per_kg_fat, prior_bmr0_kcal, prior_k_lbm_kcal_per_kg,
        fit_c_exercise_comp, fit_kcal_per_kg_fat, fit_bias_kg_per_week, fit_mae_kg_per_week,
        cap_fraction, capped_c_exercise_comp, capped_kcal_per_kg_fat, capped_reason,
        n_weeks_used, alpha_implied_min, alpha_implied_median, alpha_implied_max
      ) values (
        :asof_date, :base_params_version,
        :prior_c, :prior_alpha, :prior_bmr0, :prior_k,
        :fit_c, :fit_alpha, :fit_bias, :fit_mae,
        :cap_fraction, :capped_c, :capped_alpha, :capped_reason,
        :n_weeks, :ai_min, :ai_med, :ai_max
      ) returning proposal_id
    """)
    with engine.begin() as conn:
        proposal_id = conn.execute(sql, dict(
            asof_date=asof,
            base_params_version=priors.version,
            prior_c=priors.c0, prior_alpha=priors.alpha0,
            prior_bmr0=priors.bmr0, prior_k=priors.k_lbm,
            fit_c=c_hat, fit_alpha=alpha_hat, fit_bias=bias_kg, fit_mae=mae,
            cap_fraction=cap, capped_c=c_new, capped_alpha=alpha_new, capped_reason=capped_reason,
            n_weeks=n_weeks,
            ai_min=stats[0], ai_med=stats[1], ai_max=stats[2]
        )).scalar_one()
    return str(proposal_id)

def print_approval_sql(proposal_id: str):
    print("\n-- APPROVE THIS PROPOSAL ------------------------------------")
    print(textwrap.dedent(f"""
      -- 1) Mark as APPROVED (optional if you prefer to mark after insert)
      update proposed_model_param_updates
      set status='APPROVED', reviewer=coalesce(current_user, 'human'),
          review_notes='approved', reviewed_at=now()
      where proposal_id = '{proposal_id}';

      -- 2) Insert a new version row into model_params_timevarying
      insert into model_params_timevarying
      (params_version, effective_start_date, effective_end_date,
       c_exercise_comp, alpha_fm, alpha_lbm, bmr0_kcal, k_lbm_kcal_per_kg, kcal_per_kg_fat,
       method_notes, approved_by, approved_at)
      select
        to_char(asof_date, '"v"YYYY_MM_DD'),
        asof_date, null,
        capped_c_exercise_comp,
        0.25, 0.10,
        prior_bmr0_kcal, prior_k_lbm_kcal_per_kg,
        capped_kcal_per_kg_fat,
        format('Bayes-lite monthly from %s; fit_bias=%%.3f kg/wk; fit_mae=%%.3f kg/wk; cap=%%.1f%%; reason=%%s',
               base_params_version)::text,
        coalesce(current_user, 'human'),
        now()
      from proposed_model_param_updates
      where proposal_id = '{proposal_id}';

      -- 3) (Optional) Log to audit_hil
      insert into audit_hil (snapshot_week_start, action, actor, rationale, previous_params_version, new_params_version, created_at)
      values (
        date_trunc('week', (select asof_date from proposed_model_param_updates where proposal_id='{proposal_id}'))::date,
        'ChangeParams',
        coalesce(current_user, 'human'),
        'Approved monthly update',
        (select base_params_version from proposed_model_param_updates where proposal_id='{proposal_id}'),
        (select to_char(asof_date, '"v"YYYY_MM_DD') from proposed_model_param_updates where proposal_id='{proposal_id}'),
        now()
      );
    """))

def print_reject_sql(proposal_id: str):
    print("\n-- REJECT THIS PROPOSAL -------------------------------------")
    print(textwrap.dedent(f"""
      update proposed_model_param_updates
      set status='REJECTED', reviewer=coalesce(current_user, 'human'),
          review_notes='not applied; bias/coverage/corruption', reviewed_at=now()
      where proposal_id = '{proposal_id}';
    """))

def load_daily(engine, start: str, end: str) -> pd.DataFrame:
    """
    Load daily data joining daily_series_materialized + daily_facts.
    
    Args:
        engine: SQLAlchemy engine
        start: Start date (YYYY-MM-DD)
        end: End date (YYYY-MM-DD)
    
    Returns:
        DataFrame with columns: fact_date, fat_mass_ema_kg, bmr_kcal, intake_kcal, workout_kcal
    """
    query = text("""
        SELECT 
            dsm.fact_date,
            dsm.fat_mass_ema_kg,
            dsm.bmr_kcal,
            df.intake_kcal,
            df.workout_kcal
        FROM daily_series_materialized dsm
        JOIN daily_facts df ON dsm.fact_date = df.fact_date
        WHERE dsm.fact_date BETWEEN :start_date AND :end_date
        ORDER BY dsm.fact_date
    """)
    
    df = pd.read_sql(query, engine, params={'start_date': start, 'end_date': end})
    df['fact_date'] = pd.to_datetime(df['fact_date'])
    # Convert numeric columns to float to avoid Decimal type issues
    numeric_cols = ['fat_mass_ema_kg', 'bmr_kcal', 'intake_kcal', 'workout_kcal']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = df[col].astype(float)
    return df

def make_weeks(df: pd.DataFrame, min_days: int = 6, week_end: str = 'SUN') -> pd.DataFrame:
    """
    Create Sun-ending, non-overlapping weekly windows with alpha implied calculations.
    
    Args:
        df: Daily data DataFrame
        min_days: Minimum days required per week
        week_end: Day of week for week end ('SUN')
    
    Returns:
        DataFrame with weekly summaries including alpha_implied_kcal_per_kg
    """
    weeks_data = []
    
    # Group by week ending on Sunday
    df['week_end'] = df['fact_date'].dt.to_period('W-SUN').dt.end_time.dt.date
    
    for week_end_date, week_df in df.groupby('week_end'):
        week_df = week_df.sort_values('fact_date')
        
        if len(week_df) >= min_days:
            # Calculate weekly metrics
            energy_sum = (week_df['intake_kcal'] - week_df['workout_kcal'] - week_df['bmr_kcal']).sum()
            fm_change = week_df['fat_mass_ema_kg'].iloc[-1] - week_df['fat_mass_ema_kg'].iloc[0]
            
            # Calculate alpha implied (assuming c=0 for this calculation)
            alpha_implied = None
            if energy_sum != 0 and fm_change != 0:
                alpha_implied = -energy_sum / fm_change
            
            weeks_data.append({
                'week_start': week_df['fact_date'].min().date(),
                'week_end': week_df['fact_date'].max().date(),
                'days': len(week_df),
                'energy_sum_kcal': energy_sum,
                'fm_change_kg': fm_change,
                'alpha_implied_kcal_per_kg': alpha_implied,
                'data': week_df
            })
    
    return pd.DataFrame(weeks_data)

def fit_alpha_c(weeks_df: pd.DataFrame, prior_alpha: float, prior_c: float, 
                huber_delta: float = 1.35, bounds_alpha: Tuple = (9200, 10200), 
                bounds_c: Tuple = (0.05, 0.35)) -> Tuple[float, float, float, float]:
    """
    Fit alpha and c parameters using Huber loss and bounded optimization.
    
    Args:
        weeks: List of week data dictionaries
        prior_alpha: Prior alpha value
        prior_c: Prior c value
        huber_delta: Huber loss delta parameter
        bounds_alpha: Alpha bounds (min, max)
        bounds_c: C bounds (min, max)
    
    Returns:
        Tuple of (alpha_hat, c_hat, bias_kg, mae)
    """
    def huber_loss(residuals, delta):
        """Huber loss function."""
        abs_res = np.abs(residuals)
        return np.where(abs_res <= delta, 0.5 * abs_res**2, delta * (abs_res - 0.5 * delta))
    
    def objective(params):
        """Objective function for optimization."""
        alpha, c = params
        
        total_loss = 0
        residuals = []
        
        for _, week_row in weeks_df.iterrows():
            week_df = week_row['data']
            
            # Calculate energy sum for this week
            energy_sum = (week_df['intake_kcal'] - (1 - c) * week_df['workout_kcal'] - week_df['bmr_kcal']).sum()
            
            # Observed fat mass change
            fm_change = week_df['fat_mass_ema_kg'].iloc[-1] - week_df['fat_mass_ema_kg'].iloc[0]
            
            # Model prediction: Δfm ≈ bias + (-energy_sum / alpha)
            predicted_change = -energy_sum / alpha
            
            residual = fm_change - predicted_change
            residuals.append(residual)
            
            total_loss += huber_loss(residual, huber_delta)
        
        return total_loss
    
    # Try SciPy optimization first
    try:
        from scipy.optimize import minimize
        
        result = minimize(
            objective,
            x0=[prior_alpha, prior_c],
            method='SLSQP',
            bounds=[bounds_alpha, bounds_c],
            options={'maxiter': 1000}
        )
        
        if result.success:
            alpha_hat, c_hat = result.x
        else:
            # Fallback to grid search
            alpha_hat, c_hat = _grid_search(objective, bounds_alpha, bounds_c, prior_alpha, prior_c)
    
    except ImportError:
        # Fallback to grid search if SciPy unavailable
        alpha_hat, c_hat = _grid_search(objective, bounds_alpha, bounds_c, prior_alpha, prior_c)
    
    # Calculate bias and MAE
    residuals = []
    for _, week_row in weeks_df.iterrows():
        week_df = week_row['data']
        energy_sum = (week_df['intake_kcal'] - (1 - c_hat) * week_df['workout_kcal'] - week_df['bmr_kcal']).sum()
        fm_change = week_df['fat_mass_ema_kg'].iloc[-1] - week_df['fat_mass_ema_kg'].iloc[0]
        predicted_change = -energy_sum / alpha_hat
        residuals.append(fm_change - predicted_change)
    
    bias_kg = np.mean(residuals)
    mae = np.mean(np.abs(residuals))
    
    return alpha_hat, c_hat, bias_kg, mae

def _grid_search(objective, bounds_alpha, bounds_c, prior_alpha, prior_c):
    """Coarse grid search fallback when SciPy is unavailable."""
    alpha_range = np.linspace(bounds_alpha[0], bounds_alpha[1], 20)
    c_range = np.linspace(bounds_c[0], bounds_c[1], 20)
    
    best_loss = float('inf')
    best_params = [prior_alpha, prior_c]
    
    for alpha in alpha_range:
        for c in c_range:
            loss = objective([alpha, c])
            if loss < best_loss:
                best_loss = loss
                best_params = [alpha, c]
    
    # Local refinement around best point
    alpha_center, c_center = best_params
    alpha_refined = np.linspace(max(bounds_alpha[0], alpha_center - 50), 
                                min(bounds_alpha[1], alpha_center + 50), 10)
    c_refined = np.linspace(max(bounds_c[0], c_center - 0.05), 
                           min(bounds_c[1], c_center + 0.05), 10)
    
    for alpha in alpha_refined:
        for c in c_refined:
            loss = objective([alpha, c])
            if loss < best_loss:
                best_loss = loss
                best_params = [alpha, c]
    
    return best_params

def apply_caps(alpha_hat: float, c_hat: float, prior_alpha: float, prior_c: float, 
               cap: float = 0.03) -> Tuple[float, float]:
    """
    Apply monthly caps to parameter updates.
    
    Args:
        alpha_hat: Fitted alpha value
        c_hat: Fitted c value
        prior_alpha: Prior alpha value
        prior_c: Prior c value
        cap: Maximum relative change (default 3%)
    
    Returns:
        Tuple of (alpha_capped, c_capped)
    """
    alpha_change = (alpha_hat - prior_alpha) / prior_alpha
    c_change = (c_hat - prior_c) / prior_c
    
    alpha_capped = prior_alpha + np.sign(alpha_change) * min(abs(alpha_change), cap) * prior_alpha
    c_capped = prior_c + np.sign(c_change) * min(abs(c_change), cap) * prior_c
    
    return alpha_capped, c_capped

def guardrails(bias_kg: float, weeks_count: int, mae: float, 
               thresholds: Dict[str, float] = None) -> Tuple[bool, List[str]]:
    """
    Check guardrails for parameter update.
    
    Args:
        bias_kg: Fitted bias in kg
        weeks_count: Number of weeks used
        mae: Mean absolute error in kg/week
        thresholds: Guardrail thresholds
    
    Returns:
        Tuple of (is_ok, reasons)
    """
    if thresholds is None:
        thresholds = {
            'max_bias': 0.2,
            'min_weeks': 2,
            'max_mae': 1.0
        }
    
    reasons = []
    
    if abs(bias_kg) > thresholds['max_bias']:
        reasons.append(f"Bias too large: {bias_kg:.3f} kg > {thresholds['max_bias']} kg")
    
    if weeks_count < thresholds['min_weeks']:
        reasons.append(f"Insufficient weeks: {weeks_count} < {thresholds['min_weeks']}")
    
    if mae > thresholds['max_mae']:
        reasons.append(f"MAE too large: {mae:.3f} kg/week > {thresholds['max_mae']} kg/week")
    
    is_ok = len(reasons) == 0
    return is_ok, reasons

def emit_insert(version_id: str, asof: str, alpha_new: float, c_new: float, 
                bias_kg: float, mae: float) -> str:
    """
    Generate SQL INSERT statement for parameter update.
    
    Args:
        version_id: Version identifier
        asof: Effective date
        alpha_new: New alpha value
        c_new: New c value
        bias_kg: Fitted bias
        mae: Mean absolute error
    
    Returns:
        SQL INSERT statement as string
    """
    sql = f"""
INSERT INTO model_params_timevarying (
    params_version,
    effective_start_date,
    effective_end_date,
    c_exercise_comp,
    alpha_fm,
    alpha_lbm,
    bmr0_kcal,
    k_lbm_kcal_per_kg,
    created_by,
    created_at
) VALUES (
    '{version_id}',
    '{asof}',
    NULL,
    {c_new:.4f},
    0.25,
    0.10,
    1500.0,
    20.0,
    'bayes_update',
    NOW()
);
"""
    return sql.strip()

def get_priors(engine, asof: str) -> Priors:
    """
    Get active parameter values from model_params_timevarying.
    
    Args:
        engine: SQLAlchemy engine
        asof: Date to get active parameters for
    
    Returns:
        Priors dataclass with parameter values
    """
    query = text("""
        SELECT 
            params_version,
            c_exercise_comp,
            alpha_fm,
            alpha_lbm,
            bmr0_kcal,
            k_lbm_kcal_per_kg,
            kcal_per_kg_fat
        FROM model_params_timevarying
        WHERE effective_start_date <= :asof
          AND (effective_end_date IS NULL OR effective_end_date >= :asof)
        ORDER BY effective_start_date DESC
        LIMIT 1
    """)
    
    with engine.connect() as conn:
        result = conn.execute(query, {'asof': asof})
        row = result.fetchone()
    
    if row is None:
        raise ValueError(f"No active parameters found for date {asof}")
    
    return Priors(
        version=row[0],
        c0=float(row[1]),
        alpha_fm=float(row[2]),
        alpha_lbm=float(row[3]),
        bmr0=float(row[4]),
        k_lbm=float(row[5]),
        alpha0=float(row[6]) if row[6] is not None else 7700.0  # Default if null
    )

def main():
    """Main CLI function."""
    parser = argparse.ArgumentParser(description='Bayesian parameter updater')
    parser.add_argument('--asof', type=str, help='Date to update parameters for (YYYY-MM-DD)')
    parser.add_argument('--cap', type=float, default=0.03, help='Maximum relative change cap')
    parser.add_argument('--min-days', type=int, default=6, help='Minimum days per week')
    
    args = parser.parse_args()
    
    # Default to month-end of today if not specified
    if args.asof is None:
        today = date.today()
        # Get last day of current month
        if today.month == 12:
            month_end = date(today.year + 1, 1, 1) - pd.Timedelta(days=1)
        else:
            month_end = date(today.year, today.month + 1, 1) - pd.Timedelta(days=1)
        asof = month_end.strftime('%Y-%m-%d')
    else:
        asof = args.asof
    
    # Calculate month start and end
    asof_date = datetime.strptime(asof, '%Y-%m-%d').date()
    month_start = date(asof_date.year, asof_date.month, 1)
    month_end = asof_date
    
    print(f"Bayesian Parameter Update for {asof}")
    print(f"Month range: {month_start} to {month_end}")
    print()
    
    # Database connection
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("ERROR: DATABASE_URL environment variable not set")
        sys.exit(1)
    
    engine = create_engine(database_url)
    
    try:
        # Get priors
        priors = get_priors(engine, asof)
        print(f"Active parameters: {priors.version}")
        print(f"Prior c: {priors.c0:.4f}")
        print(f"Prior alpha: {priors.alpha0:.1f}")
        print()
        
        # Load data and create weeks
        daily_data = load_daily(engine, month_start.strftime('%Y-%m-%d'), month_end.strftime('%Y-%m-%d'))
        weeks_df = make_weeks(daily_data, args.min_days)
        
        if len(weeks_df) == 0:
            print("NO UPDATE — No valid weeks found")
            sys.exit(0)
        
        print(f"Found {len(weeks_df)} valid weeks:")
        for i, (_, week_row) in enumerate(weeks_df.iterrows(), 1):
            print(f"  Week {i}: {week_row['week_start']} to {week_row['week_end']} ({week_row['days']} days)")
        print()
        
        # Fit parameters
        alpha_hat, c_hat, bias_kg, mae = fit_alpha_c(weeks_df, priors.alpha0, priors.c0)
        
        # Apply caps
        alpha_capped, c_capped = apply_caps(alpha_hat, c_hat, priors.alpha0, priors.c0, args.cap)
        
        # Check guardrails and build reasons
        reasons = []
        if abs(bias_kg) > 0.2:
            reasons.append(f"|bias|={abs(bias_kg):.3f}>0.2")
        if weeks_df.shape[0] < 2:
            reasons.append("insufficient weeks")
        # Optional: if mae too large add: reasons.append(f"mae={mae:.3f} high")
        
        capped_reason = "OK"
        if reasons:
            capped_reason = "NO UPDATE: " + "; ".join(reasons)
        
        print("Fit Summary:")
        print(f"  Alpha (fitted): {alpha_hat:.1f} → (capped): {alpha_capped:.1f}")
        print(f"  C (fitted): {c_hat:.4f} → (capped): {c_capped:.4f}")
        print(f"  Bias: {bias_kg:.3f} kg")
        print(f"  MAE: {mae:.3f} kg/week")
        print()
        
        # Create proposal
        proposal_id = emit_proposal(
            engine, datetime.strptime(asof, '%Y-%m-%d').date(), priors,
            alpha_hat, c_hat, bias_kg, mae,
            alpha_capped, c_capped, args.cap,
            weeks_df, capped_reason
        )
        
        print(f"\nProposal recorded as proposal_id = {proposal_id}")
        print_approval_sql(proposal_id)
        print_reject_sql(proposal_id)
    
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
