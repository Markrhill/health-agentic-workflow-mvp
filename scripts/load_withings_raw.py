#!/usr/bin/env python3
"""
Load a Withings CSV (any header mix) into public.withings_measurements_raw.

Usage:
  python scripts/load_withings_raw.py /path/to/withings.csv [--source-file ALIAS]

Env:
  PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD
"""

import argparse, csv, os, sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
import psycopg  # psycopg 3.x

# ---- 1) Header normalization -------------------------------------------------

# Map many possible CSV header variants to our canonical column names.
HEADER_MAP = {
    # timestamp
    "date": "measured_at",
    "datetime": "measured_at",
    "measured_at": "measured_at",
    "timestamp": "measured_at",
    "created": "measured_at",
    # weight
    "weight (lb)": "weight_lb",
    "weight_lb": "weight_lb",
    "weight": "weight_lb",
    # fat
    "fat mass (lb)": "fat_mass_lb",
    "fat_mass_lb": "fat_mass_lb",
    "fat mass": "fat_mass_lb",
    "fat_mass": "fat_mass_lb",
    # muscle
    "muscle mass (lb)": "muscle_mass_lb",
    "muscle mass": "muscle_mass_lb",
    "muscle_mass_lb": "muscle_mass_lb",
    "muscle": "muscle_mass_lb",
    # bone
    "bone mass (lb)": "bone_mass_lb",
    "bone mass": "bone_mass_lb",
    "bone_mass_lb": "bone_mass_lb",
    # water
    "hydration (lb)": "body_water_lb",
    "hydration": "body_water_lb",
    "body_water_lb": "body_water_lb",
    "water": "body_water_lb",
    # misc
    "note": "note",
    "comments": "note",
}

CANONICAL = ["measured_at", "weight_lb", "fat_mass_lb", "muscle_mass_lb",
             "bone_mass_lb", "body_water_lb", "note"]

def normalize_header(name: str) -> Optional[str]:
    key = name.strip().lower()
    return HEADER_MAP.get(key)

# ---- 2) Parsing helpers ------------------------------------------------------

def parse_ts(val: str) -> datetime:
    """
    Try hard to parse timestamps; assume they are local or UTC.
    We'll store as UTC (timestamptz). If no tz info, assume local and convert to UTC.
    """
    if val is None or val.strip() == "":
        raise ValueError("empty timestamp")
    s = val.strip()

    # common patterns: 'YYYY-MM-DD HH:MM:SS', ISO, etc.
    # Try fromisoformat first
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            # treat as local time; convert to UTC
            return dt.replace(tzinfo=timezone.utc)  # If you prefer local→UTC, adjust here
        return dt.astimezone(timezone.utc)
    except Exception:
        pass

    # Fallback: a few strptime patterns
    for fmt in ("%Y-%m-%d %H:%M:%S",
                "%Y/%m/%d %H:%M:%S",
                "%m/%d/%Y %H:%M",
                "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue

    raise ValueError(f"unrecognized datetime format: {s}")

def parse_num(val: Any) -> Optional[float]:
    if val is None:
        return None
    s = str(val).strip()
    if s == "" or s.lower() in {"na", "null", "none"}:
        return None
    # Strip commas and units if any
    s = s.replace(",", "")
    # If something like "123 lb", split on space
    parts = s.split()
    try:
        return float(parts[0])
    except Exception:
        return None

def to_canonical_row(raw_row: Dict[str, Any]) -> Tuple[datetime, Optional[float], Optional[float],
                                                       Optional[float], Optional[float], Optional[float],
                                                       Optional[str], Dict[str, Any]]:
    # Map incoming headers to canonical keys
    mapped: Dict[str, Any] = {}
    for k, v in raw_row.items():
        canon = normalize_header(k) or k.strip().lower()
        # Keep original too; mapping may not cover everything
        mapped.setdefault(canon, v)

    # Required: measured_at
    measured_at = parse_ts(mapped.get("measured_at"))

    return (
        measured_at,
        parse_num(mapped.get("weight_lb")),
        parse_num(mapped.get("fat_mass_lb")),
        parse_num(mapped.get("muscle_mass_lb")),
        parse_num(mapped.get("bone_mass_lb")),
        parse_num(mapped.get("body_water_lb")),
        (mapped.get("note") or None),
        raw_row,  # original, untouched row to store as JSONB
    )

# ---- 3) DB insert ------------------------------------------------------------

INSERT_SQL = """
INSERT INTO public.withings_measurements_raw
(measured_at, weight_lb, fat_mass_lb, muscle_mass_lb, bone_mass_lb, body_water_lb, source_file, note, raw)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT DO NOTHING;
"""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--source-file", default=None, help="provenance label (defaults to CSV filename)")
    args = ap.parse_args()

    csv_path = args.csv_path
    if not os.path.isfile(csv_path):
        print(f"ERROR: file not found: {csv_path}", file=sys.stderr)
        sys.exit(2)

    source_file = args.source_file or os.path.basename(csv_path)

    rows = []
    bad = 0
    with open(csv_path, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            print("ERROR: CSV has no header row.", file=sys.stderr)
            sys.exit(2)

        for i, raw_row in enumerate(reader, start=2):  # start=2 for header line offset
            try:
                measured_at, w, f_, m, b, h2o, note, raw_obj = to_canonical_row(raw_row)
                rows.append((
                    measured_at, w, f_, m, b, h2o, source_file, note, psycopg.types.json.Jsonb(raw_obj)
                ))
            except Exception as e:
                bad += 1
                if bad <= 10:
                    print(f"WARN line {i}: {e} | row={raw_row}", file=sys.stderr)
                continue

    if not rows:
        print("No valid rows parsed; nothing to insert.", file=sys.stderr)
        sys.exit(3)

    # Connect via env vars (PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD)
    conn_str = "postgresql://{user}:{pw}@{host}:{port}/{db}".format(
        user=os.getenv("PGUSER", ""),
        pw=os.getenv("PGPASSWORD", ""),
        host=os.getenv("PGHOST", "localhost"),
        port=os.getenv("PGPORT", "5432"),
        db=os.getenv("PGDATABASE", ""),
    )
    try:
        with psycopg.connect(conn_str, autocommit=True) as conn, conn.cursor() as cur:
            cur.executemany(INSERT_SQL, rows)
    except Exception as e:
        print(f"DB insert failed: {e}", file=sys.stderr)
        sys.exit(4)

    print(f"Inserted {len(rows)} rows ({bad} skipped). source_file='{source_file}'")

if __name__ == "__main__":
    main()
