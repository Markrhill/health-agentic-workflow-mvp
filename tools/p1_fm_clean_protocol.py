# tools/p1_fm_clean_protocol.py
import os, argparse
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ---- CLI ----
ap = argparse.ArgumentParser(description="Gentle Hampel clean for protocol series")
ap.add_argument("--relation", default="public.p1_train_daily",
                help="Source relation (public.p1_train_daily | public.p1_test_daily)")
ap.add_argument("--start", default="2021-01-01", help="Start date (YYYY-MM-DD)")
ap.add_argument("--end",   default="2024-12-31", help="End date (YYYY-MM-DD), use 2025-12-31 for test")
ap.add_argument("--win",   type=int, default=7,  help="Rolling window (days)")
ap.add_argument("--tau",   type=float, default=5.0, help="MAD threshold multiplier")
ap.add_argument("--cap_rate", type=float, default=0.005, help="Max fraction to drop (e.g., 0.005 = 0.5%)")
args = ap.parse_args()

DB = os.environ.get("DATABASE_URL")
assert DB, "Set DATABASE_URL in your .env (e.g., export DATABASE_URL=postgresql+psycopg://user:pass@host/db)"

eng = create_engine(DB)

# ---- Load protocol series ----
q = text(f"""
SELECT fact_date, fat_mass_kg
FROM {args.relation}
WHERE fact_date BETWEEN :start AND :end
  AND fat_mass_kg IS NOT NULL
ORDER BY fact_date
""")
df = pd.read_sql(q, eng, params={"start": args.start, "end": args.end}, parse_dates=["fact_date"]).set_index("fact_date")
n0 = len(df)
assert n0 > 0, f"No rows from {args.relation} in [{args.start}, {args.end}]"

# ---- Gentle Hampel ----
win = args.win
tau = args.tau
med = df["fat_mass_kg"].rolling(win, center=False, min_periods=1).median()
abs_dev = (df["fat_mass_kg"] - med).abs()
mad = abs_dev.rolling(win, center=False, min_periods=1).median()

threshold = tau * mad
outliers = abs_dev > threshold
n_out = int(outliers.sum())

# cap removals
cap = int(max(0, round(args.cap_rate * n0)))
if n_out > cap and cap > 0:
    # keep only the largest 'cap' deviations marked as outliers
    order = abs_dev.sort_values(ascending=False)
    top_idx = set(order.index[:cap])
    outliers = df.index.to_series().apply(lambda t: t in top_idx)
    n_out = cap

df_clean = df[~outliers].copy()
n1 = len(df_clean)

# ---- Persist (separate table) ----
# choose target name based on relation (train vs test)
target = "p1_fm_clean_protocol" if args.relation.endswith("p1_train_daily") else "p1_fm_clean_protocol_test"
df_clean.reset_index().to_sql(target, eng, if_exists="replace", index=False)

print(f"[protocol clean] relation={args.relation}")
print(f" window={win}d  tau={tau}  cap_rate={args.cap_rate:.3%}  cap={cap}")
print(f" n_original={n0}  n_removed={n0-n1}  outlier_rate={((n0-n1)/n0):.2%}")
print(f" saved -> public.{target}")

# ---- Optional plot ----
if os.getenv("PLOT", "0") == "1":
    import matplotlib.pyplot as plt
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    ax1.plot(df.index, df['fat_mass_kg'], 'b-', alpha=0.6, label='Original')
    ax1.scatter(df[outliers].index, df[outliers]['fat_mass_kg'], color='red', s=12, alpha=0.9, label='Outliers')
    ax1.plot(df.index, med, 'g--', alpha=0.8, label='Rolling Median')
    ax1.fill_between(df.index, (med - threshold), (med + threshold), color='green', alpha=0.15, label='MAD band')
    ax1.set_title('Protocol series with Hampel outliers')
    ax1.legend(loc='upper left'); ax1.grid(alpha=0.3)

    ax2.plot(df_clean.index, df_clean['fat_mass_kg'], 'b-', alpha=0.8)
    ax2.set_title('Cleaned protocol series'); ax2.grid(alpha=0.3)
    plt.tight_layout()
    plt.show()
