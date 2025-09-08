#!/usr/bin/env python3
"""
validate_schema.py
Pre-flight validation script to ensure all required database objects exist
before running Python code that depends on them.

This prevents the cycles of failure from yesterday where Python code
called non-existent tables and views.

Usage:
  export PGHOST=... PGPORT=5432 PGDATABASE=... PGUSER=... PGPASSWORD=...
  python scripts/validate_schema.py
  python scripts/validate_schema.py --check-views-only
  python scripts/validate_schema.py --check-tables-only

Exit codes:
  0 = all required objects exist
  1 = some required objects missing
  2 = database connection error
  3 = configuration error
"""
import os
import sys
import argparse
import yaml
from typing import List, Dict, Set, Tuple
from pathlib import Path

try:
    import psycopg2
    import psycopg2.extras
except Exception as e:
    print("ERROR: psycopg2-binary is required. Install with `pip install psycopg2-binary`.", file=sys.stderr)
    sys.exit(3)

def die(msg: str, code: int) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)

def load_manifest() -> Dict:
    """Load schema manifest from YAML file."""
    manifest_path = Path(__file__).parent.parent / "schema.manifest.yaml"
    if not manifest_path.exists():
        die(f"Schema manifest not found at {manifest_path}", 3)
    
    with open(manifest_path, 'r') as f:
        return yaml.safe_load(f)

def connect():
    """Connect to PostgreSQL database."""
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
        die(f"DB connection failed: {e}", 2)

def get_required_objects(manifest: Dict) -> Tuple[Set[str], Set[str]]:
    """Extract required tables and views from manifest."""
    tables = set()
    views = set()
    
    for relation in manifest.get('relations', []):
        fq_name = relation.get('fq_name', '')
        rel_type = relation.get('type', '')
        
        if rel_type == 'table':
            tables.add(fq_name)
        elif rel_type in ['view', 'materialized_view']:
            views.add(fq_name)
    
    return tables, views

def get_python_dependencies() -> Tuple[Set[str], Set[str]]:
    """Hard-coded list of database objects that Python code depends on.
    
    This is extracted from scanning the codebase for SQL references.
    TODO: Make this dynamic by parsing Python files for SQL references.
    """
    # Tables/views that Python code directly references
    python_tables = {
        'public.p0_staging',  # p1_fm_clean.py, p1_residuals.py
        'public.p0_imputed_intake',  # Referenced in manifest
        'public.p1_fm_clean',  # Created by p1_fm_clean.py
    }
    
    python_views = {
        'public.p1_train_windows_flex7',  # p1_eval.py, p1_fit_params.py
        'public.p1_test_windows_flex7',   # p1_eval.py
        'public.withings_daily_valid',    # Referenced in manifest
        'public.nutrition_daily',         # Referenced in manifest
        'public.trainingpeaks_enriched',  # Referenced in manifest
        'public.p1_train_daily',          # Referenced in manifest
        'public.p1_test_daily',           # Referenced in manifest
    }
    
    return python_tables, python_views

def check_objects_exist(cur, objects: Set[str], obj_type: str) -> Tuple[List[str], List[str]]:
    """Check which objects exist in the database."""
    existing = []
    missing = []
    
    for fq_name in objects:
        schema, table = fq_name.split('.', 1)
        
        # Check if object exists
        cur.execute("""
            SELECT c.relkind
            FROM pg_namespace n
            JOIN pg_class c ON c.relnamespace = n.oid
            WHERE n.nspname = %s AND c.relname = %s
        """, (schema, table))
        
        row = cur.fetchone()
        if row:
            relkind = row[0]
            if obj_type == 'table' and relkind == 'r':
                existing.append(fq_name)
            elif obj_type == 'view' and relkind in ['v', 'm']:
                existing.append(fq_name)
            else:
                missing.append(f"{fq_name} (wrong type: {relkind})")
        else:
            missing.append(fq_name)
    
    return existing, missing

def main():
    parser = argparse.ArgumentParser(description="Validate database schema before running Python code")
    parser.add_argument("--check-views-only", action="store_true", help="Only check views")
    parser.add_argument("--check-tables-only", action="store_true", help="Only check tables")
    parser.add_argument("--include-python-deps", action="store_true", 
                       help="Also check objects that Python code depends on")
    args = parser.parse_args()
    
    # Load manifest
    manifest = load_manifest()
    manifest_tables, manifest_views = get_required_objects(manifest)
    
    # Get Python dependencies
    python_tables, python_views = get_python_dependencies()
    
    # Combine requirements
    all_tables = manifest_tables
    all_views = manifest_views
    
    if args.include_python_deps:
        all_tables.update(python_tables)
        all_views.update(python_views)
    
    # Connect to database
    conn = connect()
    cur = conn.cursor()
    
    missing_objects = []
    
    # Check tables
    if not args.check_views_only:
        existing_tables, missing_tables = check_objects_exist(cur, all_tables, 'table')
        missing_objects.extend(missing_tables)
        
        print(f"Tables: {len(existing_tables)}/{len(all_tables)} exist")
        if missing_tables:
            print("Missing tables:")
            for table in missing_tables:
                print(f"  - {table}")
    
    # Check views
    if not args.check_tables_only:
        existing_views, missing_views = check_objects_exist(cur, all_views, 'view')
        missing_objects.extend(missing_views)
        
        print(f"Views: {len(existing_views)}/{len(all_views)} exist")
        if missing_views:
            print("Missing views:")
            for view in missing_views:
                print(f"  - {view}")
    
    cur.close()
    conn.close()
    
    if missing_objects:
        print(f"\n❌ Schema validation failed: {len(missing_objects)} objects missing")
        print("\nTo fix this:")
        print("1. Create missing database objects")
        print("2. Update schema.manifest.yaml if objects were renamed")
        print("3. Run: python scripts/preflight_schema_introspect.py <missing_objects>")
        sys.exit(1)
    else:
        print("\n✅ Schema validation passed: all required objects exist")
        sys.exit(0)

if __name__ == "__main__":
    main()
