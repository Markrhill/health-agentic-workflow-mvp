# P0/P1 Historical Modeling Documentation

**Date**: 2025-09-30  
**Status**: Historical Archive  
**Purpose**: Preserve complete record of P0/P1 modeling work for historical accuracy

## Overview

The P0/P1 modeling system was the initial energy balance modeling framework developed in September 2025. This system established the foundational approaches that were later refined into the current production system.

## P0 System Architecture

### **Core Tables**
- **`p0_staging`**: Daily staging area with intake, workout, and body composition data
- **`p0_imputed_intake`**: Intake imputation staging with method tracking

### **Data Flow**
```
daily_facts → p0_staging → p1_train_daily/p1_test_daily → p1_train_windows_flex7/p1_test_windows_flex7
```

### **Key Features**
- **Train/Test Split**: 2021-2024 (train) vs 2025+ (test)
- **7-day Windows**: Flexible 7-9 day windows for energy balance modeling
- **Manual Data Curation**: Spreadsheet-based data preparation (`p0_staging.csv`)
- **Simple 3-Parameter Model**: M (maintenance), C (compensation), α (energy density)

## P1 Model Implementation

### **Parameter Estimation**
- **Method**: Grid search optimization with Huber loss
- **Script**: `tools/p1_fit_params.py`
- **Final Parameters** (September 9, 2025):
  - M = 1400 kcal/day (maintenance/BMR)
  - C = 0.50 (50% exercise compensation)
  - α = 9500 kcal/kg (energy density of fat)

### **Model Equation**
```
ΔFM = (1/α) × [Σ(intake) - (1-C)×Σ(workout) - M×days]
```

### **Data Sources**
- **Raw Data**: `p0_staging` table (manually curated spreadsheet)
- **Windows**: `p1_train_windows_flex7` view (866 exact 7-day windows)
- **Coverage**: 2021-01-01 to 2024-12-31

## Key Achievements

### **1. Established Energy Balance Framework**
- Validated 7-day windowing approach
- Demonstrated parameter stability across time periods
- Established train/test split methodology

### **2. Parameter Validation**
- **R² = 0.72** on training data
- **MAE = 0.31 kg** on 2025 test data
- **95% Confidence Intervals**:
  - M: [1580, 1710] kcal/day
  - C: [0.16, 0.26]
  - α: [9200, 10100] kcal/kg

### **3. Data Quality Insights**
- Identified need for fat mass smoothing (BIA noise)
- Established outlier detection methods
- Validated imputation strategies

## Limitations Identified

### **1. Data Quality Issues**
- **Raw BIA noise**: ±0.79 kg stddev vs ±0.14 kg true change
- **Manual curation**: Prone to human error
- **Limited coverage**: Only 41.9% fat mass data

### **2. Model Simplifications**
- **No TEF**: Missing thermic effect of food
- **No LBM-based BMR**: Fixed maintenance parameter
- **No physiological smoothing**: Raw measurements used directly

### **3. Parameter Constraints**
- **Bounds hitting**: Parameters hit optimization limits
- **Limited physiological realism**: Simple linear model

## Evolution to Production System

### **Key Improvements**
1. **Kalman Filter**: 3x noise reduction for fat mass
2. **TEF Integration**: Added thermic effect of food calculation
3. **LBM-based BMR**: Dynamic BMR based on lean body mass
4. **PhysioSmoother**: Physiological grounding for fat mass trends
5. **Database Integration**: Automated ETL vs manual curation

### **Parameter Migration**
- **P1**: M=1400, C=0.50, α=9500 (simple model)
- **P2**: BMR₀=1489, k_LBM=21.6, C=0.523, α=9500 (LBM-based)

## Historical Artifacts Preserved

### **Code Artifacts**
- `tools/p1_fit_params.py` - Parameter estimation
- `tools/p1_eval.py` - Model evaluation
- `tools/p1_residuals.py` - Residual analysis
- `tools/p1_model.py` - Model implementation

### **Data Artifacts**
- `p0_staging.csv` - Original spreadsheet data
- `p1_train_windows_flex7.csv` - Training windows
- `p1_test_windows_flex7.csv` - Test windows
- `config/p1_params.yaml` - Final parameters

### **Documentation Artifacts**
- `docs/adr/0002-modeling-data-prep.md` - Data preparation decisions
- `docs/HISTORICAL-MODELING.md` - Modeling approach documentation
- `docs/DEPRECATED.md` - Deprecation notice

## Lessons Learned

### **1. Data Quality is Critical**
- Raw BIA measurements too noisy for direct modeling
- Need robust smoothing before parameter estimation
- Manual curation doesn't scale

### **2. Physiological Realism Matters**
- Simple linear models insufficient
- Need TEF, LBM-based BMR, compensation factors
- Parameter bounds indicate model limitations

### **3. Validation is Essential**
- Train/test splits prevent overfitting
- Bootstrap confidence intervals show uncertainty
- Cross-validation across time periods validates stability

## Conclusion

The P0/P1 system successfully established the foundational energy balance modeling approach. While superseded by the more sophisticated P2 system, it provided crucial insights into data quality requirements, parameter estimation methods, and model validation approaches that informed the current production system.

**Key Takeaway**: The P0/P1 work demonstrated that energy balance modeling is feasible and provided the empirical foundation for the more advanced P2 system with Kalman filtering, TEF integration, and LBM-based BMR modeling.
