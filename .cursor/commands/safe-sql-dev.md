# Safe SQL Development Guide

## Development Workflow

When developing complex SQL queries, follow this incremental approach:

### 1. Start in Cursor Editor
- Write your initial query in the Cursor editor
- Use proper syntax highlighting and formatting
- Comment complex logic for clarity

### 2. Test on Small Subset
```sql
-- Always start with a small sample
SELECT * FROM table_name LIMIT 5;

-- Then test specific columns
SELECT column1, column2 FROM table_name LIMIT 10;

-- Verify data types and ranges
SELECT 
    column_name,
    COUNT(*) as count,
    MIN(column_name) as min_val,
    MAX(column_name) as max_val
FROM table_name 
GROUP BY column_name;
```

### 3. Build Complexity Incrementally
- Add one JOIN at a time
- Test each WHERE clause addition
- Verify each GROUP BY or ORDER BY change
- Test aggregation functions separately

### 4. Document Working Patterns
- Save successful query patterns in project files
- Document common joins and transformations
- Note performance considerations
- Record data quality checks

### 5. Validation Before Execution
- **Never execute multi-step operations without validation**
- Test each step individually
- Verify expected row counts
- Check for data type mismatches
- Validate foreign key relationships

## Best Practices

### Query Structure
```sql
-- Use consistent formatting
SELECT 
    column1,
    column2,
    CASE 
        WHEN condition1 THEN 'value1'
        WHEN condition2 THEN 'value2'
        ELSE 'default'
    END as calculated_column
FROM table1 t1
    INNER JOIN table2 t2 ON t1.id = t2.foreign_id
WHERE t1.date_column >= '2024-01-01'
    AND t1.status = 'active'
GROUP BY t1.id, t1.name
HAVING COUNT(*) > 1
ORDER BY t1.date_column DESC;
```

### Data Quality Checks
```sql
-- Check for nulls
SELECT COUNT(*) as total_rows,
       COUNT(column_name) as non_null_rows,
       COUNT(*) - COUNT(column_name) as null_count
FROM table_name;

-- Check for duplicates
SELECT column_name, COUNT(*) as duplicate_count
FROM table_name
GROUP BY column_name
HAVING COUNT(*) > 1;

-- Check data ranges
SELECT 
    MIN(numeric_column) as min_val,
    MAX(numeric_column) as max_val,
    AVG(numeric_column) as avg_val
FROM table_name;
```

### Performance Considerations
- Use LIMIT for initial testing
- Add appropriate indexes
- Consider query execution plans
- Monitor query performance
- Use EXPLAIN ANALYZE when needed

## Project-Specific Guidelines

Based on the health-agentic-workflow-mvp context:

### Schema Validation
- Always validate against `schema.manifest.yaml` before table changes
- Test on single week before batch operations
- Use versioned parameters for reproducible calculations

### Data Quality
- Enforce fat mass range 20-60kg
- Validate intake 500-6000 kcal/day
- Check imputation consistency
- Verify BIA measurement handling

### Current vs. Deprecated Tables
**CRITICAL**: Use only current canonical tables:
- ✅ `daily_facts` - Current daily health metrics
- ✅ `model_params_timevarying` - Current parameters
- ✅ `daily_series_materialized` - Current computed series
- ❌ `p0_staging`, `p1_train_daily`, `p1_test_daily` - DEPRECATED
- ❌ Any `p0_*` or `p1_*` tables - DEPRECATED

See `docs/DEPRECATED.md` for complete list.

### Common Patterns
```sql
-- 7-day windowing for ΔFM calculations
SELECT 
    date,
    fat_mass,
    LAG(fat_mass, 7) OVER (ORDER BY date) as fat_mass_7d_ago,
    fat_mass - LAG(fat_mass, 7) OVER (ORDER BY date) as delta_fm_7d
FROM daily_facts
WHERE date >= '2024-01-01'
ORDER BY date;

-- Net energy calculation
SELECT 
    date,
    intake_kcal,
    workout_kcal,
    bmr0,
    k_lbm,
    lbm_ema,
    intake_kcal - (1-c)*workout_kcal - (bmr0 + k_lbm*lbm_ema) as net_kcal
FROM daily_facts
WHERE date >= '2024-01-01';
```

## Emergency Procedures

If a query causes issues:
1. **STOP** - Don't run additional queries
2. Check query execution status
3. Review query logs
4. Consider rolling back if necessary
5. Document the issue and solution

## Resources

- Project schema: `schema.manifest.yaml`
- Migration files: `sql/migrations/`
- Test data: `data/` directory
- Documentation: `docs/` directory
