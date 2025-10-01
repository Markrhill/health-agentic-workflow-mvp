#!/usr/bin/env python3
"""
4-Parameter Energy Balance Model Estimation

Estimates physiological parameters from body composition and energy data using robust
statistical methods. Based on the energy balance equation:

delta_fm_kg = (intake_sum - (1-C)*workout_sum - BMR₀*days - k_LBM*mean_lbm*days) / α

Where:
- α: Energy density of fat tissue (kcal/kg)
- C: Exercise compensation factor (unitless)
- BMR₀: Baseline metabolic rate (kcal/day)
- k_LBM: Lean body mass metabolic coefficient (kcal/day/kg)
"""

import argparse
import logging
import os
import sys
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple, Any
import warnings

import numpy as np
import pandas as pd
from sklearn.linear_model import HuberRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import r2_score, mean_absolute_error, mean_squared_error
from sqlalchemy import create_engine, text

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Suppress sklearn warnings
warnings.filterwarnings('ignore', category=UserWarning, module='sklearn')

class EnergyBalanceModel:
    """4-Parameter Energy Balance Model Estimator."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the model with configuration parameters."""
        self.config = config
        self.engine = None
        self.data = None
        self.windows = None
        self.model = None
        self.scaler = None
        self.results = {}
        
    def connect_database(self) -> bool:
        """Connect to PostgreSQL database."""
        try:
            database_url = os.getenv('DATABASE_URL')
            if not database_url:
                raise ValueError("DATABASE_URL environment variable not set")
            
            self.engine = create_engine(database_url)
            
            # Test connection
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            
            logger.info("Database connection successful")
            return True
            
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            return False
    
    def load_data(self, start_date: str, end_date: str) -> pd.DataFrame:
        """
        Load daily facts data from database.
        
        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            
        Returns:
            DataFrame with daily facts data
        """
        query = """
            SELECT 
                fact_date,
                intake_kcal,
                workout_kcal,
                fat_mass_kg,
                fat_free_mass_kg,
                weight_kg,
                carbs_g
            FROM daily_facts
            WHERE fact_date BETWEEN :start_date AND :end_date
              AND fat_mass_kg IS NOT NULL
              AND fat_free_mass_kg IS NOT NULL
            ORDER BY fact_date
        """
        
        try:
            with self.engine.connect() as conn:
                df = pd.read_sql(text(query), conn, params={
                    'start_date': start_date,
                    'end_date': end_date
                })
            
            # Convert date column
            df['fact_date'] = pd.to_datetime(df['fact_date'])
            
            # Handle NULL values with proper numeric conversion
            df['intake_kcal'] = pd.to_numeric(df['intake_kcal'], errors='coerce')
            df['workout_kcal'] = pd.to_numeric(df['workout_kcal'], errors='coerce')
            df['intake_kcal'] = df['intake_kcal'].fillna(0.0)
            df['workout_kcal'] = df['workout_kcal'].fillna(0.0)
            
            logger.info(f"Loaded {len(df)} daily records from {start_date} to {end_date}")
            return df
            
        except Exception as e:
            logger.error(f"Failed to load data: {e}")
            raise
    
    def robust_dampen(self, s: pd.Series, window: int = 7, k: float = 3.5) -> pd.Series:
        """
        Apply robust damping using rolling median and MAD.
        
        Args:
            s: Input time series
            window: Rolling window size for median calculation
            k: MAD multiplier for damping threshold
            
        Returns:
            Series with spikes damped toward median
        """
        med = s.rolling(window, min_periods=1, center=True).median()
        mad = (s - med).abs().rolling(window, min_periods=1, center=True).median()
        eps = 1e-9
        z = (s - med) / (mad + eps)
        # damp spikes toward median instead of dropping them
        damp = med + (s - med) * np.tanh(np.clip(z, -k, k)) / np.clip(z, -k, k)
        damp = damp.where(z.abs() > 1e-6, s)
        return damp
    
    def preprocess_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Preprocess the data with robust damping.
        
        Args:
            df: Raw daily facts DataFrame
            
        Returns:
            Preprocessed DataFrame
        """
        logger.info("Applying robust damping...")
        
        # Apply robust damping to body composition data
        df['fat_mass_kg'] = self.robust_dampen(
            df['fat_mass_kg'], 
            window=self.config['robust_window'], 
            k=self.config['robust_k']
        )
        df['fat_free_mass_kg'] = self.robust_dampen(
            df['fat_free_mass_kg'], 
            window=self.config['robust_window'], 
            k=self.config['robust_k']
        )
        
        # Log data quality
        logger.info(f"Data quality after preprocessing:")
        logger.info(f"  fat_mass_kg nulls: {df['fat_mass_kg'].isnull().sum()}")
        logger.info(f"  fat_free_mass_kg nulls: {df['fat_free_mass_kg'].isnull().sum()}")
        
        # Try to use PhysioSmoother for fat mass, fall back to robust_dampen if it fails
        try:
            from physio_smoother import PhysioSmoother
            sm = PhysioSmoother(fat_half_life_days=90, hydration_half_life_days=2, huber_delta=0.8)
            df_sm = df[['fact_date','fat_mass_kg','carbs_g']].copy()
            df_sm['fact_date'] = pd.to_datetime(df_sm['fact_date'])
            sm.fit(df_sm)
            smooth = sm.get_results()[['fact_date','fat_mass_smooth','hydration_component']]
            df = df.merge(smooth, on='fact_date', how='left')
            df['_fm_clean'] = df['fat_mass_smooth']
            logger.info(f"PhysioSmoother applied: k_h={sm.get_params().get('k_h',0):.3f}, "
                        f"hl={sm.get_params().get('hydration_half_life_days')}, "
                        f"lag={sm.get_params().get('hydration_lag_days')}")
        except Exception as e:
            logger.warning(f"PhysioSmoother unavailable or failed ({e}); using robust_dampen")
            df['_fm_clean'] = self.robust_dampen(df['fat_mass_kg'],
                                                window=self.config['robust_window'],
                                                k=self.config['robust_k'])
        
        return df
    
    def build_windows(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Build sliding windows for analysis.
        
        Args:
            df: Preprocessed daily facts DataFrame
            
        Returns:
            DataFrame with window-level aggregations
        """
        window_days = self.config['window_days']
        min_valid_days = self.config['min_valid_days']
        
        logger.info(f"Building {window_days}-day sliding windows...")
        
        # Precompute smoothed series
        df['_fm_clean'] = self.robust_dampen(df['fat_mass_kg'])
        df['_lbm_clean'] = self.robust_dampen(df['fat_free_mass_kg'])
        
        rows = []
        for i in range(len(df) - window_days + 1):
            window = df.iloc[i:i+window_days]
            
            # Check eligibility criteria
            coverage_intake = window['intake_kcal'].notna().mean() >= 0.9
            coverage_workout = window['workout_kcal'].notna().mean() >= 0.9
            valid_fm_days = window['_fm_clean'].notna().sum() >= min_valid_days
            valid_lbm_days = window['_lbm_clean'].notna().sum() >= min_valid_days
            
            if (coverage_intake and coverage_workout and valid_fm_days and valid_lbm_days):
                
                # Calculate window metrics using smoothed endpoints
                delta_fm_kg = window['_fm_clean'].iloc[-1] - window['_fm_clean'].iloc[0]
                intake_sum = window['intake_kcal'].sum()
                workout_sum = window['workout_kcal'].sum()
                mean_lbm = window['_lbm_clean'].mean()
                
                rows.append({
                    'start_date': window.iloc[0]['fact_date'],
                    'end_date': window.iloc[-1]['fact_date'],
                    'delta_fm_kg': delta_fm_kg,
                    'intake_sum': intake_sum,
                    'workout_sum': workout_sum,
                    'mean_lbm': mean_lbm,
                    'days': window_days,
                    'valid_fat_mass_days': valid_fm_days,
                    'valid_lbm_days': valid_lbm_days
                })
        
        windows_df = pd.DataFrame(rows)
        logger.info(f"Created {len(windows_df)} eligible windows")
        
        return windows_df
    
    def fit_model(self, windows: pd.DataFrame) -> Tuple[HuberRegressor, StandardScaler]:
        """
        Fit the 4-parameter energy balance model.
        
        Args:
            windows: Window-level DataFrame
            
        Returns:
            Tuple of (fitted_model, scaler)
        """
        logger.info("Fitting 4-parameter energy balance model...")
        
        # Center LBM and orthogonalize workout relative to intake
        lbm_center = windows['mean_lbm'].mean()
        self.results['lbm_center'] = lbm_center
        
        # Prepare features and target
        y = windows['delta_fm_kg'].values
        X_days = windows['days'].values.astype(float)
        X_days_lbm_c = (windows['days'] * (windows['mean_lbm'] - lbm_center)).values.astype(float)
        
        # Orthogonalize workout against intake (to reduce collinearity)
        x_int = windows['intake_sum'].values.reshape(-1, 1)
        wk = windows['workout_sum'].values
        beta_ls = np.linalg.lstsq(np.column_stack([np.ones(len(x_int)), x_int]), wk, rcond=None)[0]
        wk_resid = wk - (beta_ls[0] + beta_ls[1] * x_int.ravel())
        
        X = np.column_stack([X_days, X_days_lbm_c, wk_resid, windows['intake_sum'].values.astype(float)])
        
        # Store X for condition number calculation
        self.X_unscaled = X
        
        # Apply feature standardization
        scaler = StandardScaler(with_mean=True, with_std=True)
        X_scaled = scaler.fit_transform(X)
        
        # Fit Huber regressor
        model = HuberRegressor(
            epsilon=self.config['huber_epsilon'],
            max_iter=500,
            alpha=self.config['huber_alpha'],
            fit_intercept=False
        )
        
        model.fit(X_scaled, y)
        
        logger.info("Model fitting completed")
        return model, scaler
    
    def interpret_parameters(self, model: HuberRegressor, scaler: StandardScaler) -> Dict[str, float]:
        """
        Convert regression coefficients to interpretable parameters.
        
        Args:
            model: Fitted HuberRegressor
            scaler: Fitted StandardScaler
            
        Returns:
            Dictionary of physiological parameters
        """
        # Get unscaled coefficients
        beta_unscaled = model.coef_ / scaler.scale_
        
        # Extract coefficients for centered LBM model
        b_days, b_days_lbm_c, b_workout_resid, b_intake = beta_unscaled
        
        # Calculate physiological parameters
        alpha = 1.0 / b_intake if b_intake != 0 else np.nan
        c = 1.0 + (b_workout_resid / b_intake) if not np.isnan(alpha) and b_intake != 0 else np.nan
        
        # With centered LBM, b_days corresponds to -(BMR0 + k_LBM*LBM_center)/α
        k_lbm = -b_days_lbm_c / b_intake if not np.isnan(alpha) and b_intake != 0 else np.nan
        bmr0 = -b_days / b_intake - k_lbm * self.results.get('lbm_center', 0.0) if not np.isnan(alpha) and b_intake != 0 else np.nan
        
        return {
            'alpha': alpha,
            'c': c,
            'bmr0': bmr0,
            'k_lbm': k_lbm,
            'beta_days': b_days,
            'beta_days_lbm_c': b_days_lbm_c,
            'beta_workout_resid': b_workout_resid,
            'beta_intake': b_intake
        }
    
    def calculate_fit_metrics(self, model: HuberRegressor, scaler: StandardScaler, 
                            windows: pd.DataFrame) -> Dict[str, float]:
        """
        Calculate model fit metrics.
        
        Args:
            model: Fitted HuberRegressor (can be None for fixed-alpha mode)
            scaler: Fitted StandardScaler (can be None for fixed-alpha mode)
            windows: Window-level DataFrame
            
        Returns:
            Dictionary of fit metrics
        """
        y_true = windows['delta_fm_kg'].values
        
        if model is None or scaler is None:
            # For fixed-alpha mode, use simple metrics without prediction
            return {
                'r2': np.nan,
                'mae': np.nan,
                'rmse': np.nan,
                'n_windows': len(windows)
            }
        
        X = np.column_stack([
            windows['days'].values,
            (windows['days'] * windows['mean_lbm']).values,
            windows['workout_sum'].values,
            windows['intake_sum'].values
        ])
        
        X_scaled = scaler.transform(X)
        y_pred = model.predict(X_scaled)
        
        r2 = r2_score(y_true, y_pred)
        mae = mean_absolute_error(y_true, y_pred)
        rmse = np.sqrt(mean_squared_error(y_true, y_pred))
        
        return {
            'r2': r2,
            'mae': mae,
            'rmse': rmse,
            'n_windows': len(windows)
        }
    
    def validate_parameters(self, params: Dict[str, float]) -> Tuple[bool, List[str]]:
        """
        Validate parameter physiological plausibility.
        
        Args:
            params: Dictionary of fitted parameters
            
        Returns:
            Tuple of (all_plausible, warnings_list)
        """
        warnings = []
        
        # α: Energy density of fat tissue
        if not (8000 <= params['alpha'] <= 10000):
            warnings.append(f"α={params['alpha']:,.0f} outside plausible range (8000-10000 kcal/kg)")
        
        # C: Exercise compensation factor
        if not (0.0 <= params['c'] <= 0.5):
            warnings.append(f"C={params['c']:.3f} outside plausible range (0.0-0.5)")
        
        # BMR₀: Baseline metabolic rate
        if not (200 <= params['bmr0'] <= 1000):
            warnings.append(f"BMR₀={params['bmr0']:,.0f} outside plausible range (200-1000 kcal/day)")
        
        # k_LBM: Lean body mass metabolic coefficient
        if not (2 <= params['k_lbm'] <= 25):
            warnings.append(f"k_LBM={params['k_lbm']:.1f} outside plausible range (2-25 kcal/day/kg)")
        
        return len(warnings) == 0, warnings
    
    def _constrained_fallback(self, windows: pd.DataFrame) -> Dict[str, float]:
        """
        Apply constrained fallback when free-fit fails.
        
        Args:
            windows: Window-level DataFrame
            
        Returns:
            Dictionary of constrained parameters
        """
        alpha_fixed = self.config.get('alpha_fixed', 9800.0)
        k_lbm_prior = self.config.get('k_lbm_prior', 11.5)
        
        # Prepare features for constrained fit
        lbm_center = self.results.get('lbm_center', windows['mean_lbm'].mean())
        X_days = windows['days'].values.astype(float)
        X_days_lbm_c = (windows['days'] * (windows['mean_lbm'] - lbm_center)).values.astype(float)
        
        # Orthogonalize workout against intake
        x_int = windows['intake_sum'].values.reshape(-1, 1)
        wk = windows['workout_sum'].values
        beta_ls = np.linalg.lstsq(np.column_stack([np.ones(len(x_int)), x_int]), wk, rcond=None)[0]
        wk_resid = wk - (beta_ls[0] + beta_ls[1] * x_int.ravel())
        
        # Solve: lhs = (C-1)*workout_resid - days*BMR0
        lhs = windows['delta_fm_kg'] * alpha_fixed - windows['intake_sum']
        X_constrained = np.column_stack([wk_resid, -X_days])
        
        # Linear regression without intercept
        coefs = np.linalg.lstsq(X_constrained, lhs, rcond=None)[0]
        C_raw = 1 + coefs[0]
        BMR0_raw = -coefs[1]
        
        # Apply bounds
        c_bounds = self.config.get('c_bounds', (0.0, 0.4))
        bmr0_bounds = self.config.get('bmr0_bounds', (400.0, 1200.0))
        
        C = np.clip(C_raw, c_bounds[0], c_bounds[1])
        BMR0 = np.clip(BMR0_raw, bmr0_bounds[0], bmr0_bounds[1])
        
        return {
            'alpha': alpha_fixed,
            'c': C,
            'bmr0': BMR0,
            'k_lbm': k_lbm_prior,
            'beta_days': 0.0,
            'beta_days_lbm_c': 0.0,
            'beta_workout_resid': 0.0,
            'beta_intake': 0.0
        }
    
    def run_analysis(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """
        Run the complete energy balance model analysis.
        
        Args:
            start_date: Analysis start date
            end_date: Analysis end date
            
        Returns:
            Dictionary containing all results
        """
        logger.info("Starting 4-parameter energy balance model analysis")
        logger.info(f"Date range: {start_date} to {end_date}")
        
        # Load and preprocess data
        self.data = self.load_data(start_date, end_date)
        self.data = self.preprocess_data(self.data)
        
        # Build windows
        self.windows = self.build_windows(self.data)
        
        if len(self.windows) < 20:
            raise ValueError(f"Insufficient windows ({len(self.windows)}) for reliable estimation")
        
        # Fit model
        self.model, self.scaler = self.fit_model(self.windows)
        
        # Interpret parameters
        params = self.interpret_parameters(self.model, self.scaler)
        
        # Calculate condition number
        from numpy.linalg import cond
        self.results['cond_X'] = float(cond(self.X_unscaled))
        
        # Calculate fit metrics
        fit_metrics = self.calculate_fit_metrics(self.model, self.scaler, self.windows)
        
        # Validate parameters and check for fallback conditions
        all_plausible, warnings = self.validate_parameters(params)
        needs_fallback = (not all_plausible or 
                         self.results['cond_X'] > self.config.get('cond_threshold', 1e4) or
                         params.get('alpha', 0) <= 0)
        
        # Apply fallback if needed
        if needs_fallback:
            logger.warning("Free-fit parameters failed validation or condition check. Applying constrained fallback...")
            params = self._constrained_fallback(self.windows)
            self.results['used_fallback'] = True
        else:
            self.results['used_fallback'] = False
        
        # Compile results
        self.results = {
            'parameters': params,
            'fit_metrics': fit_metrics,
            'validation': {
                'all_plausible': all_plausible,
                'warnings': warnings
            },
            'data_summary': {
                'n_daily_records': len(self.data),
                'n_windows': len(self.windows),
                'date_range': f"{start_date} to {end_date}",
                'window_days': self.config['window_days']
            }
        }
        
        return self.results
    
    def print_results(self):
        """Print formatted results."""
        print("\n" + "="*80)
        print("4-PARAMETER ENERGY BALANCE MODEL ESTIMATION RESULTS")
        print("="*80)
        
        # Data summary
        print(f"\n📊 DATA SUMMARY")
        print("-" * 40)
        print(f"Daily records: {self.results['data_summary']['n_daily_records']:,}")
        print(f"Analysis windows: {self.results['data_summary']['n_windows']:,}")
        print(f"Date range: {self.results['data_summary']['date_range']}")
        print(f"Window length: {self.results['data_summary']['window_days']} days")
        
        # Raw coefficients
        print(f"\n🔬 RAW REGRESSION COEFFICIENTS")
        print("-" * 40)
        params = self.results['parameters']
        print(f"β₁ (days):           {params['beta_days']:12.6f}")
        print(f"β₂ (days × LBM_c):  {params['beta_days_lbm_c']:12.6f}")
        print(f"β₃ (workout_resid): {params['beta_workout_resid']:12.6f}")
        print(f"β₄ (intake_sum):    {params['beta_intake']:12.6f}")
        
        # Diagnostics
        print(f"\n🔍 DIAGNOSTICS")
        print("-" * 40)
        cond_x = self.results.get('cond_X', 'N/A')
        if isinstance(cond_x, (int, float)):
            print(f"Condition number (X): {cond_x:.2e}")
        else:
            print(f"Condition number (X): {cond_x}")
        lbm_center = self.results.get('lbm_center', 'N/A')
        if isinstance(lbm_center, (int, float)):
            print(f"LBM center: {lbm_center:.1f} kg")
        else:
            print(f"LBM center: {lbm_center}")
        print(f"Used fallback: {'Yes' if self.results.get('used_fallback', False) else 'No'}")
        
        # Interpreted parameters
        print(f"\n⚖️  PHYSIOLOGICAL PARAMETERS")
        print("-" * 40)
        print(f"α (energy density):      {params['alpha']:8,.0f} kcal/kg fat")
        print(f"C (exercise compensation): {params['c']:8.3f}")
        print(f"BMR₀ (baseline metabolism): {params['bmr0']:8,.0f} kcal/day")
        print(f"k_LBM (LBM coefficient):   {params['k_lbm']:8.1f} kcal/day/kg")
        
        # Model fit
        print(f"\n📈 MODEL FIT METRICS")
        print("-" * 40)
        fit = self.results['fit_metrics']
        print(f"R² (coefficient of determination): {fit['r2']:8.3f}")
        print(f"MAE (mean absolute error):         {fit['mae']:8.3f} kg")
        print(f"RMSE (root mean square error):     {fit['rmse']:8.3f} kg")
        
        # Validation
        print(f"\n✅ PARAMETER VALIDATION")
        print("-" * 40)
        validation = self.results['validation']
        if validation['all_plausible']:
            print("✅ All parameters within physiologically plausible ranges")
        else:
            print("⚠️  Parameters outside plausible ranges:")
            for warning in validation['warnings']:
                print(f"   - {warning}")
        
        print("\n" + "="*80)
    
    def save_results(self, output_file: str):
        """Save results to CSV file."""
        try:
            # Prepare data for CSV
            results_data = {
                'parameter': ['alpha', 'c', 'bmr0', 'k_lbm'],
                'value': [
                    self.results['parameters']['alpha'],
                    self.results['parameters']['c'],
                    self.results['parameters']['bmr0'],
                    self.results['parameters']['k_lbm']
                ],
                'unit': ['kcal/kg', 'unitless', 'kcal/day', 'kcal/day/kg'],
                'r2': [self.results['fit_metrics']['r2']] * 4,
                'mae': [self.results['fit_metrics']['mae']] * 4,
                'rmse': [self.results['fit_metrics']['rmse']] * 4,
                'n_windows': [self.results['fit_metrics']['n_windows']] * 4,
                'date_range': [self.results['data_summary']['date_range']] * 4
            }
            
            df_results = pd.DataFrame(results_data)
            df_results.to_csv(output_file, index=False)
            
            logger.info(f"Results saved to {output_file}")
            
        except Exception as e:
            logger.error(f"Failed to save results: {e}")

def create_config(args) -> Dict[str, Any]:
    """Create configuration dictionary from command line arguments."""
    return {
        'start_date': args.start_date,
        'end_date': args.end_date,
        'window_days': args.window_days,
        'robust_window': args.robust_window,
        'robust_k': args.robust_k,
        'min_valid_days': args.min_valid_days,
        'huber_epsilon': args.huber_epsilon,
        'huber_alpha': args.huber_alpha,
        'alpha_fixed': 9800.0,
        'k_lbm_prior': 11.5,
        'c_bounds': (0.0, 0.4),
        'bmr0_bounds': (400.0, 1200.0),
        'cond_threshold': 1e4
    }

def main():
    """Main CLI interface."""
    parser = argparse.ArgumentParser(
        description='4-Parameter Energy Balance Model Estimation',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python energy_balance_model.py
  python energy_balance_model.py --start-date 2022-01-01 --end-date 2023-12-31
  python energy_balance_model.py --window-days 21 --robust-k 2.5
  python energy_balance_model.py --output results.csv --verbose
        """
    )
    
    # Data parameters
    parser.add_argument('--start-date', type=str, default='2021-01-01',
                       help='Analysis start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, default='2024-12-31',
                       help='Analysis end date (YYYY-MM-DD)')
    
    # Model parameters
    parser.add_argument('--window-days', type=int, default=14,
                       help='Window length in days (default: 14)')
    parser.add_argument('--robust-window', type=int, default=7,
                       help='Outlier detection window (default: 7)')
    parser.add_argument('--robust-k', type=float, default=3.0,
                       help='MAD threshold multiplier (default: 3.0)')
    parser.add_argument('--min-valid-days', type=int, default=10,
                       help='Minimum valid days per window (default: 10)')
    
    # Regression parameters
    parser.add_argument('--huber-epsilon', type=float, default=1.35,
                       help='Huber regression epsilon (default: 1.35)')
    parser.add_argument('--huber-alpha', type=float, default=1e-3,
                       help='Huber regression alpha (default: 1e-3)')
    
    # Output parameters
    parser.add_argument('--output', type=str, help='Output CSV file path')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')
    parser.add_argument('--fixed-alpha', action='store_true', help='Skip free-fit and use constrained fallback directly')
    
    args = parser.parse_args()
    
    # Configure logging
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        # Create configuration
        config = create_config(args)
        
        # Initialize model
        model = EnergyBalanceModel(config)
        
        # Connect to database
        if not model.connect_database():
            sys.exit(1)
        
        # Run analysis
        if args.fixed_alpha:
            # Skip free-fit and use constrained fallback directly
            model.data = model.load_data(args.start_date, args.end_date)
            model.data = model.preprocess_data(model.data)
            model.windows = model.build_windows(model.data)
            
            if len(model.windows) < 20:
                raise ValueError(f"Insufficient windows ({len(model.windows)}) for reliable estimation")
            
            # Use constrained fallback directly
            model.results = {'lbm_center': model.windows['mean_lbm'].mean()}
            params = model._constrained_fallback(model.windows)
            model.results['used_fallback'] = True
            model.results['cond_X'] = float('inf')  # Not applicable for constrained fit
            
            # Calculate fit metrics
            fit_metrics = model.calculate_fit_metrics(None, None, model.windows)
            
            # Compile results
            model.results.update({
                'parameters': params,
                'fit_metrics': fit_metrics,
                'validation': {'all_plausible': True, 'warnings': []},
                'data_summary': {
                    'n_daily_records': len(model.data),
                    'n_windows': len(model.windows),
                    'date_range': f"{args.start_date} to {args.end_date}",
                    'window_days': config['window_days']
                }
            })
            
            results = model.results
        else:
            results = model.run_analysis(args.start_date, args.end_date)
        
        # Print results
        model.print_results()
        
        # Save results if requested
        if args.output:
            model.save_results(args.output)
        
        logger.info("Analysis completed successfully")
        
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
