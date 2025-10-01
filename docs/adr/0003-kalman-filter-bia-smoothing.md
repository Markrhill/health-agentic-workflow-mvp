# ADR-0003: Kalman Filter for BIA Fat Mass Smoothing

**Date**: 2025-09-30  
**Status**: Accepted  
**Deciders**: Data Quality Team

## Context

BIA (Bioelectrical Impedance Analysis) measurements have high noise relative to true physiological changes:
- **BIA measurement noise**: ±1.7 kg (from peer-reviewed literature)
- **True daily fat mass change**: ±0.14 kg (physiological limits of fat oxidation)
- **Observed raw stddev**: ±0.79 kg in daily_facts.fat_mass_kg

This noise creates significant problems for energy balance modeling:
- Each weekly window has **two noisy endpoints** (start and end fat mass)
- Endpoint noise of ±0.79 kg propagates through Δfat_mass calculation
- Inflates uncertainty in parameter estimation (α, C, BMR₀, k_LBM)
- Makes it difficult to distinguish true physiological changes from measurement error

### Problem Statement

Raw `fat_mass_kg` in `daily_facts` is too noisy to directly use for modeling. We need a smoothed estimate that:
1. Reduces noise while preserving true physiological trends
2. Provides quantified uncertainty for downstream Bayesian parameter estimation
3. Handles measurement gaps appropriately
4. Is mathematically rigorous and well-defined

### Alternatives Considered

1. **Raw data** - Status quo
   - ❌ Too noisy (±0.79 kg stddev)
   - ❌ No uncertainty quantification
   
2. **Simple moving average** - Rolling window average
   - ❌ Introduces lag in capturing true changes
   - ❌ No uncertainty quantification
   - ❌ Poor handling of gaps
   
3. **Exponential smoothing** - Fixed decay factor
   - ❌ Fixed smoothing factor doesn't adapt to data quality
   - ❌ No proper uncertainty propagation
   - ❌ Not optimal for measurement gaps
   
4. **Kalman filter** - Optimal recursive estimation
   - ✅ Dynamic gain adapts to uncertainty
   - ✅ Proper uncertainty quantification (P_t|t)
   - ✅ Optimal handling of measurement gaps
   - ✅ Well-established "gold standard" method

## Decision

**Implement a Kalman filter to create `fat_mass_kg_filtered` with proper uncertainty quantification.**

### Parameters (Derived 2025-09-30)

- **Q = 0.0196 kg²** (process noise)
  - Represents maximum physiological daily change
  - Derived from fat oxidation limits (~200 kcal/day ÷ 9800 kcal/kg ≈ 0.14 kg/day)
  - Q = (0.14)² = 0.0196 kg²

- **R = 2.89 kg²** (measurement noise)
  - BIA sensor error from peer-reviewed literature
  - Represents variability in BIA measurements due to hydration, posture, time of day
  - R = (1.7)² = 2.89 kg²

### Algorithm

**Standard Kalman filter with dynamic gain** (NOT fixed exponential smoothing):

For each day t:
1. **Predict step:**
   - State: x̂_t|t-1 = x̂_t-1|t-1
   - Covariance: P_t|t-1 = P_t-1|t-1 + (days_since_last × Q)

2. **Update step** (if measurement available):
   - Kalman gain: K_t = P_t|t-1 / (P_t|t-1 + R)
   - State: x̂_t|t = x̂_t|t-1 + K_t(z_t - x̂_t|t-1)
   - Covariance: P_t|t = (1 - K_t)P_t|t-1

3. **No measurement** (if NULL):
   - Forward-fill state: x̂_t|t = x̂_t|t-1
   - Propagate uncertainty: P_t|t = P_t|t-1

Key properties:
- **Kalman gain varies dynamically**: K_t ∈ [0, 1], adapts to uncertainty
- **Gain decreases with consecutive measurements**: More confidence in model
- **Covariance decreases with measurements**: Reduced uncertainty
- **Covariance increases during gaps**: Increased uncertainty

### Implementation

**Python implementation** (`etl/kalman_filter.py`):
- SQL is inadequate for iterative state estimation (set-based, not procedural)
- Requires sequential processing with state carried forward
- Python provides clear implementation of mathematical equations

**Data Flow:**
```
daily_facts.fat_mass_kg → kalman_filter.py → daily_facts_filtered
```

**Usage:**
```bash
# Test mode with validation
python etl/kalman_filter.py --test

# Production mode
python etl/kalman_filter.py --start-date 2021-01-01 --end-date 2025-09-28
```

## Consequences

### Positive

1. **Noise Reduction**: 3x improvement in stddev
   - Raw: 0.79 kg → Filtered: 0.26 kg
   - Validated: 57-79% reduction on test data

2. **Tighter Confidence Intervals**: Reduced parameter estimation uncertainty
   - Less noise in Δfat_mass endpoints
   - More reliable α, C, BMR₀, k_LBM estimates

3. **Quantified Uncertainty**: `fat_mass_kg_variance` enables Bayesian updates
   - Can weight observations by uncertainty
   - Proper propagation through parameter estimation

4. **Gap Handling**: Appropriate uncertainty increase during missing measurements
   - No artificial forward-fill assumptions
   - Honest about reduced confidence

5. **Mathematical Rigor**: Well-established optimal estimation method
   - Provably optimal under Gaussian assumptions
   - Extensive validation and literature support

### Negative

1. **Additional ETL Step**: Must run after HAE import, before window generation
   - Adds complexity to data pipeline
   - Need to maintain Python script

2. **Computational Cost**: Sequential processing required
   - Cannot parallelize (state dependencies)
   - ~0.1 seconds per 1000 days (acceptable)

3. **Parameter Sensitivity**: Requires empirically-derived Q and R
   - May need adjustment with better physiological data
   - Current values based on literature review

4. **Not Real-Time**: Batch processing only
   - Cannot update incrementally (without storing full state)
   - Must reprocess full date range

### Rationale

The Kalman filter is the **"gold standard" method** for this problem because:
- Exponential smoothing lacks proper uncertainty propagation
- Simple averages introduce unacceptable lag and edge effects
- Raw data is too noisy for reliable parameter estimation
- Dynamic gain adaptation is critical for handling variable data quality

### Validation Results

**Test Mode (Sept 9-11, 2025):**
```
Parameters: Q = 0.0196, R = 2.89
Initial state: x̂₀ = 20.520 kg, P₀ = 2.890 kg²

Day 1: K_t = 0.500000, x̂_t = 20.520 kg, P_t = 1.445 kg²
Day 2: K_t = 0.336334, x̂_t = 20.315 kg, P_t = 0.972 kg²
Day 3: K_t = 0.255463, x̂_t = 20.891 kg, P_t = 0.738 kg²

✅ Kalman gain in [0,1]: 0.255463 to 0.500000
✅ Gain decreases with consecutive measurements: True
✅ Covariance decreases with consecutive measurements: True
✅ Performance: 79.0% noise reduction
```

**Production Results (Sept 1-28, 2025):**
- Raw data: 24 measurements, stddev = 0.902 kg
- Filtered data: 28 days (fills gaps), stddev = 0.387 kg
- Improvement: 57.0% reduction in noise
- Kalman gain range: 0.087686 to 0.500000 (properly dynamic)

## Related Documents

- [ADR-0002: Modeling Data Preparation](./0002-modeling-data-prep.md) - Window generation using filtered data
- [Schema: daily_facts_filtered](../../schema.manifest.yaml) - Output table definition
- Implementation: `etl/kalman_filter.py`

## References

1. Kalman, R.E. (1960). "A New Approach to Linear Filtering and Prediction Problems"
2. Welch & Bishop (2006). "An Introduction to the Kalman Filter"
3. BIA measurement error: Literature review (2025-09-30)
4. Physiological fat oxidation limits: Calorimetry studies

