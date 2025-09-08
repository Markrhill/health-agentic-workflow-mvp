# tools/p1_residuals.py
import os
import math
import numpy as np
import pandas as pd
from pathlib import Path

import matplotlib.pyplot as plt
from sqlalchemy import create_engine
from dotenv import load_dotenv

# -----------------------------
# Config
# -----------------------------
# Fitted parameters (update here if you re-fit)
M_KCAL_PER_DAY = 1630.0   # maintenance kcal/day
C_COMPENSATION = 0.19     # fraction of workout kcal "eaten back"
ALPHA_KCAL_PER_KG = 9800.0  # energy per kg fat

FIG_DIR = Path("figures")
DATA_OUT = Path("data/p1_residuals_summary.csv")
FIG_DIR.mkdir(parents=True, exist_ok=True)
DATA_OUT.parent.mkdir(parents=True, exist_ok=True)

# -----------------------------
# DB connection
# -----------------------------
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set in environment (.env).")

engine = create_engine(DATABASE_URL)

# -----------------------------
# Load windowed training data
# -----------------------------
# Expecting columns:
# start_date, end_date, days, delta_fm_kg, intake_kcal_sum, workout_kcal_sum, is_7d (boolean)
sql = """
    SELECT
      start_date,
      end_date,
      days,
      delta_fm_kg,
      intake_kcal_sum,
      workout_kcal_sum,
      is_7d
    FROM p1_train_windows_flex7
    WHERE is_7d = TRUE
"""
df = pd.read_sql(sql, engine)

if df.empty:
    raise RuntimeError("No rows returned from p1_train_windows_flex7 (is_7d=TRUE).")

# -----------------------------
# Model prediction & residuals
# -----------------------------
# Model: ΔFM_pred_kg = (ΣIntake - (1 - C)*ΣWorkout - M*days) / α
df["pred_delta_fm_kg"] = (
    (df["intake_kcal_sum"]
     - (1.0 - C_COMPENSATION) * df["workout_kcal_sum"]
     - M_KCAL_PER_DAY * df["days"]) / ALPHA_KCAL_PER_KG
)

# Residual definition (keep consistent with prior runs):
# residual = pred - actual  (negative mean => model overpredicts fat loss)
df["residual_kg"] = df["pred_delta_fm_kg"] - df["delta_fm_kg"]

# -----------------------------
# Summary statistics
# -----------------------------
mean_res = df["residual_kg"].mean()
std_res  = df["residual_kg"].std(ddof=1)
rng_min  = df["residual_kg"].min()
rng_max  = df["residual_kg"].max()
n = len(df)

summary = pd.DataFrame(
    {
        "mean_residual_kg": [mean_res],
        "std_residual_kg": [std_res],
        "min_residual_kg": [rng_min],
        "max_residual_kg": [rng_max],
        "n_windows": [n],
        "M_kcal_per_day": [M_KCAL_PER_DAY],
        "C_compensation": [C_COMPENSATION],
        "alpha_kcal_per_kg": [ALPHA_KCAL_PER_KG],
    }
)
summary.to_csv(DATA_OUT, index=False)

print("Residual Summary:")
print(summary.to_string(index=False))

# -----------------------------
# Quick diagnostic plots
# -----------------------------
# 1) Histogram of residuals
plt.figure()
plt.hist(df["residual_kg"], bins=40)
plt.title("Residuals (pred - actual) [kg]")
plt.xlabel("kg")
plt.ylabel("count")
plt.axvline(0.0, linestyle="--")
plt.tight_layout()
plt.savefig(FIG_DIR / "p1_residuals_hist.png", dpi=160)

# 2) Residuals vs. predicted fat change
plt.figure()
plt.scatter(df["pred_delta_fm_kg"], df["residual_kg"], s=8)
plt.title("Residuals vs Predicted ΔFM (kg)")
plt.xlabel("Predicted ΔFM (kg)")
plt.ylabel("Residual (kg)")
plt.axhline(0.0, linestyle="--")
plt.tight_layout()
plt.savefig(FIG_DIR / "p1_residuals_vs_pred.png", dpi=160)

# 3) Residuals vs. net kcal over window
net_kcal = df["intake_kcal_sum"] - (1.0 - C_COMPENSATION) * df["workout_kcal_sum"] - M_KCAL_PER_DAY * df["days"]
plt.figure()
plt.scatter(net_kcal, df["residual_kg"], s=8)
plt.title("Residuals vs Net kcal (adj for C and M)")
plt.xlabel("Net kcal over 7 days")
plt.ylabel("Residual (kg)")
plt.axhline(0.0, linestyle="--")
plt.tight_layout()
plt.savefig(FIG_DIR / "p1_residuals_vs_netkcal.png", dpi=160)

print("\nSaved:")
print(f"  {DATA_OUT}")
print(f"  {FIG_DIR / 'p1_residuals_hist.png'}")
print(f"  {FIG_DIR / 'p1_residuals_vs_pred.png'}")
print(f"  {FIG_DIR / 'p1_residuals_vs_netkcal.png'}")