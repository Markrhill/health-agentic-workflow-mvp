-- Migration: 009_add_tef_column.sql
-- Date: 2025-10-01
-- Purpose: Add Thermic Effect of Food (TEF) calculation to daily_facts
--
-- TEF is the energy cost of digesting, absorbing, and processing nutrients.
-- Different macronutrients have different thermic effects:
--   - Protein: 25% of energy consumed (highest)
--   - Carbohydrates: 8% of energy consumed
--   - Fat: 2% of energy consumed (lowest)
--
-- Formula: TEF = (protein_g × 4 kcal/g × 0.25) + (carbs_g × 4 kcal/g × 0.08) + (fat_g × 9 kcal/g × 0.02)
--
-- This is a preprocessing calculation, not a parameter to estimate.

-- ============================================================================
-- FORWARD MIGRATION
-- ============================================================================

-- Step 1: Add tef_kcal column to daily_facts
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_schema = 'public' 
          AND table_name = 'daily_facts' 
          AND column_name = 'tef_kcal'
    ) THEN
        ALTER TABLE daily_facts 
        ADD COLUMN tef_kcal NUMERIC(8,2);
        
        RAISE NOTICE 'Added tef_kcal column to daily_facts';
    ELSE
        RAISE NOTICE 'Column tef_kcal already exists in daily_facts';
    END IF;
END $$;

-- Step 2: Add column comment explaining the formula
COMMENT ON COLUMN daily_facts.tef_kcal IS 
'Thermic Effect of Food (TEF) in kcal - energy cost of digestion. Formula: (protein_g × 4 × 0.25) + (carbs_g × 4 × 0.08) + (fat_g × 9 × 0.02). Protein has highest TEF (25%), fat has lowest (2%).';

-- Step 3: Update existing rows with TEF calculation
UPDATE daily_facts
SET tef_kcal = ROUND(
    COALESCE(protein_g * 4 * 0.25, 0) +
    COALESCE(carbs_g * 4 * 0.08, 0) +
    COALESCE(fat_g * 9 * 0.02, 0),
    2
)
WHERE tef_kcal IS NULL
  AND (protein_g IS NOT NULL OR carbs_g IS NOT NULL OR fat_g IS NOT NULL);

-- Step 4: Add CHECK constraint for sanity check
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'daily_facts_tef_kcal_range'
    ) THEN
        ALTER TABLE daily_facts
        ADD CONSTRAINT daily_facts_tef_kcal_range 
        CHECK (tef_kcal IS NULL OR (tef_kcal >= 0 AND tef_kcal <= 2000));
        
        RAISE NOTICE 'Added CHECK constraint for tef_kcal range';
    ELSE
        RAISE NOTICE 'CHECK constraint daily_facts_tef_kcal_range already exists';
    END IF;
END $$;

-- Step 5: Create index for TEF queries
CREATE INDEX IF NOT EXISTS idx_daily_facts_tef_kcal 
ON daily_facts(tef_kcal) 
WHERE tef_kcal IS NOT NULL;

-- ============================================================================
-- VERIFICATION
-- ============================================================================

-- Verify the migration
DO $$
DECLARE
    v_total_rows bigint;
    v_rows_with_tef bigint;
    v_mean_tef numeric;
    v_min_tef numeric;
    v_max_tef numeric;
BEGIN
    SELECT 
        COUNT(*),
        COUNT(tef_kcal),
        ROUND(AVG(tef_kcal), 1),
        ROUND(MIN(tef_kcal), 1),
        ROUND(MAX(tef_kcal), 1)
    INTO v_total_rows, v_rows_with_tef, v_mean_tef, v_min_tef, v_max_tef
    FROM daily_facts;
    
    RAISE NOTICE '============================================';
    RAISE NOTICE 'TEF Column Migration Verification:';
    RAISE NOTICE '  Total rows in daily_facts: %', v_total_rows;
    RAISE NOTICE '  Rows with TEF calculated: %', v_rows_with_tef;
    RAISE NOTICE '  Mean TEF: % kcal/day', v_mean_tef;
    RAISE NOTICE '  Min TEF: % kcal/day', v_min_tef;
    RAISE NOTICE '  Max TEF: % kcal/day', v_max_tef;
    RAISE NOTICE '  Expected mean: 250-350 kcal/day';
    RAISE NOTICE '============================================';
    
    -- Validate expected range
    IF v_mean_tef IS NOT NULL AND (v_mean_tef < 200 OR v_mean_tef > 400) THEN
        RAISE WARNING 'Mean TEF (% kcal) outside expected range (250-350 kcal)', v_mean_tef;
    END IF;
    
    IF v_max_tef IS NOT NULL AND v_max_tef > 2000 THEN
        RAISE WARNING 'Max TEF (% kcal) exceeds sanity limit (2000 kcal)', v_max_tef;
    END IF;
END $$;

-- ============================================================================
-- ROLLBACK (if needed)
-- ============================================================================
-- To rollback this migration, run:
--
-- ALTER TABLE daily_facts DROP COLUMN IF EXISTS tef_kcal;
-- DROP INDEX IF EXISTS idx_daily_facts_tef_kcal;
--
-- Note: This will permanently delete all TEF calculations.
-- ============================================================================

