# Health Agentic Workflow MVP

A data-driven health coaching system that combines multiple data sources (Withings, MyFitnessPal, TrainingPeaks) to provide personalized weekly coaching recommendations through parameterized models and human-in-the-loop decision making.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-13+-blue.svg)](https://www.postgresql.org/)

## 🎯 Overview

This MVP demonstrates an agentic workflow for health coaching that:
- **Ingests data** from multiple health and fitness sources
- **Applies versioned models** for reproducible fat mass predictions  
- **Generates weekly snapshots** for human review and decision making
- **Maintains audit trails** for continuous learning and improvement

## 📚 Documentation

- **[SCHEMA.md](docs/SCHEMA.md)**: Complete database schema with tables, views, relationships, and business rules
- **[UI-MFP-Weekly.md](docs/UI-MFP-Weekly.md)**: User interface specification for Weekly Process Discipline (v1.0)
- **[ADR/](docs/adr/)**: Architecture Decision Records documenting key design decisions
  - `0001-params-and-materialized-series.md`: Versioned parameters and materialized daily series
  - `0001-apple-health-router.md`: Apple Health data routing decisions
  - `0002-modeling-data-prep.md`: Data preparation for modeling

## 🚀 Quick Start

1. **Database Setup**: Run migrations in `sql/migrations/`
2. **Data Ingestion**: Load sample data from `data/` directory  
3. **Parameter Fitting**: Use `tools/p1_fit_params.py` for model calibration
4. **Weekly Process**: Follow UI workflow in `docs/UI-MFP-Weekly.md`

## 🏗️ Architecture

- **Data Layer**: PostgreSQL with materialized views for performance
- **Processing**: Python tools for data cleaning, modeling, and analysis
- **Validation**: Schema contracts and data quality checks
- **Documentation**: Comprehensive schema manifest and ADRs

## 📊 Key Features

- **Multi-source Integration**: Withings, MyFitnessPal, TrainingPeaks
- **Parameter Versioning**: Reproducible model calculations
- **Weekly Snapshots**: Immutable coaching decision records
- **Data Quality**: Automated validation and imputation
- **Audit Trails**: Complete decision history for learning

## 🛠️ Development

- **Schema Management**: `schema.manifest.yaml` defines complete data model
- **Migrations**: Versioned SQL migrations in `sql/migrations/`
- **Validation**: Pre-flight checks prevent runtime errors
- **Testing**: Comprehensive test suite for data quality

## 📈 Status

- **Current Version**: 0.2.0
- **Schema**: Complete with coaching tables and materialized series
- **Documentation**: Comprehensive technical and user documentation
- **Open Source**: Ready for community contribution

## 🤝 Contributing

This project is designed for open-source contribution. See `docs/README.md` for detailed contribution guidelines.

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details.
