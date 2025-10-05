#!/usr/bin/env python3
"""
Backtesting Framework for Metabolic Parameter Calibration

Evaluates rolling parameter estimation across training years 2021-2024
with forward-looking validation on subsequent year's data.
"""

import pandas as pd
import numpy as np
from sklearn.linear_model import HuberRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_squared_error, mean_absolute_error
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path

# Configuration
DATA_PATH = 'data/parameter_estimation/biweekly_windows_2025-10-02_v1.1.csv'
OUTPUT_PATH = 'data/parameter_estimation/backtest_results_2025-10-02.csv'
FIGURES_PATH = 'figures'

# Literature baseline parameters
ALPHA_LITERATURE = 9675  # kcal/kg
C_LITERATURE = 0.20  # compensation factor

def katch_mcardle_bmr(lbm_kg):
    """Katch-McArdle BMR formula: 370 + 21.6 × LBM"""
    return 370 + 21.6 * lbm_kg

def fit_parameters(train_df):
    """
    Fit 3 parameters using Huber regression.
    
    Model: y_deficit = 14 × bmr_apparent - c_apparent × total_workout_kcal
    
    Returns: dict with alpha_apparent, bmr_apparent, c_apparent
    """
    y_train = train_df['y_deficit'].values
    
    # Features: [intercept, workout]
    X_train = np.column_stack([
        np.ones(len(train_df)),
        train_df['total_workout_kcal'].values
    ])
    
    # Standardize features (except intercept)
    scaler = StandardScaler()
    X_train_scaled = X_train.copy()
    X_train_scaled[:, 1:] = scaler.fit_transform(X_train[:, 1:])
    
    # Fit Huber regressor
    huber = HuberRegressor(epsilon=1.35, alpha=1e-3, fit_intercept=False)
    huber.fit(X_train_scaled, y_train)
    
    # Unscale coefficients
    beta = huber.coef_.copy()
    beta[1:] = beta[1:] / scaler.scale_
    
    # Extract parameters
    bmr_apparent = beta[0] / 14  # Divide by days
    c_apparent = -beta[1]  # Negative because compensation reduces y_deficit
    
    # Calculate apparent alpha from residuals
    y_pred = X_train @ beta
    predicted_delta_fm = (train_df['total_intake_kcal'].values - y_pred) / ALPHA_LITERATURE
    residuals_fm = train_df['delta_fm_kg'].values - predicted_delta_fm
    
    # Fit alpha to minimize fat mass prediction error
    # delta_fm = (intake - y_deficit) / alpha
    energy_surplus = train_df['total_intake_kcal'].values - y_pred
    actual_delta_fm = train_df['delta_fm_kg'].values
    
    # alpha = energy_surplus / delta_fm (weighted average, excluding near-zero changes)
    mask = np.abs(actual_delta_fm) > 0.05  # Exclude maintenance windows
    if mask.sum() > 5:
        alpha_apparent = np.median(energy_surplus[mask] / actual_delta_fm[mask])
    else:
        alpha_apparent = ALPHA_LITERATURE
    
    return {
        'alpha_apparent': alpha_apparent,
        'bmr_apparent': bmr_apparent,
        'c_apparent': c_apparent,
        'scaler': scaler,
        'huber': huber
    }

def predict_with_fitted(test_df, params):
    """Predict delta_fm using fitted parameters"""
    bmr = params['bmr_apparent']
    c = params['c_apparent']
    alpha = params['alpha_apparent']
    
    # Predict y_deficit
    y_pred = 14 * bmr - c * test_df['total_workout_kcal'].values
    
    # Predict delta_fm
    predicted_delta_fm = (test_df['total_intake_kcal'].values - y_pred) / alpha
    
    return predicted_delta_fm

def predict_with_literature(test_df):
    """Predict delta_fm using literature parameters"""
    bmr = katch_mcardle_bmr(test_df['lbm_avg_kg'].values)
    c = C_LITERATURE
    alpha = ALPHA_LITERATURE
    
    # Predict y_deficit
    y_pred = 14 * bmr - c * test_df['total_workout_kcal'].values
    
    # Predict delta_fm
    predicted_delta_fm = (test_df['total_intake_kcal'].values - y_pred) / alpha
    
    return predicted_delta_fm

def calculate_metrics(actual, predicted):
    """Calculate prediction metrics"""
    rmse = np.sqrt(mean_squared_error(actual, predicted))
    mae = mean_absolute_error(actual, predicted)
    bias = np.mean(predicted - actual)  # Positive = over-prediction
    
    return {'rmse': rmse, 'mae': mae, 'bias': bias}

def backtest_single_year(df, train_year, test_year):
    """
    Train on train_year data, test on test_year data.
    
    Returns: dict with parameters and metrics
    """
    # Filter data
    train_df = df[df['window_start'].str.startswith(str(train_year))].copy()
    test_df = df[df['window_start'].str.startswith(str(test_year))].copy()
    
    if len(train_df) < 5 or len(test_df) < 1:
        return None
    
    # Fit parameters
    params = fit_parameters(train_df)
    
    # Predictions with fitted parameters
    pred_fitted = predict_with_fitted(test_df, params)
    metrics_fitted = calculate_metrics(test_df['delta_fm_kg'].values, pred_fitted)
    
    # Predictions with literature parameters
    pred_literature = predict_with_literature(test_df)
    metrics_literature = calculate_metrics(test_df['delta_fm_kg'].values, pred_literature)
    
    # Calculate improvement
    improvement_rmse = (metrics_literature['rmse'] - metrics_fitted['rmse']) / metrics_literature['rmse'] * 100
    improvement_mae = (metrics_literature['mae'] - metrics_fitted['mae']) / metrics_literature['mae'] * 100
    
    return {
        'train_year': train_year,
        'test_year': test_year,
        'n_train': len(train_df),
        'n_test': len(test_df),
        'alpha_apparent': params['alpha_apparent'],
        'bmr_apparent': params['bmr_apparent'],
        'c_apparent': params['c_apparent'],
        'rmse_fitted': metrics_fitted['rmse'],
        'mae_fitted': metrics_fitted['mae'],
        'bias_fitted': metrics_fitted['bias'],
        'rmse_literature': metrics_literature['rmse'],
        'mae_literature': metrics_literature['mae'],
        'bias_literature': metrics_literature['bias'],
        'improvement_rmse_pct': improvement_rmse,
        'improvement_mae_pct': improvement_mae,
        'pred_fitted': pred_fitted,
        'pred_literature': pred_literature,
        'actual': test_df['delta_fm_kg'].values,
        'test_windows': test_df['window_start'].values
    }

def run_backtest():
    """Run full backtest across all years"""
    print("=" * 80)
    print("METABOLIC PARAMETER BACKTESTING FRAMEWORK")
    print("=" * 80)
    
    # Load data
    df = pd.read_csv(DATA_PATH)
    df['year'] = pd.to_datetime(df['window_start']).dt.year
    
    print(f"\nData loaded: {len(df)} windows")
    print(f"Years: {df['year'].min()} - {df['year'].max()}")
    print(f"Train/Test split: {(df['dataset_split']=='TRAIN').sum()} train, {(df['dataset_split']=='TEST').sum()} test")
    
    # Run backtest for each train/test combination
    results = []
    train_years = [2021, 2022, 2023, 2024]
    
    print("\n" + "-" * 80)
    print("RUNNING BACKTESTS")
    print("-" * 80)
    
    for train_year in train_years:
        for test_year in range(train_year + 1, 2026):
            result = backtest_single_year(df, train_year, test_year)
            if result:
                results.append(result)
                print(f"\nTrain {train_year} → Test {test_year}:")
                print(f"  Fitted:     α={result['alpha_apparent']:,.0f}, BMR={result['bmr_apparent']:.0f}, c={result['c_apparent']:.3f}")
                print(f"  Metrics:    RMSE={result['rmse_fitted']:.3f} kg, MAE={result['mae_fitted']:.3f} kg, Bias={result['bias_fitted']:+.3f} kg")
                print(f"  Literature: RMSE={result['rmse_literature']:.3f} kg, MAE={result['mae_literature']:.3f} kg, Bias={result['bias_literature']:+.3f} kg")
                print(f"  Improvement: RMSE {result['improvement_rmse_pct']:+.1f}%, MAE {result['improvement_mae_pct']:+.1f}%")
    
    # Save results
    results_df = pd.DataFrame([{k: v for k, v in r.items() if not isinstance(v, np.ndarray)} for r in results])
    results_df.to_csv(OUTPUT_PATH, index=False)
    print(f"\n✓ Results saved to: {OUTPUT_PATH}")
    
    # Create visualizations
    create_visualizations(results_df, results)
    
    return results_df, results

def create_visualizations(results_df, full_results):
    """Create diagnostic visualizations"""
    Path(FIGURES_PATH).mkdir(exist_ok=True)
    
    # 1. Parameter stability across train years (same-year+1 test)
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))
    
    # Filter to consecutive year tests
    consecutive = results_df[results_df['test_year'] == results_df['train_year'] + 1]
    
    if len(consecutive) > 0:
        axes[0].plot(consecutive['train_year'], consecutive['alpha_apparent'], 'o-', linewidth=2, markersize=8)
        axes[0].axhline(ALPHA_LITERATURE, color='red', linestyle='--', label='Literature')
        axes[0].set_xlabel('Training Year')
        axes[0].set_ylabel('α (kcal/kg)')
        axes[0].set_title('Apparent Energy Density')
        axes[0].legend()
        axes[0].grid(True, alpha=0.3)
        
        axes[1].plot(consecutive['train_year'], consecutive['bmr_apparent'], 'o-', linewidth=2, markersize=8)
        axes[1].axhline(370 + 21.6 * 72, color='red', linestyle='--', label='Katch-McArdle (72kg LBM)')
        axes[1].set_xlabel('Training Year')
        axes[1].set_ylabel('BMR (kcal/day)')
        axes[1].set_title('Apparent Basal Metabolic Rate')
        axes[1].legend()
        axes[1].grid(True, alpha=0.3)
        
        axes[2].plot(consecutive['train_year'], consecutive['c_apparent'], 'o-', linewidth=2, markersize=8)
        axes[2].axhline(C_LITERATURE, color='red', linestyle='--', label='Literature')
        axes[2].set_xlabel('Training Year')
        axes[2].set_ylabel('Compensation Factor')
        axes[2].set_title('Exercise Compensation')
        axes[2].legend()
        axes[2].grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(f'{FIGURES_PATH}/backtest_parameter_stability.png', dpi=150, bbox_inches='tight')
    print(f"✓ Saved: {FIGURES_PATH}/backtest_parameter_stability.png")
    plt.close()
    
    # 2. Prediction error comparison
    fig, ax = plt.subplots(figsize=(10, 6))
    
    x = np.arange(len(results_df))
    width = 0.35
    
    ax.bar(x - width/2, results_df['mae_fitted'], width, label='Fitted', alpha=0.8)
    ax.bar(x + width/2, results_df['mae_literature'], width, label='Literature', alpha=0.8)
    
    ax.set_xlabel('Train → Test Year')
    ax.set_ylabel('MAE (kg per 14 days)')
    ax.set_title('Prediction Error: Fitted vs Literature Parameters')
    ax.set_xticks(x)
    ax.set_xticklabels([f"{r['train_year']}→{r['test_year']}" for _, r in results_df.iterrows()], rotation=45)
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')
    
    plt.tight_layout()
    plt.savefig(f'{FIGURES_PATH}/backtest_error_comparison.png', dpi=150, bbox_inches='tight')
    print(f"✓ Saved: {FIGURES_PATH}/backtest_error_comparison.png")
    plt.close()
    
    # 3. Actual vs Predicted scatter plots
    n_results = len(full_results)
    ncols = min(3, n_results)
    nrows = (n_results + ncols - 1) // ncols
    
    fig, axes = plt.subplots(nrows, ncols, figsize=(5*ncols, 5*nrows))
    if nrows == 1 and ncols == 1:
        axes = np.array([axes])
    axes = axes.flatten()
    
    for idx, result in enumerate(full_results[:len(axes)]):
        ax = axes[idx]
        
        actual = result['actual']
        pred_fitted = result['pred_fitted']
        pred_lit = result['pred_literature']
        
        # Plot
        ax.scatter(actual, pred_fitted, alpha=0.6, s=80, label=f"Fitted (MAE={result['mae_fitted']:.3f})")
        ax.scatter(actual, pred_lit, alpha=0.6, s=80, marker='x', label=f"Literature (MAE={result['mae_literature']:.3f})")
        
        # Perfect prediction line
        lim = [min(actual.min(), pred_fitted.min(), pred_lit.min()) - 0.5,
               max(actual.max(), pred_fitted.max(), pred_lit.max()) + 0.5]
        ax.plot(lim, lim, 'k--', alpha=0.3, linewidth=1)
        
        ax.set_xlabel('Actual ΔFM (kg)')
        ax.set_ylabel('Predicted ΔFM (kg)')
        ax.set_title(f"Train {result['train_year']} → Test {result['test_year']}")
        ax.legend()
        ax.grid(True, alpha=0.3)
    
    # Hide unused subplots
    for idx in range(len(full_results), len(axes)):
        axes[idx].axis('off')
    
    plt.tight_layout()
    plt.savefig(f'{FIGURES_PATH}/backtest_predictions_scatter.png', dpi=150, bbox_inches='tight')
    print(f"✓ Saved: {FIGURES_PATH}/backtest_predictions_scatter.png")
    plt.close()

if __name__ == '__main__':
    results_df, results = run_backtest()
    
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    
    print(f"\nAverage improvement over literature:")
    print(f"  RMSE: {results_df['improvement_rmse_pct'].mean():+.1f}%")
    print(f"  MAE:  {results_df['improvement_mae_pct'].mean():+.1f}%")
    
    print(f"\nParameter ranges (consecutive year tests):")
    consecutive = results_df[results_df['test_year'] == results_df['train_year'] + 1]
    if len(consecutive) > 0:
        print(f"  α: {consecutive['alpha_apparent'].min():,.0f} - {consecutive['alpha_apparent'].max():,.0f} kcal/kg")
        print(f"  BMR: {consecutive['bmr_apparent'].min():.0f} - {consecutive['bmr_apparent'].max():.0f} kcal/day")
        print(f"  c: {consecutive['c_apparent'].min():.3f} - {consecutive['c_apparent'].max():.3f}")
    
    print("\n" + "=" * 80)

