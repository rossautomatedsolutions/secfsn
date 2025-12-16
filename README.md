# SEC FSN — SEC Financial Statements & Notes Pipeline

SEC FSN is a Python-based data engineering and analytics library for working with SEC EDGAR Financial Statements & Notes (FSN) data.

This project focuses on:
- Robust ingestion and validation of SEC filings
- Efficient transformation using Polars
- Clean, analytics-ready fundamentals panels
- Practical examples for research, screening, Excel (PyXLL), and Plotly


---

## Key Features

### End-to-end FSN data pipeline
- Download and preprocess SEC FSN datasets
- Convert TSV → Parquet
- Combine quarterly and monthly releases
- Validate schema, coverage, and file integrity

### High-performance fundamentals engine
- Built on Polars, surfaced as Pandas
- Multi-period fundamentals panels
- Derived metrics (margins, ROE, ROA, leverage)
- YoY, TTM, and delta calculations

### Practical analytics examples
- Company comparisons
- Value screening & ranking
- Rolling TTM metrics
- Interactive Plotly visualizations (heatmaps, scatter plots, waterfall / P&L bridges)

### Excel integration (PyXLL)
- Load fundamentals directly into Excel
- Apply screeners and rankings from Python
- Return clean, formatted DataFrames for spreadsheet analysis

---

## Project Structure

```text
secfsn/
├── Notebooks/
│   └── 01 FSN Data Engineering & Fundamentals.ipynb
├── common/
│   ├── logging_utils.py
│   └── timing.py
├── config/
│   ├── constants.py
│   ├── core.py
│   └── logging.py
├── engine/
│   ├── loader.py
│   ├── polars_engine.py
│   └── screener.py
├── fsn/
│   ├── downloader.py
│   ├── pipeline.py
│   ├── quarter_combiner.py
│   ├── tsv_to_parquet.py
│   └── utils.py
├── monitoring/
│   ├── audit_periods.py
│   ├── integrity.py
│   ├── run_checks.py
│   ├── validate_files.py
│   └── validate_fundamentals.py
├── scripts/
│   └── run_screener_example.py
├── .gitignore
└── README.md
```


## Notebook Walkthrough

The primary notebook, `01 FSN Data Engineering & Fundamentals.ipynb`, demonstrates the full workflow end-to-end.

### Section I — Data Engineering & Validation
- Running the FSN download and preprocessing pipeline
- Validating file presence, schema consistency, and period coverage
- Inspecting raw and processed datasets
- Building single-period fundamentals using Polars

### Section II — Fundamentals Analytics
- Multi-period fundamentals panels
- Rolling TTM calculations (based on filings, not strict accounting quarters)
- Company-level comparisons
- Value screening and ranking examples

### Section III — Excel (PyXLL) Examples
- Returning fundamentals to Excel as DataFrame handles
- Applying screeners and rankings from Excel
- Formatting numeric outputs for spreadsheet consumption

### Section IV — Visualization with Plotly
- ROE vs ROA density heatmaps
- Profitability and fundamentals scatter plots
- Interactive company exploration
- P&L waterfall / bridge charts

---

## Inspiration & Attribution

The early ideas and exploratory approach for this project were heavily inspired by the EDGAR and feature engineering notebooks from:

Stefan Jansen — *Machine Learning for Algorithmic Trading*

In particular:
- The EDGAR / XBRL exploration notebook informed the initial data access patterns
- The feature engineering notebook influenced later ideas around fundamentals panels and derived metrics

This project extends those concepts into:
- a structured FSN pipeline
- Polars-based transformation workflows
- Excel (PyXLL) and Plotly integrations
- reusable screening and analytics tooling

All inspiration is acknowledged with respect and appreciation.

---

Blog posts: [link here]  
Demo video: [link here]
