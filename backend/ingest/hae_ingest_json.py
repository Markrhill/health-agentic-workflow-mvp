# backend/ingest/hae_ingest_json.py
import json, sys, os
from datetime import datetime
import psycopg2
from psycopg2.extras import Json

# Uses DATABASE_URL from your .env (same as the rest of the app)
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set"); sys.exit(1)

if len(sys.argv) != 2:
    print("USAGE: python backend/ingest/hae_ingest_json.py /path/to/HealthAutoExport-YYYY-MM-DD.json")
    sys.exit(2)

infile = sys.argv[1]
with open(infile, "r", encoding="utf-8") as f:
    payload = json.load(f)

metrics = payload.get("data", {}).get("metrics", [])
if not metrics:
    print("No metrics array found"); sys.exit(0)

conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True

DDL = """
CREATE TABLE IF NOT EXISTS hae_samples (
  sample_date        date        NOT NULL,
  metric_name        text        NOT NULL,
  unit               text,
  value_num          double precision,
  summary_json       jsonb       NOT NULL,
  source             text,
  created_at         timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (sample_date, metric_name)
);
"""
UPSERT = """
INSERT INTO hae_samples (sample_date, metric_name, unit, value_num, summary_json, source)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (sample_date, metric_name) DO UPDATE
SET unit = EXCLUDED.unit,
    value_num = COALESCE(EXCLUDED.value_num, hae_samples.value_num),
    summary_json = EXCLUDED.summary_json,
    source = COALESCE(EXCLUDED.source, hae_samples.source),
    created_at = now();
"""

with conn, conn.cursor() as cur:
    cur.execute(DDL)

    for m in metrics:
        name = m.get("name")                 # e.g., "protein", "total_fat", "heart_rate", "sleep_analysis", "heart_rate_variability"
        unit = m.get("units")
        data = m.get("data", [])
        if not data: 
            continue

        # HAE groups a day's worth into a single element (we'll take the first)
        d0 = data[0]

        # Determine date (all examples show midnight local as a string)
        # Example: "2025-09-01 00:00:00 -0700"
        date_str = d0.get("date")
        if not date_str:
            # fall back: try sleep fields
            date_str = d0.get("sleepEnd") or d0.get("inBedEnd")
        sample_date = datetime.strptime(date_str[:19], "%Y-%m-%d %H:%M:%S").date()

        # Choose a numeric value to store in value_num (for quick rollups),
        # while keeping the full record in summary_json.
        value_num = None
        src = d0.get("source")

        if "qty" in d0:
            value_num = float(d0["qty"])
        elif name == "heart_rate":
            # store Average if present
            if "Avg" in d0: value_num = float(d0["Avg"])
        elif name == "sleep_analysis":
            # store total hours of sleep as value_num
            if "totalSleep" in d0: value_num = float(d0["totalSleep"])
        # heart_rate_variability already handled by qty

        cur.execute(
            UPSERT,
            (sample_date, name, unit, value_num, Json(d0), source)
        )

print(f"Ingested: {infile}")

