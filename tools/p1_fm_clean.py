# tools/p1_fm_clean.py
import os
import pandas as pd
from sqlalchemy import create_engine, text

DB = os.environ.get("DATABASE_URL")
assert DB, "Set DATABASE_URL in your .env"

eng = create_engine(DB)

# pull daily train/test (from p0_staging split)
q = """
SELECT fact_date, fat_mass_kg
FROM p0_staging
WHERE fact_date BETWEEN DATE '2021-01-01' AND DATE '2025-08-04'
ORDER BY fact_date;
"""
df = pd.read_sql(q, eng, parse_dates=["fact_date"]).set_index("fact_date")

# rolling 7d median & MAD (median absolute deviation)
win = 7
med = df["fat_mass_kg"].rolling(win, center=False, min_periods=1).median()
abs_dev = (df["fat_mass_kg"] - med).abs()
mad = abs_dev.rolling(win, center=False, min_periods=1).median()

# outlier detection using MAD (typically 3*MAD threshold)
threshold = 3 * mad
outliers = abs_dev > threshold

print(f"Found {outliers.sum()} outliers out of {len(df)} records")
print(f"Outlier rate: {outliers.mean():.2%}")

# clean data by removing outliers
df_clean = df[~outliers].copy()

# save cleaned data back to database
# Option 1: Create a new table
df_clean.reset_index().to_sql('p1_fm_clean', eng, if_exists='replace', index=False)

# Option 2: Update existing table with cleaned values
# (uncomment if you want to update the original table)
# df_clean.reset_index().to_sql('p0_staging_clean', eng, if_exists='replace', index=False)

print(f"Cleaned data saved to p1_fm_clean table")
print(f"Original records: {len(df)}")
print(f"Cleaned records: {len(df_clean)}")
print(f"Records removed: {len(df) - len(df_clean)}")

# Optional: Plot the results for visualization
import matplotlib.pyplot as plt

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))

# Original data with outliers highlighted
ax1.plot(df.index, df['fat_mass_kg'], 'b-', alpha=0.7, label='Original')
ax1.scatter(df[outliers].index, df[outliers]['fat_mass_kg'], 
           color='red', s=20, alpha=0.8, label='Outliers')
ax1.plot(df.index, med, 'g--', alpha=0.8, label='Rolling Median')
ax1.fill_between(df.index, med - threshold, med + threshold, 
                alpha=0.2, color='green', label='MAD Threshold')
ax1.set_title('Fat Mass Data with Outlier Detection')
ax1.set_ylabel('Fat Mass (kg)')
ax1.legend()
ax1.grid(True, alpha=0.3)

# Cleaned data
ax2.plot(df_clean.index, df_clean['fat_mass_kg'], 'b-', alpha=0.7)
ax2.set_title('Cleaned Fat Mass Data')
ax2.set_xlabel('Date')
ax2.set_ylabel('Fat Mass (kg)')
ax2.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig('fat_mass_cleaning_results.png', dpi=300, bbox_inches='tight')
plt.show()

print("Visualization saved as 'fat_mass_cleaning_results.png'")
