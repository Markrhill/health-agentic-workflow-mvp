import os, math, argparse
import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ---- Fast 1D fused-lasso (L2 + TV) via Condat's algorithm ----
# Solves: min_x 0.5*||x - y||_2^2 + lam * TV(x), where TV is L1 of first differences.
# Reference: Condat (2013) "A Direct Algorithm for 1D Total Variation Denoising"
def tv1d_denoise(y: np.ndarray, lam: float) -> np.ndarray:
    if lam <= 0:  # no smoothing
        return y.copy()
    n = y.size
    x = np.empty(n, dtype=float)
    k = k0 = 0
    umin = lam; umax = -lam
    vmin = y[0] - lam; vmax = y[0] + lam
    twolam = 2.0 * lam
    for i in range(1, n):
        val = y[i]
        # lower envelope
        if val + umin < vmin:
            for j in range(k0, k+1): x[j] = vmin
            k0 = k = i - 1
            vmin = val - lam; vmax = val + lam
            umin = lam; umax = -lam
        else:
            umin += val - vmin
            if umin >= lam:
                while k < i - 1:
                    k += 1
                    vmin += (umin - lam) / (k - k0 + 1)
                vmin += (umin - lam) / (i - k0 + 1)
                umin = lam
        # upper envelope
        if val + umax > vmax:
            for j in range(k0, k+1): x[j] = vmax
            k0 = k = i - 1
            vmin = val - lam; vmax = val + lam
            umin = lam; umax = -lam
        else:
            umax += val - vmax
            if umax <= -lam:
                while k < i - 1:
                    k += 1
                    vmax += (umax + lam) / (k - k0 + 1)
                vmax += (umax + lam) / (i - k0 + 1)
                umax = -lam
        if umin >= lam:  # tighten lower
            while k0 <= k:
                x[k0] = vmin; k0 += 1
            k = i - 1; vmin = y[i] - lam; vmax = y[i] + lam
            umin = lam; umax = -lam
        elif umax <= -lam:  # tighten upper
            while k0 <= k:
                x[k0] = vmax; k0 += 1
            k = i - 1; vmin = y[i] - lam; vmax = y[i] + lam
            umin = lam; umax = -lam
    # final projection
    vbar = (vmin + vmax) / 2.0
    for j in range(k0, n):
        x[j] = vbar
    return x

# ---- CLI ----
ap = argparse.ArgumentParser(description="Path A: TV-L1 (fused-lasso) on p1_train_daily")
ap.add_argument("--start", default="2021-01-01")
ap.add_argument("--end",   default="2024-12-31")
ap.add_argument("--hampel", action="store_true", default=True, help="Enable gentle Hampel pre-clean")
ap.add_argument("--win", type=int, default=7, help="Hampel window (days)")
ap.add_argument("--tau", type=float, default=5.0, help="Hampel MAD multiplier")
ap.add_argument("--cap_rate", type=float, default=0.005, help="Max fraction removed by Hampel")
ap.add_argument("--lambdas", default="0,10,20,40,80,120,160,220,300", help="Comma list (kg units)")
ap.add_argument("--cv_block", default="M", help="Pandas offset alias (M=month) for blocked CV")
args = ap.parse_args()

DB = os.environ.get("DATABASE_URL")
assert DB, "Set DATABASE_URL (e.g., postgresql+psycopg://user:pass@host/db)"
eng = create_engine(DB)

# ---- Load series ----
q = text("""
SELECT fact_date, fat_mass_kg
FROM public.p1_train_daily
WHERE fact_date BETWEEN :s AND :e
ORDER BY fact_date
""")
df = pd.read_sql(q, eng, params={"s": args.start, "e": args.end}, parse_dates=["fact_date"]).set_index("fact_date")
y = df["fat_mass_kg"].astype(float).to_numpy()
n = len(y)
assert n > 60, f"Too few points ({n}) for blocked CV"

# ---- Gentle Hampel (optional, default ON) ----
def gentle_hampel(s: pd.Series, win=7, tau=5.0, cap_rate=0.005):
    med = s.rolling(win, min_periods=1).median()
    abs_dev = (s - med).abs()
    mad = abs_dev.rolling(win, min_periods=1).median().replace(0, np.nan).fillna(abs_dev.median())
    thr = tau * mad
    outliers = abs_dev > thr
    # cap removals
    cap = int(round(cap_rate * len(s)))
    if outliers.sum() > cap and cap > 0:
        # keep only the largest deviations
        keep = abs_dev.sort_values(ascending=False).index[:cap]
        outliers = s.index.to_series().isin(keep)
    return s[~outliers]

if args.hampel:
    s_clean = gentle_hampel(df["fat_mass_kg"], args.win, args.tau, args.cap_rate)
    df = df.loc[s_clean.index]
    y = df["fat_mass_kg"].to_numpy()

# ---- Build calendar-aligned arrays (fill NaN gaps for stable Δ1d/metrics)
full = pd.DataFrame(index=pd.date_range(df.index.min(), df.index.max(), freq="D"))
full["fat_mass_kg"] = df["fat_mass_kg"]
mask_obs = ~full["fat_mass_kg"].isna()
y_full = full["fat_mass_kg"].to_numpy()
idx = np.where(mask_obs)[0]

# ---- CV lambdas ----
lam_grid = [float(v) for v in args.lambdas.split(",")]
# blocked CV splits by month (or args.cv_block)
blocks = full.index.to_series().groupby(full.index.to_period(args.cv_block)).apply(lambda s: (s.min(), s.max()))
splits = []
for (p, (a, b)) in blocks.items():
    aidx = (full.index >= a) & (full.index <= b)
    if aidx.sum() >= 20:  # require minimum points in a block
        splits.append(aidx)

def rmse(a, b):
    m = ~np.isnan(a) & ~np.isnan(b)
    if m.sum() == 0: return np.nan
    return float(np.sqrt(np.mean((a[m] - b[m])**2)))

def fit_eval(lam):
    # fit on training (all but one block), validate on held-out block; average RMSE
    rmses = []
    for hold in splits:
        train_mask = ~hold & mask_obs.values
        val_mask = hold & mask_obs.values
        if train_mask.sum() < 30 or val_mask.sum() < 10:
            continue
        y_train = y_full.copy()
        # keep only observed training points, NaN elsewhere
        y_train[~train_mask] = np.nan
        # fill missing by nearest neighbor for solver stability (doesn't affect val filtering)
        y_fill = pd.Series(y_train).interpolate("nearest", limit_direction="both").to_numpy()
        xhat = tv1d_denoise(y_fill, lam)
        # eval on validation observed points
        rmses.append(rmse(y_full[val_mask], xhat[val_mask]))
    return np.nanmean(rmses) if len(rmses) else np.nan

cv_table = [(lam, fit_eval(lam)) for lam in lam_grid]
cv_table = [t for t in cv_table if not math.isnan(t[1])]
assert cv_table, "CV failed to compute — check data coverage"
lam_best, cv_rmse = min(cv_table, key=lambda t: t[1])

# ---- Final fit on full period ----
# Fill for solver, then denoise
y_fill = pd.Series(y_full).interpolate("nearest", limit_direction="both").to_numpy()
xhat = tv1d_denoise(y_fill, lam_best)
full["fm_tv_l1"] = xhat
full["lambda_best"] = lam_best

# ---- Metrics vs RAW (acceptance gates)
def sd_d1(series):
    d = np.diff(series)
    d = d[~np.isnan(d)]
    return float(np.std(d, ddof=1)) if d.size > 1 else np.nan

def sign_flips_7(series):
    # 7-day endpoints, ignore zeros
    s = pd.Series(series, index=full.index)
    d7 = s - s.shift(7)
    sign = d7.apply(lambda z: 1 if z > 0 else (-1 if z < 0 else 0))
    flips = ((sign != sign.shift(1)) & (sign != 0) & (sign.shift(1) != 0)).sum()
    return int(flips)

raw = full["fat_mass_kg"].to_numpy()
filt = full["fm_tv_l1"].to_numpy()

sd_raw = sd_d1(raw)
sd_filt = sd_d1(filt)
sd_cut_pct = 100.0 * (1 - sd_filt / sd_raw) if sd_raw and not np.isnan(sd_filt) else np.nan

flips_raw = sign_flips_7(raw)
flips_filt = sign_flips_7(filt)
flip_cut_pct = 100.0 * (1 - flips_filt / flips_raw) if flips_raw else np.nan

print(f"[TV-L1] best_lambda={lam_best:.3f}  CV_RMSE={cv_rmse:.4f}")
print(f"[Noise] SD Δ1d raw={sd_raw:.4f}  tvl1={sd_filt:.4f}  cut={sd_cut_pct:.1f}%")
print(f"[Stab ] flips7 raw={flips_raw}  tvl1={flips_filt}  cut={flip_cut_pct:.1f}%")

# ---- Persist to DB ----
out = full.reset_index().rename(columns={"index":"fact_date"})
# keep only dates that were in the original training window
out = out[(out["fact_date"] >= pd.to_datetime(args.start)) & (out["fact_date"] <= pd.to_datetime(args.end))]
out["fat_mass_kg"] = out["fat_mass_kg"].astype(float)
out["fm_tv_l1"] = out["fm_tv_l1"].astype(float)
out["lambda_best"] = out["lambda_best"].astype(float)
out.to_sql("p1_fm_tv_l1_train", eng, if_exists="replace", index=False)
print("saved -> public.p1_fm_tv_l1_train (fact_date, fat_mass_kg, fm_tv_l1, lambda_best)")
