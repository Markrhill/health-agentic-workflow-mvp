"""
Physiological Smoother for BIA Fat Mass Data

This module implements a physiologically grounded smoothing algorithm that separates
fat mass trends from hydration/glycogen fluctuations in noisy BIA data.

The model assumes:
- Fat compartment (F): slow trend with strong smoothing (EWMA half-life ~90 days)
- Hydration/glycogen compartment (H): fast fluctuations from carbs and alcohol
- Observed fat mass: y_t = F_t + k_H * H_t + noise_t

Author: Health Agentic Workflow MVP
Date: 2025-09-29
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from typing import Dict, Tuple, Optional, Union
import logging
from statsmodels.robust.norms import HuberT
from statsmodels.robust.robust_linear_model import RLM
import warnings

# Configure logging
logger = logging.getLogger(__name__)

class PhysioSmoother:
    """
    Physiological smoother for BIA fat mass data that separates fat trends
    from hydration/glycogen fluctuations.
    """
    
    def __init__(self, 
                 fat_half_life_days: float = 90.0,
                 hydration_half_life_days: float = 2.0,
                 carb_mass_per_g: float = 0.0035,
                 huber_delta: float = 0.8,
                 max_iterations: int = 5,
                 convergence_tol: float = 1e-6,
                 random_state: Optional[int] = None):
        """
        Initialize the physiological smoother.
        
        Args:
            fat_half_life_days: Half-life for fat compartment EWMA (days)
            hydration_half_life_days: Half-life for hydration compartment EWMA (days)
            carb_mass_per_g: Mass per gram of carbs (kg per gram of carbs)
            alcohol_mass_per_g: Mass per gram of alcohol (kg per gram of alcohol)
            huber_delta: Huber loss delta parameter for robust regression
            max_iterations: Maximum IRLS iterations
            convergence_tol: Convergence tolerance for IRLS
            random_state: Random state for reproducibility
        """
        self.config = {
            'fat_half_life_days': fat_half_life_days,
            'hydration_half_life_days': hydration_half_life_days,
            'carb_mass_per_g': carb_mass_per_g,
            'huber_delta': huber_delta,
            'max_iterations': max_iterations,
            'convergence_tol': convergence_tol,
            'random_state': random_state
        }
        
        # Initialize results
        self.df_out = None
        self.params = {}
        self.converged = False
        self.iterations = 0
        
        logger.info(f"PhysioSmoother initialized with fat_half_life={fat_half_life_days}d, "
                   f"hydration_half_life={hydration_half_life_days}d")
    
    def _ewma(self, s: pd.Series, halflife_days: float) -> pd.Series:
        """
        Compute exponentially weighted moving average.
        
        Args:
            s: Input time series
            halflife_days: Half-life in days
            
        Returns:
            EWMA of the series
        """
        return pd.Series(s).ewm(halflife=halflife_days, adjust=False).mean()
    
    def _compute_hydration_component(self, df: pd.DataFrame) -> pd.Series:
        """
        Compute hydration/glycogen component from carbs.
        
        Args:
            df: DataFrame with carbs_g column
            
        Returns:
            Hydration component time series (centered)
        """
        carbs = pd.to_numeric(df['carbs_g'], errors='coerce').fillna(0.0)
        h_raw = self._ewma(carbs * self.config['carb_mass_per_g'],
                           self.config['hydration_half_life_days'])
        return h_raw - h_raw.mean()
    
    def _huber_weights(self, residuals: np.ndarray) -> np.ndarray:
        """
        Compute Huber weights for robust regression.
        
        Args:
            residuals: Residual values
            
        Returns:
            Huber weights
        """
        delta = self.config['huber_delta']
        abs_residuals = np.abs(residuals)
        
        # Huber weight function: w = min(1, delta / |r|)
        weights = np.where(abs_residuals <= delta, 1.0, delta / abs_residuals)
        
        return weights
    
    def _robust_regression(self, X: np.ndarray, y: np.ndarray) -> Tuple[float, np.ndarray]:
        """
        Perform robust regression using Huber loss.
        
        Args:
            X: Design matrix (hydration component)
            y: Target variable (fat_mass_obs - fat_trend)
            
        Returns:
            Tuple of (coefficient, weights)
        """
        # Use statsmodels RLM with HuberT
        try:
            model = RLM(y, X, M=HuberT())
            result = model.fit()
            k_h = result.params[0]
            weights = result.weights
        except Exception as e:
            logger.warning(f"Statsmodels RLM failed: {e}. Using custom Huber regression.")
            # Fallback to custom implementation
            k_h = 0.0
            weights = np.ones_like(y)
            
            for _ in range(10):  # Simple IRLS
                # Weighted least squares
                W = np.diag(weights)
                XWX = X.T @ W @ X
                XWy = X.T @ W @ y
                
                if np.linalg.cond(XWX) < 1e12:  # Check condition number
                    k_h_new = np.linalg.solve(XWX, XWy)[0]
                else:
                    k_h_new = k_h  # Keep previous value
                
                # Update weights
                residuals = y - k_h_new * X.flatten()
                weights = self._huber_weights(residuals)
                
                # Check convergence
                if abs(k_h_new - k_h) < self.config['convergence_tol']:
                    break
                k_h = k_h_new
        
        # Apply bounds to k_h
        k_h = float(np.clip(k_h, 0.0, 1.5))
        
        return k_h, weights
    
    def fit(self, df: pd.DataFrame) -> 'PhysioSmoother':
        """
        Fit the physiological smoother to the data.
        
        Args:
            df: DataFrame with columns fact_date, fat_mass_kg, carbs_g, and optional alcohol_g
            
        Returns:
            Self for method chaining
        """
        logger.info("Starting physiological smoothing fit...")
        
        # Validate input data
        required_cols = ['fact_date', 'fat_mass_kg', 'carbs_g']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f"Missing required columns: {missing_cols}")
        
        # Sort by date and reset index
        df_sorted = df.sort_values('fact_date').reset_index(drop=True)
        
        # Normalize carbs column name
        possible = [c for c in df_sorted.columns
                    if c.lower() in ('carbs_g','carb_g','carbs','carbohydrates_g')]
        if not possible:
            raise ValueError("No carbs column found. Expected one of: carbs_g, carb_g, carbs, carbohydrates_g")
        df_sorted['carbs_g'] = pd.to_numeric(df_sorted[possible[0]], errors='coerce').fillna(0.0)

        # Cheap grid to pick hydration half-life and lag by maximizing |corr|
        best = (0.0, self.config['hydration_half_life_days'], 1)  # (|corr|, hl, lag)
        for hl in (1.0, 2.0, 3.0):
            for lag in (0, 1, 2):
                H = self._ewma(df_sorted['carbs_g'] * self.config['carb_mass_per_g'], hl)\
                      .shift(lag).bfill()
                Y = pd.Series(df_sorted['fat_mass_kg']) - self._ewma(df_sorted['fat_mass_kg'],
                                                                     self.config['fat_half_life_days'])
                m = ~(H.isna() | Y.isna())
                if m.sum() > 30:
                    corr = abs(np.corrcoef(H[m].values, Y[m].values)[0,1])
                    if corr > best[0]:
                        best = (corr, hl, lag)
        self.config['hydration_half_life_days'] = best[1]
        self.config['hydration_lag_days'] = best[2]
        logger.info(f"[PhysioSmoother] selected hydration hl={best[1]}d lag={best[2]} (|corr|={best[0]:.3f})")

        # Build hydration component with chosen settings
        h_raw = self._ewma(df_sorted['carbs_g'] * self.config['carb_mass_per_g'],
                           self.config['hydration_half_life_days'])\
                  .shift(self.config['hydration_lag_days']).bfill()
        hydration_component = (h_raw - h_raw.mean()).values
        
        # Initialize arrays
        n = len(df_sorted)
        fat_mass_obs = df_sorted['fat_mass_kg'].values
        fat_trend = np.full(n, np.nan)
        residuals = np.full(n, np.nan)
        weights = np.ones(n)
        
        # IRLS loop
        k_h = 0.0
        prev_k_h = np.inf
        
        for iteration in range(self.config['max_iterations']):
            logger.info(f"IRLS iteration {iteration + 1}/{self.config['max_iterations']}")
            
            # Step 1: Update fat trend using current k_h
            if iteration == 0:
                # Initial fat trend (no hydration correction)
                fat_trend = self._ewma(pd.Series(fat_mass_obs),
                                      self.config['fat_half_life_days']).values
            else:
                # Fat trend with hydration correction
                fat_corrected = fat_mass_obs - k_h * hydration_component
                fat_trend = self._ewma(pd.Series(fat_corrected),
                                      self.config['fat_half_life_days']).values
            
            # Step 2: Fit k_h using robust regression
            y_residual = (fat_mass_obs - fat_trend)
            y_residual_c = y_residual - np.nanmean(y_residual)  # center
            X_h = hydration_component.reshape(-1, 1)  # already centered
            valid = ~(np.isnan(y_residual_c) | np.isnan(X_h).ravel())
            
            if valid.sum() < 10:
                logger.warning("Insufficient valid data for regression")
                break
            
            y_valid = y_residual_c[valid]
            X_valid = X_h[valid]
            
            k_h_new, weights_valid = self._robust_regression(X_valid, y_valid)
            
            # Update weights for all data points
            weights[valid] = weights_valid
            weights[~valid] = 0.0
            
            # Check convergence
            if abs(k_h_new - prev_k_h) < self.config['convergence_tol']:
                logger.info(f"Converged after {iteration + 1} iterations")
                self.converged = True
                break
            
            k_h = k_h_new
            prev_k_h = k_h_new
            
            logger.info(f"k_h = {k_h:.6f}, mean |residual| = {np.nanmean(np.abs(y_residual)):.4f}")
        
        if not self.converged:
            logger.warning(f"Did not converge after {self.config['max_iterations']} iterations")
        
        # Final fat trend with converged k_h
        fat_corrected = fat_mass_obs - k_h * hydration_component
        fat_trend = self._ewma(pd.Series(fat_corrected),
                              self.config['fat_half_life_days']).values
        
        # Compute final residuals and intercept shift
        residuals = fat_mass_obs - (fat_trend + k_h * hydration_component)
        intercept_shift = float(np.nanmean(fat_mass_obs - (fat_trend + k_h * hydration_component)))
        
        # Store results
        self.df_out = df_sorted.copy()
        self.df_out['fat_mass_obs'] = fat_mass_obs
        self.df_out['fat_mass_smooth'] = fat_trend
        self.df_out['hydration_component'] = k_h * hydration_component
        self.df_out['residuals'] = residuals
        self.df_out['weights'] = weights
        
        # Store parameters
        self.params = {
            'k_h': k_h,
            'intercept_shift_kg': intercept_shift,
            'mean_abs_residual': np.nanmean(np.abs(residuals)),
            'converged': self.converged,
            'iterations': iteration + 1,
            'config': self.config.copy()
        }
        
        self.params.update({
            'hydration_half_life_days': self.config['hydration_half_life_days'],
            'hydration_lag_days': self.config.get('hydration_lag_days', 1),
        })
        
        self.iterations = iteration + 1
        
        logger.info(f"Fit complete: k_h = {k_h:.6f}, mean |residual| = {self.params['mean_abs_residual']:.4f}")
        
        return self
    
    def plot(self, figsize: Tuple[int, int] = (12, 8), 
             start_date: Optional[str] = None, 
             end_date: Optional[str] = None) -> plt.Figure:
        """
        Plot the smoothing results.
        
        Args:
            figsize: Figure size
            start_date: Start date for plotting (YYYY-MM-DD)
            end_date: End date for plotting (YYYY-MM-DD)
            
        Returns:
            Matplotlib figure
        """
        if self.df_out is None:
            raise ValueError("Must call fit() before plotting")
        
        # Filter data by date if specified
        df_plot = self.df_out.copy()
        if start_date:
            df_plot = df_plot[df_plot['fact_date'] >= start_date]
        if end_date:
            df_plot = df_plot[df_plot['fact_date'] <= end_date]
        
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=figsize, sharex=True)
        
        # Plot 1: Fat mass smoothing
        ax1.scatter(df_plot['fact_date'], df_plot['fat_mass_obs'], 
                   alpha=0.6, s=20, color='lightblue', label='Observed')
        ax1.plot(df_plot['fact_date'], df_plot['fat_mass_smooth'], 
                linewidth=2, color='darkblue', label='Smoothed Fat')
        
        # Add hydration component as offset band around zero
        ax1.fill_between(df_plot['fact_date'], 0, df_plot['hydration_component'],
                        alpha=0.25, color='orange', label='Hydration (carb-driven)', step='mid')
        
        # Add subtitle with parameters
        k_h = self.params.get('k_h', 0)
        mean_resid = self.params.get('mean_abs_residual', 0)
        ax1.set_ylabel('Fat Mass (kg)')
        ax1.set_title(f'Physiological Fat Mass Smoothing\nk_h = {k_h:.4f}, mean|resid| = {mean_resid:.3f} kg')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # Plot 2: Residuals
        ax2.scatter(df_plot['fact_date'], df_plot['residuals'], 
                   alpha=0.6, s=20, color='red', label='Residuals')
        ax2.axhline(y=0, color='black', linestyle='--', alpha=0.5)
        ax2.set_ylabel('Residuals (kg)')
        ax2.set_xlabel('Date')
        ax2.set_title('Residuals (Observed - Model)')
        ax2.set_ylim(-2, 2)  # Set y-limits for real data
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        # Format x-axis
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        ax1.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
        plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45)
        
        plt.tight_layout()
        return fig
    
    def compare_loss(self, start_date: str, end_date: str) -> Dict[str, float]:
        """
        Compare smoothed fat mass change with cumulative calorie deficit.
        
        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            
        Returns:
            Dictionary with comparison metrics
        """
        if self.df_out is None:
            raise ValueError("Must call fit() before comparing loss")
        
        # Filter data by date
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        # Ensure fact_date is datetime
        fact_date_dt = pd.to_datetime(self.df_out['fact_date'])
        mask = ((fact_date_dt >= start_dt) & (fact_date_dt <= end_dt))
        df_period = self.df_out[mask].copy()
        
        if len(df_period) < 2:
            raise ValueError(f"Insufficient data in period {start_date} to {end_date}")
        
        # Calculate fat mass change
        fat_start = df_period['fat_mass_smooth'].iloc[0]
        fat_end = df_period['fat_mass_smooth'].iloc[-1]
        fat_change = fat_end - fat_start
        
        # Calculate cumulative calorie deficit (assuming net_kcal is available)
        if 'net_kcal' in df_period.columns:
            cumulative_deficit = -df_period['net_kcal'].sum()  # Negative net_kcal = deficit
        else:
            # Estimate from intake and workout if available
            if 'intake_kcal' in df_period.columns and 'workout_kcal' in df_period.columns:
                net_kcal = df_period['intake_kcal'] - df_period['workout_kcal']
                cumulative_deficit = -net_kcal.sum()
            else:
                cumulative_deficit = np.nan
        
        # Calculate expected fat change from calorie deficit
        # Assuming 7700 kcal per kg fat
        kcal_per_kg_fat = 7700
        expected_fat_change = cumulative_deficit / kcal_per_kg_fat if not np.isnan(cumulative_deficit) else np.nan
        
        # Calculate agreement
        if not np.isnan(expected_fat_change) and expected_fat_change != 0:
            agreement_ratio = fat_change / expected_fat_change
        else:
            agreement_ratio = np.nan
        
        results = {
            'period_start': start_date,
            'period_end': end_date,
            'fat_change_kg': fat_change,
            'cumulative_deficit_kcal': cumulative_deficit,
            'expected_fat_change_kg': expected_fat_change,
            'agreement_ratio': agreement_ratio,
            'days': len(df_period)
        }
        
        logger.info(f"Period {start_date} to {end_date}:")
        logger.info(f"  Fat change: {fat_change:.3f} kg")
        logger.info(f"  Cumulative deficit: {cumulative_deficit:.0f} kcal")
        logger.info(f"  Expected fat change: {expected_fat_change:.3f} kg")
        logger.info(f"  Agreement ratio: {agreement_ratio:.3f}")
        
        return results
    
    def get_results(self) -> pd.DataFrame:
        """
        Get the smoothing results.
        
        Returns:
            DataFrame with smoothing results
        """
        if self.df_out is None:
            raise ValueError("Must call fit() before getting results")
        
        return self.df_out.copy()
    
    def get_params(self) -> Dict:
        """
        Get the fitted parameters.
        
        Returns:
            Dictionary of fitted parameters
        """
        return self.params.copy()


def demo():
    """Demonstrate the PhysioSmoother with synthetic data."""
    import matplotlib.pyplot as plt
    
    # Create synthetic data
    np.random.seed(42)
    dates = pd.date_range('2023-01-01', '2023-12-31', freq='D')
    n = len(dates)
    
    # True fat mass trend (slow)
    fat_trend = 20 + 0.01 * np.arange(n) + 2 * np.sin(2 * np.pi * np.arange(n) / 365)
    
    # Hydration component (fast fluctuations)
    carbs = 200 + 50 * np.random.randn(n)
    hydration = 0.5 * np.sin(2 * np.pi * np.arange(n) / 7) + 0.3 * np.random.randn(n)
    
    # Observed fat mass
    fat_mass_obs = fat_trend + 0.002 * hydration + 0.1 * np.random.randn(n)
    
    # Create DataFrame
    df = pd.DataFrame({
        'fact_date': dates,
        'fat_mass_kg': fat_mass_obs,
        'carbs_g': carbs,
        'alcohol_g': 10 * np.random.rand(n)  # Random alcohol
    })
    
    # Fit smoother
    smoother = PhysioSmoother()
    smoother.fit(df)
    
    # Plot results
    fig = smoother.plot()
    plt.show()
    
    # Print parameters
    params = smoother.get_params()
    print(f"Fitted k_h: {params['k_h']:.6f}")
    print(f"Mean absolute residual: {params['mean_abs_residual']:.4f}")
    print(f"Converged: {params['converged']}")


if __name__ == '__main__':
    demo()
