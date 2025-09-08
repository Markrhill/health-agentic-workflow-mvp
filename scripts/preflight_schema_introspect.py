#!/usr/bin/env python3
"""
introspect_columns.py
Print YAML-ready manifest stubs for exact Postgres relation schemas.

Requirements:
  pip install psycopg2-binary

Environment:
  PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD

Usage:
  export PGHOST=... PGPORT=5432 PGDATABASE=... PGUSER=... PGPASSWORD=...
  python introspect_columns.py public.p0_staging public.p0_imputed_intake
Exit codes:
  0 = success
  2 = some relations not found
  3 = database/connection error
  4 = bad CLI usage (no relations provided)
"""
import os
import sys
import argparse
from typing import List, Tuple, Dict

try:
    import psycopg2
    import psycopg2.extras
except Exception as e:
    print("ERROR: psycopg2-binary is required. Install with `pip install psycopg2-binary`.", file=sys.stderr)
    sys.exit(3)

RELKIND_MAP = {
    'r': 'table',
    'v': 'view',
    'm': 'materialized_view',
    'f': 'foreign_table'
}

def die(msg: str, code: int) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)

def connect():
    try:
        conn = psycopg2.connect(
            host=os.environ.get('PGHOST', 'localhost'),
            port=int(os.environ.get('PGPORT', '5432')),
            dbname=os.environ.get('PGDATABASE'),
            user=os.environ.get('PGUSER'),
            password=os.environ.get('PGPASSWORD'),
        )
        conn.autocommit = True
        return conn
    except Exception as e:
        die(f"DB connection failed: {e}", 3)

def split_relname(fully_qualified: str) -> Tuple[str, str]:
    if '.' in fully_qualified:
        schema, rel = fully_qualified.split('.', 1)
    else:
        schema, rel = 'public', fully_qualified
    return schema, rel

def ensure_exists(cur, schema: str, rel: str) -> Tuple[bool, str]:
    cur.execute("""
        SELECT c.relkind
        FROM pg_namespace n
        JOIN pg_class c ON c.relnamespace = n.oid
        WHERE n.nspname = %s AND c.relname = %s
    """, (schema, rel))
    row = cur.fetchone()
    if not row:
        return False, ""
    return True, row[0]

def fetch_columns(cur, schema: str, rel: str) -> List[Dict]:
    cur.execute("""
        SELECT
          a.attnum AS ordinal_position,
          a.attname AS column_name,
          pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type,
          NOT a.attnotnull AS is_nullable,
          pg_get_expr(ad.adbin, ad.adrelid) AS column_default
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
        LEFT JOIN pg_attrdef ad ON ad.adrelid = c.oid AND ad.adnum = a.attnum
        WHERE n.nspname = %s AND c.relname = %s
        ORDER BY a.attnum;
    """, (schema, rel))
    rows = cur.fetchall()
    cols = []
    for ordinal_position, name, dtype, is_nullable, default in rows:
        cols.append({
            "ordinal_position": ordinal_position,
            "name": name,
            "data_type": dtype,
            "is_nullable": bool(is_nullable),
            "default": default
        })
    return cols

def yaml_escape(s: str) -> str:
    # Simple scalar escaper for YAML (quotes if needed)
    if s is None:
        return "null"
    if any(ch in s for ch in [":", "#", "-", "{", "}", ",", "[", "]", "&", "*", "!", "|", ">", "'", '"', "%", "@", "`", "\n", "\r", "\t"]):
        return '"' + s.replace('"', '\\"') + '"'
    return s

def print_yaml_stub(fq: str, relkind: str, cols: List[Dict]) -> None:
    print(f"- id: {fq.split('.',1)[1]}")
    print(f"  purpose: TBD")
    print(f"  type: {RELKIND_MAP.get(relkind, relkind)}")
    print(f"  fq_name: {fq}")
    print(f"  keys:")
    print(f"    - TBD_PRIMARY_KEY  # <-- set the correct key(s)")
    print(f"  columns:")
    for c in cols:
        name = c["name"]
        dtype = c["data_type"]
        # Map PG types to manifest-friendly types (leave as-is; you can refine later)
        print(f"    - {{ name: {yaml_escape(name)}, type: {yaml_escape(dtype)}, required: {'false' if c['is_nullable'] else 'true'} }}")
    print("  tests:")
    print("    shape:")
    print("      - not_null: [TBD_PRIMARY_KEY]  # <-- adjust")
    print("      - unique_keys: [[TBD_PRIMARY_KEY]]")
    print()

def main():
    ap = argparse.ArgumentParser(description="Introspect Postgres relations and print YAML-ready manifest stubs.")
    ap.add_argument("relations", nargs="*", help="Fully-qualified relation names (schema.name). If schema omitted, defaults to public.")
    args = ap.parse_args()

    if not args.relations:
        die("No relations provided. Example: python introspect_columns.py public.p0_staging public.p0_imputed_intake", 4)

    conn = connect()
    cur = conn.cursor()

    missing: List[str] = []
    results: List[Tuple[str, str, List[Dict]]] = []

    for relname in args.relations:
        schema, rel = split_relname(relname)
        exists, relkind = ensure_exists(cur, schema, rel)
        fq = f"{schema}.{rel}"
        if not exists:
            missing.append(fq)
            continue
        cols = fetch_columns(cur, schema, rel)
        results.append((fq, relkind, cols))

    if missing:
        print("The following relations were NOT found:", file=sys.stderr)
        for m in missing:
            print(f"  - {m}", file=sys.stderr)
        sys.exit(2)

    # Output YAML-ready blocks
    for fq, relkind, cols in results:
        print_yaml_stub(fq, relkind, cols)

if __name__ == "__main__":
    main()
