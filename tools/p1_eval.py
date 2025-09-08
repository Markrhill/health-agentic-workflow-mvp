#!/usr/bin/env python3
from __future__ import annotations
import os, json, math, pathlib
import yaml
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sqlalchemy import create_engine, text
from tools.p1_model import predict_dfm, residuals, mae, rmse

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
FIGS = ROOT / "figures"
CFG  = ROOT / "config" / "p1_params.yaml"

DATA.mkdir(exist_ok=True)
FIGS.mkdir(exist_ok=True)

def load_cfg():
    with open(CFG, "r") as f:
        cfg = yaml.safe_load(f)
    # env overrides
    db = cfg.get("db", {})
    db["password"] = os.getenv("P1_DB_PASSWORD", db.get("password", ""))
    cfg["db"] = db
    return cfg

def pg_engine(cfg):
    db = cfg["db"]
    url = (
        f"postgresql+psycopg2://{db['user']}:{db['password']}@{db['host']}:"
        f"{db['port']}/{db['database']}?sslmode={db.get('sslmode','disable')}"
    )
    return create_engine(url)

def find_view(engine, preferred: str, fallback: str | None = None) -> str:
    with engine.connect() as con:
        q = text("""
          select table_schema, table_name
          from information_schema.views
          where (table_schema, table_name) in (
            ('public', :preferred){fallback_clause}
          )
        """.replace("{fallback_clause}",
                    "" if not fallback else ",('public', :fallback)"))
        params = {"preferred": preferred}
        if fallback: params["fallback"] = fallback
        df = pd.read_sql(q, con, params=params)
    if not df.empty:
        # prefer the first row which is ordered as specified
        return df.iloc[0]["table_name"]
    raise RuntimeError(
        f"Neither view found: {preferred}" + (f", {fallback}" if fallback else "")
    )

def load_windows(engine, view_name: str) -> pd.DataFrame:
    cols = ["start_date","end_date","days",
            "delta_fm_kg","intake_kcal_sum","workout_kcal_sum",
            "is_7d","is_8d","is_9d"]
    with engine.connect() as con:
        df = pd.read_sql(text(f"select {', '.join(cols)} from {view_name} order by end_date"),
                         con, parse_dates=["start_date","end_date"])
    return df

def leakage_check(train: pd.DataFrame, test: pd.DataFrame) -> dict:
    # no end_date overlap allowed between train and test windows
    overlap = set(pd.to_datetime(train["end_date"]).dt.date) & \
              set(pd.to_datetime(test["end_date"]).dt.date)
    return {"overlap_count": len(overlap),
            "ok": len(overlap) == 0}

def metrics_block(resid: np.ndarray) -> dict:
    return {
        "n": int(resid.size),
        "bias_mean": float(np.mean(resid)),
        "median_resid": float(np.median(resid)),
        "mae": mae(resid),
        "rmse": rmse(resid),
        "p50_abs": float(np.percentile(np.abs(resid), 50)),
        "p80_abs": float(np.percentile(np.abs(resid), 80)),
        "within_0p5kg": float(np.mean(np.abs(resid) <= 0.5)),
        "within_1p0kg": float(np.mean(np.abs(resid) <= 1.0)),
        "min": float(np.min(resid)),
        "max": float(np.max(resid)),
    }

def spider(ax, labels, values, title):
    angles = np.linspace(0, 2*np.pi, len(labels), endpoint=False).tolist()
    values = values + values[:1]
    angles = angles + angles[:1]
    ax.plot(angles, values)
    ax.fill(angles, values, alpha=0.1)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels)
    ax.set_title(title)

def main():
    cfg = load_cfg()
    m  = float(cfg["m_kcal_per_day"])
    c  = float(cfg["compensation_c"])
    a  = float(cfg["alpha_kcal_per_kg"])
    wd = int(cfg["window_days"])

    eng = pg_engine(cfg)

    # locate views
    train_view = find_view(eng, "p1_train_windows_flex7")
    test_view  = find_view(eng, "p1_test_windows_flex7")

    train = load_windows(eng, train_view)
    test  = load_windows(eng,  test_view)

    # lock model: use only exact-7-day windows for eval
    train7 = train.loc[train["days"] == wd].copy()
    test7  = test.loc[test["days"] == wd].copy()

    # leakage guard
    leakage = leakage_check(train7, test7)
    if not leakage["ok"]:
        print(f"[WARN] Train/Test end-date overlap: {leakage['overlap_count']} days")

    # predictions + residuals (pred - actual)
    yhat = predict_dfm(test7["intake_kcal_sum"].to_numpy(),
                       test7["workout_kcal_sum"].to_numpy(),
                       m, c, a, test7["days"].to_numpy())
    resid = residuals(test7["delta_fm_kg"].to_numpy(), yhat)

    # metrics
    metrics = {
        "params": {"m": m, "c": c, "alpha": a, "window_days": wd},
        "leakage": leakage,
        "test_metrics": metrics_block(resid),
    }
    (DATA / "p1_test_metrics.json").write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics["test_metrics"], indent=2))

    # plots — histogram
    plt.figure(figsize=(8,6))
    plt.hist(resid, bins=40)
    plt.axvline(0, ls="--", color="k", alpha=0.7)
    plt.title("Residuals (pred - actual) [kg] — TEST")
    plt.xlabel("kg"); plt.ylabel("count")
    plt.tight_layout()
    plt.savefig(FIGS / "p1_test_residuals_hist.png", dpi=160)
    plt.close()

    # residuals vs predicted
    plt.figure(figsize=(8,6))
    plt.scatter(yhat, resid, alpha=0.5)
    plt.axhline(0, ls="--", color="k", alpha=0.7)
    plt.xlabel("Predicted ΔFM (kg)"); plt.ylabel("Residual (kg)")
    plt.title("Residuals vs Predicted ΔFM — TEST")
    plt.tight_layout()
    plt.savefig(FIGS / "p1_test_residuals_vs_pred.png", dpi=160)
    plt.close()

    # 28-day rolling mean of residuals by end_date
    tmp = test7[["end_date"]].copy()
    tmp["resid"] = resid
    tmp = tmp.sort_values("end_date").set_index("end_date")
    roll = tmp["resid"].rolling("28D").mean()
    plt.figure(figsize=(9,6))
    plt.plot(roll.index, roll.values)
    plt.axhline(0, ls="--", color="k", alpha=0.7)
    plt.title("28-day rolling mean of residuals — TEST")
    plt.ylabel("Residual (kg)"); plt.xlabel("Date")
    plt.tight_layout()
    plt.savefig(FIGS / "p1_test_residuals_rolling28.png", dpi=160)
    plt.close()

    # Sensitivity sweep (±10%) for each parameter → spider MAE
    baselines = []
    labels = ["M -10%","M +10%","C -10%","C +10%","α -10%","α +10%"]
    deltas = [(-0.1,0.1), (-0.1,0.1), (-0.1,0.1)]
    # recompute six scenarios
    scen = []
    for sign in (-0.1, 0.1):
        y = predict_dfm(test7["intake_kcal_sum"], test7["workout_kcal_sum"],
                        m*(1+sign), c, a, test7["days"])
        scen.append(mae(residuals(test7["delta_fm_kg"], y)))
    for sign in (-0.1, 0.1):
        y = predict_dfm(test7["intake_kcal_sum"], test7["workout_kcal_sum"],
                        m, c*(1+sign), a, test7["days"])
        scen.append(mae(residuals(test7["delta_fm_kg"], y)))
    for sign in (-0.1, 0.1):
        y = predict_dfm(test7["intake_kcal_sum"], test7["workout_kcal_sum"],
                        m, c, a*(1+sign), test7["days"])
        scen.append(mae(residuals(test7["delta_fm_kg"], y)))

    # normalize around baseline MAE
    base = mae(resid)
    polar_vals = [v/base for v in scen]

    fig = plt.figure(figsize=(7,7))
    ax = plt.subplot(111, polar=True)
    spider(ax, labels, polar_vals, f"MAE sensitivity (baseline={base:.3f} kg)")
    plt.savefig(FIGS / "p1_test_mae_sensitivity_spider.png", dpi=160)
    plt.close()

    print(f"Wrote metrics to {DATA/'p1_test_metrics.json'} and figures to {FIGS}/")

if __name__ == "__main__":
    main()
