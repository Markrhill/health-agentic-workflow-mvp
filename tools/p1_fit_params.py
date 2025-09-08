import os
import numpy as np, pandas as pd
from pathlib import Path
from math import isfinite
from sqlalchemy import create_engine

# Database connection
DB = os.environ.get("DATABASE_URL")
assert DB, "Set DATABASE_URL in your .env"

eng = create_engine(DB)

# Load the already-built windows view from database
# df must have columns: end_date, days, intake_kcal_sum, workout_kcal_sum, delta_fm_kg
q = """
SELECT 
    end_date,
    days,
    intake_kcal_sum,
    workout_kcal_sum,
    delta_fm_kg
FROM p1_train_windows_flex7 
WHERE is_7d = true
ORDER BY end_date;
"""

df = pd.read_sql(q, eng, parse_dates=["end_date"])
print(f"Loaded {len(df)} training windows from database")

def huber(res, delta=0.5):
    a = np.abs(res)
    return np.where(a <= delta, 0.5*a*a, delta*(a - 0.5*delta))

def objective(M, C, alpha):
    pred = (df.intake_kcal_sum - (1-C)*df.workout_kcal_sum - M*df.days) / alpha
    res = df.delta_fm_kg.values - pred
    return np.nanmean(huber(res))

# coarse → fine grid search (fast, no scipy needed)
def grid_search():
    Ms = np.arange(1400, 2201, 50)       # kcal/day
    Cs = np.arange(0.00, 0.501, 0.05)
    As = np.arange(7000, 9501, 250)      # kcal/kg
    best = (1e9, None)
    for M in Ms:
        for C in Cs:
            for A in As:
                val = objective(M, C, A)
                if isfinite(val) and val < best[0]:
                    best = (val, (M, C, A))
    # local refine
    M0,C0,A0 = best[1]
    Ms = np.arange(M0-100, M0+101, 10)
    Cs = np.arange(max(0,C0-0.08), min(0.5,C0+0.08)+1e-9, 0.01)
    As = np.arange(A0-300, A0+301, 50)
    best = (1e9, None)
    for M in Ms:
        for C in Cs:
            for A in As:
                val = objective(M, C, A)
                if val < best[0]:
                    best = (val, (M, C, A))
    return best

if __name__ == "__main__":
    loss, (M,C,A) = grid_search()
    print(f"Best params: M={M:.0f} kcal/d, C={C:.2f}, α={A:.0f} kcal/kg (Huber loss={loss:.4f})")
