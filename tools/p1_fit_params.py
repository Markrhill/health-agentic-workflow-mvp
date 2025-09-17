import os
import numpy as np, pandas as pd
from pathlib import Path
from math import isfinite
from sqlalchemy import create_engine
import argparse

# Database connection
DB = os.environ.get("DATABASE_URL")
assert DB, "Set DATABASE_URL in your .env"

eng = create_engine(DB)

parser = argparse.ArgumentParser(description="Fit M, C, alpha via coarse→fine grid search on weekly windows")
parser.add_argument("--include-all-days", action="store_true", help="Use all curated windows (7/14/21/28); by default, only is_7d=true")
# Bounds for M
parser.add_argument("--M-min", type=int, default=1400)
parser.add_argument("--M-max", type=int, default=2200)
parser.add_argument("--M-step", type=int, default=50)
# Bounds for C
parser.add_argument("--C-min", type=float, default=0.00)
parser.add_argument("--C-max", type=float, default=0.50)
parser.add_argument("--C-step", type=float, default=0.05)
# Bounds for alpha (kcal/kg)
parser.add_argument("--A-min", type=int, default=7000)
parser.add_argument("--A-max", type=int, default=9500)
parser.add_argument("--A-step", type=int, default=250)
# Huber delta
parser.add_argument("--huber-delta", type=float, default=0.5)
args = parser.parse_args()

base_sql = (
    "SELECT end_date, days, intake_kcal_sum, workout_kcal_sum, delta_fm_kg "
    "FROM p1_train_windows_flex7 "
)
q = base_sql + ("WHERE is_7d = true ORDER BY end_date;" if not args.include_all_days else "ORDER BY end_date;")

df = pd.read_sql(q, eng, parse_dates=["end_date"])
print(f"Loaded {len(df)} training windows from database (include_all_days={args.include_all_days})")

def huber(res, delta):
    a = np.abs(res)
    return np.where(a <= delta, 0.5*a*a, delta*(a - 0.5*delta))

def objective(M, C, alpha):
    pred = (df.intake_kcal_sum - (1-C)*df.workout_kcal_sum - M*df.days) / alpha
    res = df.delta_fm_kg.values - pred
    return np.nanmean(huber(res, delta=args.huber_delta))

def grid_search():
    print(f"DEBUG: Using ranges - M: {args.M_min} to {args.M_max} step {args.M_step}")
    print(f"DEBUG: Using ranges - C: {args.C_min} to {args.C_max} step {args.C_step}")
    print(f"DEBUG: Using ranges - A: {args.A_min} to {args.A_max} step {args.A_step}")
    Ms = np.arange(args.M_min, args.M_max + 1, args.M_step)
    Cs = np.arange(args.C_min, args.C_max + 1e-12, args.C_step)
    As = np.arange(args.A_min, args.A_max + 1, args.A_step)
    best = (1e9, None)
    for M in Ms:
        for C in Cs:
            for A in As:
                val = objective(M, C, A)
                if isfinite(val) and val < best[0]:
                    best = (val, (M, C, A))
    M0, C0, A0 = best[1]
    Ms = np.arange(max(args.M_min, M0 - 100), min(args.M_max, M0 + 100) + 1, 10)
    Cs = np.arange(max(args.C_min, C0 - 0.08), min(args.C_max, C0 + 0.08) + 1e-12, 0.01)
    As = np.arange(max(args.A_min, A0 - 300), min(args.A_max, A0 + 300) + 1, 50)
    best = (1e9, None)
    for M in Ms:
        for C in Cs:
            for A in As:
                val = objective(M, C, A)
                if val < best[0]:
                    best = (val, (M, C, A))
    return best

if __name__ == "__main__":
    loss, (M, C, A) = grid_search()
    print(
        f"Best params: M={M:.0f} kcal/d, C={C:.2f}, α={A:.0f} kcal/kg (Huber loss={loss:.4f})\n"
        f"Bounds used: M[{args.M_min},{args.M_max}] step {args.M_step}; "
        f"C[{args.C_min:.2f},{args.C_max:.2f}] step {args.C_step:.2f}; "
        f"α[{args.A_min},{args.A_max}] step {args.A_step}; "
        f"include_all_days={args.include_all_days}, delta={args.huber_delta}"
    )
