# Testing Dynamic Goals System

## Overview
This document outlines how to test that the UI colors automatically update when performance goals change, without requiring any code changes.

## Test Scenario: Goal Change from Cutting to Maintenance

### Step 1: Verify Current Goals
1. Start the backend: `cd backend && npm start`
2. Start the frontend: `cd frontend && npm start`
3. Open browser to `http://localhost:3000`
4. Verify the "Current Performance Goals" section shows:
   - Protein: Min 140g | Target 190g
   - Fiber: Min 25g | Target 35g
   - Net Deficit: Target 400 | Max 750
   - Source: attia | recomp

### Step 2: Observe Current Color Logic
Note the colors in the Weekly Metrics table (values dynamically pulled from `performance_goals_timevarying`):
- **Protein**: Green ≥{protein_g_target}, Yellow ≥{protein_g_min}, Red <{protein_g_min}
- **Fiber**: Green ≥{fiber_g_target}, Yellow ≥{fiber_g_min}, Red <{fiber_g_min}  
- **Net Calories**: Green ({net_deficit_target} to {net_deficit_max}), Yellow (0 to {net_deficit_target}), Red (>0 or <{net_deficit_max})

### Step 3: Insert New Maintenance Goals
Run this SQL to create new maintenance-focused goals:

```sql
-- Insert maintenance goals (higher protein, smaller deficit)
INSERT INTO performance_goals_timevarying VALUES (
    'v2025_09_25_maintenance',
    '2025-09-25',
    NULL,  -- Current/ongoing
    
    -- Nutrition (maintenance-focused)
    120.0,   -- protein_g_min (yellow) - lower than cutting
    160.0,   -- protein_g_target (green) - lower than cutting
    20.0,    -- fiber_g_min - lower than cutting
    30.0,    -- fiber_g_target - lower than cutting
    500,     -- net_deficit_max (red threshold) - smaller deficit
    200,     -- net_deficit_target - much smaller deficit
    
    -- Training Volume (same)
    3.0,     -- z2_hours_min
    5.0,     -- z2_hours_target
    0.75,    -- z4_5_hours_min
    1.5,     -- z4_5_hours_target
    2,       -- strength_sessions_min
    3,       -- strength_sessions_target
    
    -- Performance Metrics (same)
    250,     -- ftp_watts_target
    40.0,    -- vo2max_target
    
    -- Body Composition (same)
    20.0,    -- body_fat_pct_max
    17.0,    -- body_fat_pct_target
    73.0,    -- lean_mass_kg_min
    
    'custom', 
    'maintenance',
    'Switched to maintenance: lower protein targets, smaller deficit',
    'mark',
    NOW()
);
```

### Step 4: Verify Dynamic Updates
1. **Refresh the browser page**
2. **Verify the "Current Performance Goals" section now shows**:
   - Protein: Min 120g | Target 160g
   - Fiber: Min 20g | Target 30g
   - Net Deficit: Target 200 | Max 500
   - Source: custom | maintenance

3. **Observe the color changes in Weekly Metrics** (automatically updated from database):
   - **Protein**: Green ≥{new_protein_g_target}, Yellow ≥{new_protein_g_min}, Red <{new_protein_g_min}
   - **Fiber**: Green ≥{new_fiber_g_target}, Yellow ≥{new_fiber_g_min}, Red <{new_fiber_g_min}
   - **Net Calories**: Green ({new_net_deficit_target} to {new_net_deficit_max}), Yellow (0 to {new_net_deficit_target}), Red (>0 or <{new_net_deficit_max})

### Step 5: Test Bulking Goals
Insert bulking goals to test surplus handling:

```sql
-- Insert bulking goals (even higher protein, positive net)
INSERT INTO performance_goals_timevarying VALUES (
    'v2025_09_25_bulking',
    '2025-09-25',
    NULL,  -- Current/ongoing
    
    -- Nutrition (bulking-focused)
    150.0,   -- protein_g_min (yellow)
    200.0,   -- protein_g_target (green) - higher than maintenance
    25.0,    -- fiber_g_min
    35.0,    -- fiber_g_target
    -200,    -- net_deficit_max (red threshold) - now a surplus threshold
    -100,    -- net_deficit_target - small surplus
    
    -- Training Volume (same)
    3.0,     -- z2_hours_min
    5.0,     -- z2_hours_target
    0.75,    -- z4_5_hours_min
    1.5,     -- z4_5_hours_target
    2,       -- strength_sessions_min
    3,       -- strength_sessions_target
    
    -- Performance Metrics (same)
    250,     -- ftp_watts_target
    40.0,    -- vo2max_target
    
    -- Body Composition (same)
    20.0,    -- body_fat_pct_max
    17.0,    -- body_fat_pct_target
    73.0,    -- lean_mass_kg_min
    
    'custom', 
    'bulking',
    'Bulking phase: higher protein, small surplus',
    'mark',
    NOW()
);
```

### Step 6: Verify Surplus Logic
1. **Refresh the browser page**
2. **Verify bulking goals display**
3. **Observe surplus color logic** (dynamically calculated from bulking goals):
   - **Net Calories**: Green ({bulking_net_deficit_target} to {bulking_net_deficit_max}), Yellow (0 to {bulking_net_deficit_target}), Red (>0 or <{bulking_net_deficit_max})
   - Positive net calories should show RED (surplus)

## Expected Results

### ✅ Success Criteria
1. **No code changes required** - only database updates
2. **Goals section updates automatically** - shows new version, thresholds, and source
3. **Color logic adapts immediately** - protein/fiber/deficit colors change based on new thresholds
4. **Source attribution works** - shows whether goals are from 'attia', 'custom', or 'coach'
5. **Priority tracking works** - shows 'recomp', 'maintenance', or 'bulking'

### 🔍 Key Factory Principle Validation
- **Database is source of truth** - UI is just a renderer
- **Parameter-driven design** - all thresholds come from `performance_goals_timevarying`
- **Automatic adaptation** - colors adjust when goals change
- **Audit trail** - goal changes are tracked in `audit_hil` table

## Rollback Test
To return to original Attia goals:
```sql
-- End the current goals
UPDATE performance_goals_timevarying 
SET effective_end_date = CURRENT_DATE 
WHERE goal_version = 'v2025_09_25_bulking' AND effective_end_date IS NULL;
```

The original `v2025_09_25` goals should automatically become active again.
