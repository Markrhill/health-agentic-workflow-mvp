#!/usr/bin/env python3
"""
detect_schema_drift.py
Compare actual database schema with manifest to detect drift.

This helps catch when your database structure diverges from your
documented schema, preventing the cycles of failure.

Usage:
  export PGHOST=... PGPORT=5432 PGDATABASE=... PGUSER=... PGPASSWORD=...
  python scripts/detect_schema_drift.py
  python scripts/detect_schema_drift.py --fix-manifest  # Update manifest with actual schema

Exit codes:
  0 = no drift detected
  1 = drift detected
  2 = database connection error
  3 = configuration error
"""
import os
import sys
import argparse
import yaml
from typing import Dict, List, Set, Tuple
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

def get_actual_schema(cur) -> Dict[str, Dict]:
    """Get actual database schema from PostgreSQL."""
    actual = {}
    
    # Get all tables and views
    cur.execute("""
        SELECT 
            n.nspname as schema_name,
            c.relname as table_name,
            c.relkind as relation_type,
            obj_description(c.oid) as comment
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
        AND c.relkind IN ('r', 'v', 'm', 'f')
        ORDER BY c.relname;
    """)
    
    for schema_name, table_name, relkind, comment in cur.fetchall():
        fq_name = f"{schema_name}.{table_name}"
        
        # Get columns
        cur.execute("""
            SELECT 
                a.attname as column_name,
                pg_catalog.format_type(a.atttypid, a.atttypmod) as data_type,
                NOT a.attnotnull as is_nullable,
                pg_get_expr(ad.adbin, ad.adrelid) as column_default
            FROM pg_attribute a
            LEFT JOIN pg_attrdef ad ON ad.adrelid = a.attrelid AND ad.adnum = a.attnum
            WHERE a.attrelid = (
                SELECT oid FROM pg_class 
                WHERE relname = %s AND relnamespace = (
                    SELECT oid FROM pg_namespace WHERE nspname = %s
                )
            )
            AND a.attnum > 0 AND NOT a.attisdropped
            ORDER BY a.attnum;
        """, (table_name, schema_name))
        
        columns = []
        for col_name, col_type, is_nullable, col_default in cur.fetchall():
            columns.append({
                'name': col_name,
                'type': col_type,
                'nullable': is_nullable,
                'default': col_default
            })
        
        actual[fq_name] = {
            'type': 'table' if relkind == 'r' else 'view',
            'columns': columns,
            'comment': comment
        }
    
    return actual

def get_manifest_schema(manifest: Dict) -> Dict[str, Dict]:
    """Extract schema from manifest."""
    manifest_schema = {}
    
    for relation in manifest.get('relations', []):
        fq_name = relation.get('fq_name', '')
        if not fq_name:
            continue
            
        columns = []
        for col in relation.get('columns', []):
            columns.append({
                'name': col.get('name', ''),
                'type': col.get('type', ''),
                'nullable': col.get('required', True) == False,
                'default': None  # Not stored in manifest
            })
        
        manifest_schema[fq_name] = {
            'type': relation.get('type', ''),
            'columns': columns,
            'comment': relation.get('purpose', '')
        }
    
    return manifest_schema

def compare_schemas(actual: Dict, manifest: Dict) -> List[str]:
    """Compare actual schema with manifest and return drift issues."""
    issues = []
    
    # Check for missing objects in manifest
    for fq_name in actual:
        if fq_name not in manifest:
            issues.append(f"Object {fq_name} exists in DB but not in manifest")
    
    # Check for missing objects in database
    for fq_name in manifest:
        if fq_name not in actual:
            issues.append(f"Object {fq_name} in manifest but not in DB")
            continue
        
        # Compare object types
        actual_type = actual[fq_name]['type']
        manifest_type = manifest[fq_name]['type']
        if actual_type != manifest_type:
            issues.append(f"Object {fq_name}: type mismatch (DB: {actual_type}, manifest: {manifest_type})")
        
        # Compare columns
        actual_cols = {col['name']: col for col in actual[fq_name]['columns']}
        manifest_cols = {col['name']: col for col in manifest[fq_name]['columns']}
        
        # Missing columns in manifest
        for col_name in actual_cols:
            if col_name not in manifest_cols:
                issues.append(f"Object {fq_name}: column {col_name} exists in DB but not in manifest")
        
        # Missing columns in database
        for col_name in manifest_cols:
            if col_name not in actual_cols:
                issues.append(f"Object {fq_name}: column {col_name} in manifest but not in DB")
                continue
            
            # Compare column types
            actual_col = actual_cols[col_name]
            manifest_col = manifest_cols[col_name]
            
            if actual_col['type'] != manifest_col['type']:
                issues.append(f"Object {fq_name}.{col_name}: type mismatch (DB: {actual_col['type']}, manifest: {manifest_col['type']})")
            
            if actual_col['nullable'] != manifest_col['nullable']:
                issues.append(f"Object {fq_name}.{col_name}: nullable mismatch (DB: {actual_col['nullable']}, manifest: {manifest_col['nullable']})")
    
    return issues

def main():
    parser = argparse.ArgumentParser(description="Detect schema drift between database and manifest")
    parser.add_argument("--fix-manifest", action="store_true", 
                       help="Update manifest with actual database schema (creates backup)")
    args = parser.parse_args()
    
    # Load manifest
    manifest = load_manifest()
    
    # Connect to database
    conn = connect()
    cur = conn.cursor()
    
    # Get actual schema
    actual = get_actual_schema(cur)
    manifest_schema = get_manifest_schema(manifest)
    
    # Compare schemas
    issues = compare_schemas(actual, manifest_schema)
    
    cur.close()
    conn.close()
    
    if issues:
        print("❌ Schema drift detected:")
        for issue in issues:
            print(f"  - {issue}")
        
        if args.fix_manifest:
            print("\n🔧 Fixing manifest with actual schema...")
            # TODO: Implement manifest fixing logic
            print("Feature not yet implemented. Use preflight_schema_introspect.py to generate stubs.")
        
        sys.exit(1)
    else:
        print("✅ No schema drift detected")
        sys.exit(0)

if __name__ == "__main__":
    main()
