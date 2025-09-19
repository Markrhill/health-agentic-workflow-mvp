# Health Agentic Workflow MVP - Project Structure

## 📁 Directory Overview

```
health-agentic-workflow-mvp/
├── 📄 README.md                           # Project overview and quick start
├── 📄 CHANGELOG.md                        # Version history and changes
├── 📄 schema.manifest.yaml                # Complete database schema definition
├── 📄 project-structure.txt               # Generated file listing
├── 📄 project-tree.txt                    # Generated directory tree
│
├── 📁 config/                             # Configuration files
│   └── p1_params.yaml                     # Model parameters
│
├── 📁 data/                               # Data storage
│   ├── archive/                           # Historical data backups
│   │   └── p1_test_metrics_20250908_2144.json
│   └── p1_test_metrics.json               # Current test metrics
│
├── 📁 docs/                               # Comprehensive documentation
│   ├── README.md                          # Documentation overview
│   ├── SCHEMA.md                          # Database schema documentation
│   ├── UI-MFP-Weekly.md                  # User interface specifications
│   └── adr/                               # Architecture Decision Records
│       ├── 0001-apple-health-router.md
│       ├── 0001-params-and-materialized-series.md
│       └── 0002-modeling-data-prep.md
│
├── 📁 sql/                                # Database migrations
│   └── migrations/                        # Versioned SQL migrations
│       ├── 20250916_01_performance_goals.sql
│       ├── 20250916_02_model_params_timevarying.sql
│       ├── 20250916_03_daily_series_materialized.sql
│       ├── 20250916_04_weekly_coaching_snapshot.sql
│       ├── 20250916_05_audit_hil.sql
│       └── 20250916_06_facts_intake_dow_medians.sql
│
├── 📁 scripts/                            # Database and utility scripts
│   ├── detect_schema_drift.py             # Schema drift detection
│   ├── load_withings_raw.py               # Withings data ingestion
│   ├── preflight_schema_introspect.py     # Schema introspection
│   └── validate_schema.py                 # Pre-flight validation
│
├── 📁 tools/                              # Core processing tools
│   ├── p1_eval.py                         # Model evaluation
│   ├── p1_fit_params.py                   # Parameter fitting
│   ├── p1_fm_clean.py                     # Fat mass cleaning
│   ├── p1_fm_clean_protocol.py            # Cleaning protocol
│   ├── p1_model.py                        # Core model implementation
│   ├── p1_residuals.py                    # Residual analysis
│   └── p1_tv_l1_train.py                  # TV-L1 denoising training
│
├── 📁 ml/                                 # Machine learning utilities
│   ├── __init__.py
│   └── solver.py                          # Optimization solver
│
├── 📁 tests/                              # Test suite
│   └── py/
│       └── test_solver.py                 # Solver tests
│
├── 📁 notebooks/                          # Jupyter notebooks
│   └── README.md
│
├── 📁 figures/                            # Generated visualizations
│
├── 📁 backend/                            # Backend services
│   └── ingest/
│       └── hae_ingest_json.py             # Health data ingestion
│
└── 📁 .vscode/                            # VS Code configuration
    └── settings.json
```

## 🎯 Key Components

### **Core System**
- **Schema Management**: `schema.manifest.yaml` defines complete data model
- **Database Migrations**: Versioned SQL in `sql/migrations/`
- **Data Processing**: Python tools in `tools/` directory
- **Validation**: Pre-flight checks in `scripts/`

### **Documentation**
- **Technical Docs**: Complete schema and UI specifications
- **Architecture Decisions**: ADR pattern for design decisions
- **User Guides**: Clear onboarding and usage instructions

### **Data Flow**
1. **Ingestion**: Raw data → `backend/ingest/`
2. **Processing**: Data cleaning → `tools/`
3. **Modeling**: Parameter fitting → `tools/p1_*`
4. **Storage**: Database → `sql/migrations/`
5. **Analysis**: Evaluation → `tools/p1_eval.py`

## 🚀 Getting Started

1. **Database Setup**: Run migrations in `sql/migrations/`
2. **Data Ingestion**: Use scripts in `scripts/`
3. **Model Training**: Run tools in `tools/`
4. **Documentation**: Start with `docs/README.md`

## 📊 Project Stats

- **Total Files**: 35+ core files
- **Documentation**: 6 comprehensive docs
- **Database Objects**: 6 tables + 1 view
- **Python Tools**: 7 processing scripts
- **SQL Migrations**: 6 versioned migrations
- **Architecture Decisions**: 3 ADRs

## 🔧 Technology Stack

- **Database**: PostgreSQL with materialized views
- **Language**: Python 3.8+
- **Schema**: YAML manifest with validation
- **Migrations**: Versioned SQL
- **Documentation**: Markdown with Mermaid diagrams
- **Version Control**: Git with semantic versioning
