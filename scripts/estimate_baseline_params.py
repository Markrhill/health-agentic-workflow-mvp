import os, sys, numpy as np, pandas as pd, psycopg2
from dataclasses import dataclass

# ========= Reproducibility header =========
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
np.set_printoptions(suppress=True, precision=4)

# ========= Config =========
WINDOW_DAYS = 14
USE_KALMAN_SMOOTHED_FAT = True

# Ridge penalties
LAMBDA_ALPHA = 100.0
LAMBDA_WORKOUT = 50.0
LAMBDA_CONST = 10.0

# Physiological clamps
C_MIN, C_MAX = 0.05, 0.40
BMR_MIN = 1600.0
ALPHA_MIN = 5000.0  # Prevent division by zero
ALPHA_MAX = 50000.0  # Allow "wrong" values if they predict correctly

# ========= Database loader =========
def load_daily_facts(start_date, end_date):
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    query = """
        SELECT 
            fact_date,
            intake_kcal,
            workout_kcal,
            fat_mass_kg,
            fat_free_mass_kg
        FROM daily_facts
        WHERE fact_date BETWEEN %s AND %s
        ORDER BY fact_date
    """
    df = pd.read_sql_query(query, conn, params=(start_date, end_date))
    conn.close()
    df['workout_kcal'] = df['workout_kcal'].fillna(0)
    return df

# ========= BIA noise reduction =========
def robust_clean(series, window=7, k=3.0):
    """Hampel filter: remove outliers > k*MAD from rolling median"""
    s = series.astype(float).copy()
    med = s.rolling(window, center=True, min_periods=1).median()
    mad = (s - med).abs().rolling(window, center=True, min_periods=1).median()
    mad = mad.replace(0, np.nan).ffill().bfill()
    s[(s - med).abs() > k * mad] = np.nan
    return s

@dataclass
class KalmanParams:
    q_process: float   # process variance (kg^2/day)
    r_meas: float      # measurement variance (kg^2)

def estimate_qr(fm: pd.Series) -> KalmanParams:
    """Estimate Kalman parameters from data"""
    d = fm.diff().dropna()
    robust_var_d = np.median(np.abs(d - d.median()))**2 * (np.pi/2)
    w = fm.rolling(7, min_periods=3).std().dropna()
    robust_r = np.median(w)**2
    q = max(1e-5, 0.25 * robust_var_d)
    r = max(1e-4, robust_r)
    return KalmanParams(q_process=q, r_meas=r)

def kalman_smooth_fat(dates: pd.Series, fm_obs: pd.Series, q: float, r: float):
    """RTS smoother for scalar random walk"""
    n = len(fm_obs)
    x_pred = np.zeros(n); P_pred = np.zeros(n)
    x_filt = np.zeros(n); P_filt = np.zeros(n)
    
    first_idx = int(np.where(fm_obs.notna())[0][0])
    x_filt[first_idx] = fm_obs.iloc[first_idx]
    P_filt[first_idx] = 10.0

    # Forward filter
    for t in range(first_idx+1, n):
        x_pred[t] = x_filt[t-1]
        P_pred[t] = P_filt[t-1] + q
        if np.isnan(fm_obs.iloc[t]):
            x_filt[t], P_filt[t] = x_pred[t], P_pred[t]
        else:
            y = fm_obs.iloc[t]
            S = P_pred[t] + r
            K = P_pred[t] / S
            x_filt[t] = x_pred[t] + K * (y - x_pred[t])
            P_filt[t] = (1 - K) * P_pred[t]

    # Backward smoother
    x_smooth = x_filt.copy()
    P_smooth = P_filt.copy()
    for t in range(n-2, first_idx-1, -1):
        C = P_filt[t] / (P_filt[t] + q)
        x_smooth[t] = x_filt[t] + C * (x_smooth[t+1] - x_filt[t])
        P_smooth[t] = P_filt[t] + C * (P_smooth[t+1] - P_filt[t])

    return pd.Series(x_smooth, index=fm_obs.index, name="fat_mass_kg_smooth")

# ========= Window builder =========
def build_windows(df, window_days=14, col_fat="fat_mass_kg"):
    rows = []
    for i in range(len(df) - window_days + 1):
        w = df.iloc[i:i+window_days]
        if (pd.notna(w.iloc[0][col_fat]) and
            pd.notna(w.iloc[-1][col_fat]) and
            w[col_fat].notna().sum() >= 10 and
            w['fat_free_mass_kg'].notna().sum() >= 10):
            rows.append({
                'delta_fm_kg': float(w.iloc[-1][col_fat] - w.iloc[0][col_fat]),
                'intake_sum': float(w['intake_kcal'].sum()),
                'workout_sum': float(w['workout_kcal'].sum()),
                'days': int(window_days)
            })
    return pd.DataFrame(rows)

# ========= Simplified 3-parameter fit =========
def fit_three_param_simple(W: pd.DataFrame,
                          lam_alpha: float, lam_workout: float, lam_const: float,
                          c_bounds=(0.05,0.40), bmr_min=1600.0, alpha_min=5000.0, alpha_max=50000.0):
    """
    Model: intake - α*ΔFM = (1-C)*workout + BMR*days
    Unknowns: [α, (1-C), BMR]
    Takes intake at face value; α absorbs systematic errors
    """
    intake = W['intake_sum'].values
    workout = W['workout_sum'].values
    days = W['days'].values
    delta_fm = W['delta_fm_kg'].values
    
    # Linear system: X @ beta = y
    X = np.column_stack([-delta_fm, workout, days])
    y = intake
    
    # Ridge regression
    XtX = X.T @ X
    Xty = X.T @ y
    Lam = np.diag([lam_alpha, lam_workout, lam_const])
    beta = np.linalg.solve(XtX + Lam, Xty)
    
    alpha_hat, one_minus_C, BMR = beta
    
    # Clamp to physiological bounds
    alpha_hat = float(np.clip(alpha_hat, alpha_min, alpha_max))
    C = float(np.clip(1.0 - one_minus_C, c_bounds[0], c_bounds[1]))
    BMR = float(max(bmr_min, BMR))
    
    # Prediction errors
    delta_fm_pred = (intake - ((1-C)*workout + BMR*days)) / alpha_hat
    err = delta_fm_pred - delta_fm
    
    return dict(
        alpha=alpha_hat,
        C=C, 
        BMR=BMR,
        MAE=float(np.mean(np.abs(err))),
        RMSE=float(np.sqrt(np.mean(err**2))),
        BIAS=float(np.mean(err))
    )

# ========= Main =========
def main():
    print("=== BASELINE FIT (2022 weight loss period: 3/15-12/15) ===")
    df_2024 = load_daily_facts('2022-03-15', '2022-12-15')
    
    # Clean and smooth
    df_2024['fat_mass_kg'] = robust_clean(df_2024['fat_mass_kg'])
    df_2024['fat_free_mass_kg'] = robust_clean(df_2024['fat_free_mass_kg'])
    
    if USE_KALMAN_SMOOTHED_FAT:
        kp = estimate_qr(df_2024['fat_mass_kg'])
        df_2024['fat_mass_kg_smooth'] = kalman_smooth_fat(
            df_2024['fact_date'], df_2024['fat_mass_kg'], kp.q_process, kp.r_meas
        )
        fat_col = "fat_mass_kg_smooth"
        print(f"Kalman smoothing: q={kp.q_process:.6f}, r={kp.r_meas:.6f}")
    else:
        fat_col = "fat_mass_kg"
    
    W_2024 = build_windows(df_2024, WINDOW_DAYS, col_fat=fat_col)
    print(f"2024 windows: {len(W_2024)}")
    
    baseline = fit_three_param_simple(
        W_2024,
        lam_alpha=LAMBDA_ALPHA,
        lam_workout=LAMBDA_WORKOUT,
        lam_const=LAMBDA_CONST,
        c_bounds=(C_MIN, C_MAX),
        bmr_min=BMR_MIN,
        alpha_min=ALPHA_MIN,
        alpha_max=ALPHA_MAX
    )
    
    print(f"\nBaseline Parameters:")
    print(f"  α (kcal/kg)     : {baseline['alpha']:,.0f}")
    print(f"  C (compensation): {baseline['C']:.3f}")
    print(f"  BMR (kcal/day)  : {baseline['BMR']:.0f}")
    print(f"\n2022 Weight Loss Period Fit Quality:")
    print(f"  MAE  : {baseline['MAE']:.3f} kg")
    print(f"  RMSE : {baseline['RMSE']:.3f} kg")
    print(f"  Bias : {baseline['BIAS']:+.3f} kg")
    
    # Validation on 2023 data
    print("\n=== PROSPECTIVE VALIDATION (2023 data) ===")
    df_2025 = load_daily_facts('2023-01-01', '2023-12-31')
    
    df_2025['fat_mass_kg'] = robust_clean(df_2025['fat_mass_kg'])
    df_2025['fat_free_mass_kg'] = robust_clean(df_2025['fat_free_mass_kg'])
    
    if USE_KALMAN_SMOOTHED_FAT:
        kp_2025 = estimate_qr(df_2025['fat_mass_kg'])
        df_2025['fat_mass_kg_smooth'] = kalman_smooth_fat(
            df_2025['fact_date'], df_2025['fat_mass_kg'], kp_2025.q_process, kp_2025.r_meas
        )
    
    W_2025 = build_windows(df_2025, WINDOW_DAYS, col_fat=fat_col)
    print(f"2023 windows: {len(W_2025)}")
    
    # Predict with baseline parameters
    predicted = (
        W_2025['intake_sum'] 
        - (1-baseline['C']) * W_2025['workout_sum']
        - baseline['BMR'] * W_2025['days']
    ) / baseline['alpha']
    
    actual = W_2025['delta_fm_kg'].values
    err_2025 = predicted - actual
    
    mae_2025 = np.mean(np.abs(err_2025))
    rmse_2025 = np.sqrt(np.mean(err_2025**2))
    bias_2025 = np.mean(err_2025)
    
    print(f"\n2023 Prediction Quality:")
    print(f"  MAE  : {mae_2025:.3f} kg")
    print(f"  RMSE : {rmse_2025:.3f} kg")
    print(f"  Bias : {bias_2025:+.3f} kg")
    
    # Decision threshold
    if mae_2025 < 0.4:
        print("\n✓ Parameters are working - proceed with migration")
    elif mae_2025 < 0.6:
        print("\n⚠ Parameters are marginal - consider quarterly updates")
    else:
        print("\n✗ Parameters don't generalize - this may be the Kobayashi Maru")

if __name__ == "__main__":
    main()

