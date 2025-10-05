# P0/P1 Historical Artifacts Archive

This directory contains preserved artifacts from the P0/P1 modeling system for historical reference.

## Artifacts Preserved

### **Code Artifacts**
- `tools/p1_fit_params.py` - Parameter estimation via grid search
- `tools/p1_eval.py` - Model evaluation and diagnostics  
- `tools/p1_residuals.py` - Residual analysis and visualization
- `tools/p1_model.py` - Model implementation

### **Data Artifacts**
- `p0_staging.csv` - Original spreadsheet data (manually curated)
- `p1_train_windows_flex7.csv` - Training windows (866 windows)
- `p1_test_windows_flex7.csv` - Test windows
- `config/p1_params.yaml` - Final fitted parameters

### **Documentation Artifacts**
- `docs/adr/0002-modeling-data-prep.md` - Data preparation decisions
- `docs/HISTORICAL-MODELING.md` - Modeling approach documentation
- `docs/DEPRECATED.md` - Deprecation notice

### **Results Artifacts**
- Parameter estimates: M=1400, C=0.50, α=9500
- Performance metrics: R²=0.72, MAE=0.31 kg
- Confidence intervals and validation results

## Historical Context

These artifacts represent the initial energy balance modeling system developed in September 2025. While superseded by the P2 system with Kalman filtering and TEF integration, they provide crucial historical context for:

1. **Model Evolution**: How the current system evolved from simpler approaches
2. **Parameter Validation**: Baseline performance metrics for comparison
3. **Data Quality Insights**: Lessons learned about BIA noise and preprocessing
4. **Methodology Development**: Foundation for current modeling approaches

## Usage

These artifacts are preserved for:
- **Historical reference** - Understanding system evolution
- **Research purposes** - Comparing P0/P1 vs P2 approaches  
- **Audit trails** - Complete record of modeling decisions
- **Educational value** - Learning from initial implementation

**Note**: These artifacts should NOT be used for current operations. Use `daily_facts` and `model_params_timevarying` for current modeling.
