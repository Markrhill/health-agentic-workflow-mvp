from dataclasses import dataclass

import argparse
import json
import os
from datetime import datetime
from typing import Optional

import pandas as pd
try:
    import psycopg
except Exception:  # psycopg may not be installed in all envs
    psycopg = None

KCALS_PER_KG_FAT = 7700.0

@dataclass
class MaintenanceEstimate:
    m_kcal_per_day: float
    comp_c: float  # compensation coefficient used (0.0–0.5 typical)

def estimate_m_from_windows(df, comp_c: float = 0.25) -> MaintenanceEstimate:
    """
    DEPRECATED: prefer estimate_M_from_blocks(...) which removes net_kcal_sum.
    df must have columns: net_kcal_sum, workout_kcal_sum, delta_fm_kg, days (7–9).
    net_kcal_sum = intake_kcal_sum - workout_kcal_sum (uncompensated)
    We apply compensation inside this function.
    """
    adj_net = df["net_kcal_sum"] + comp_c * df["workout_kcal_sum"]
    # m_hat is avg over windows of (adj_net - 7700*ΔFM)/days
    m_hat = ((adj_net - KCALS_PER_KG_FAT * df["delta_fm_kg"]) / df["days"]).mean()
    return MaintenanceEstimate(m_kcal_per_day=float(m_hat), comp_c=comp_c)


def estimate_M_from_blocks(df, comp_c: float = 0.25, kcals_per_kg: float = 9800.0) -> MaintenanceEstimate:
    """
    Estimate maintenance kcal per day from blocks of data.
    df must have columns: intake_kcal_sum, workout_kcal_sum, delta_fm_kg, days.
    kcals_per_kg is the kcal equivalent per kg of fat mass change.
    """
    adj_net = df["intake_kcal_sum"] - (1 - comp_c) * df["workout_kcal_sum"]
    m_hat = ((adj_net - kcals_per_kg * df["delta_fm_kg"]) / df["days"]).mean()
    return MaintenanceEstimate(m_kcal_per_day=float(m_hat), comp_c=comp_c)


# -----------------------------
# Adapter & CLI (audit-preserving)
# -----------------------------

def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Accepts either {intake_sum, workout_sum} or {intake_kcal_sum, workout_kcal_sum}.
    Ensures the latter pair exists. Also ensures 'net_kcal_sum' exists for legacy path.
    """
    out = df.copy()
    if "intake_kcal_sum" not in out.columns and "intake_sum" in out.columns:
        out["intake_kcal_sum"] = out["intake_sum"].astype(float)
    if "workout_kcal_sum" not in out.columns and "workout_sum" in out.columns:
        out["workout_kcal_sum"] = out["workout_sum"].astype(float)
    # Build legacy term if missing
    if "net_kcal_sum" not in out.columns and {
        "intake_kcal_sum",
        "workout_kcal_sum",
    }.issubset(out.columns):
        out["net_kcal_sum"] = out["intake_kcal_sum"] - out["workout_kcal_sum"]
    return out


def run_solver(
    df: pd.DataFrame,
    comp_c: float = 0.19,
    kcals_per_kg: float = 9800.0,
    legacy_comp_c: Optional[float] = None,
) -> dict:
    """Compute both the new (compensation-explicit) estimate and the legacy one.

    Parameters
    ----------
    df : DataFrame with columns: intake_sum/workout_sum (or *_kcal_sum), delta_fm_kg, days
    comp_c : float, exercise compensation coefficient for the new estimator
    kcals_per_kg : float, kcal per kg for the new estimator (alpha)
    legacy_comp_c : float|None; if None, uses comp_c for the legacy path
    """
    legacy_comp_c = comp_c if legacy_comp_c is None else legacy_comp_c
    df = _normalize_columns(df)

    # New, compensation-explicit estimator
    est_v2 = estimate_M_from_blocks(
        df.rename(columns={
            "intake_kcal_sum": "intake_kcal_sum",
            "workout_kcal_sum": "workout_kcal_sum",
        }),
        comp_c=comp_c,
        kcals_per_kg=kcals_per_kg,
    )

    # Legacy estimator (kept for audit/provenance)
    est_legacy = estimate_m_from_windows(df, comp_c=legacy_comp_c)

    # Minimal metadata
    meta = {
        "rows": int(len(df)),
        "min_start": str(df.get("start_date", df.get("end_date", pd.Series([None]))).min()),
        "max_end": str(df.get("end_date", df.get("start_date", pd.Series([None]))).max()),
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }

    return {
        "new": {
            "m_kcal_per_day": est_v2.m_kcal_per_day,
            "comp_c": est_v2.comp_c,
            "kcals_per_kg": kcals_per_kg,
        },
        "legacy": {
            "m_kcal_per_day": est_legacy.m_kcal_per_day,
            "comp_c": est_legacy.comp_c,
            "kcals_per_kg": KCALS_PER_KG_FAT,
        },
        "meta": meta,
    }


def _load_dataframe(dsn: Optional[str], sql: Optional[str], csv_path: Optional[str]) -> pd.DataFrame:
    if csv_path:
        return pd.read_csv(csv_path)
    if dsn and sql:
        if psycopg is None:
            raise RuntimeError("psycopg is not installed; provide --input CSV instead")
        with psycopg.connect(dsn) as conn:
            return pd.read_sql(sql, conn)
    raise RuntimeError("Provide either --input CSV or both --dsn and --sql")


def main():
    parser = argparse.ArgumentParser(description="Estimate maintenance (new + legacy)")
    parser.add_argument("--dsn", help="Postgres DSN", default=os.environ.get("PG_DSN"))
    parser.add_argument(
        "--sql",
        help="SQL to fetch blocks",
        default="select * from public.weekly_blocks_regression",
    )
    parser.add_argument("--input", help="CSV path instead of DSN/SQL", default=None)
    parser.add_argument("--comp-c", type=float, default=0.19, dest="comp_c")
    parser.add_argument("--kcals-per-kg", type=float, default=9800.0, dest="kcals_per_kg")
    parser.add_argument("--legacy-comp-c", type=float, default=None, dest="legacy_comp_c")
    parser.add_argument("--out", help="Output JSON path", default="params_estimate.json")

    args = parser.parse_args()

    df = _load_dataframe(args.dsn, args.sql, args.input)
    result = run_solver(
        df,
        comp_c=args.comp_c,
        kcals_per_kg=args.kcals_per_kg,
        legacy_comp_c=args.legacy_comp_c,
    )

    with open(args.out, "w") as f:
        json.dump(result, f, indent=2)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
