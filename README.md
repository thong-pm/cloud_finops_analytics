# Cloud FinOps Cost, Amortization & Anomaly Pipeline

## Problem Statement
Cloud billing exports across FinOps Foundation FOCUS 1.0 and raw AWS Cost and Usage Reports (CUR) use different schemas and mix cash-basis charges (`BilledCost` / `line_item_unblended_cost`), accrual-basis commitment consumption (`EffectiveCost` / amortized cost), and lumpy promotional or enterprise discount credits (`ChargeCategory = 'Credit'`).

Directly aggregating raw billing rows distorts unit economics and breaks standard mean/standard-deviation anomaly alerts whenever a one-off migration spike, workload step-change, or bulk credit lands.

## Architecture & Separation of Concerns

### 1. Conformed Billing Ingestion & Staging (`dlt` + `dbt Core`)
- `ingestion/load_finops_data.py`: `dlt` pipeline streaming FinOps Foundation FOCUS 1.0 exports (`focus_cost_export`, keyed on `Id`) and multi-month raw AWS CUR Parquet files (`aws_cur_export`, keyed on composite `["identity_line_item_id", "identity_time_interval"]`) in batches into PostgreSQL (`local`), DuckDB, or BigQuery (`dev` / `prod`).
- `dbt_finops/models/staging/`: Maps distinct billing formats into a single conformed FOCUS-aligned schema:
  - `stg_focus_cost.sql`: Normalizes FOCUS 1.0 records, cleans string `'NULL'` literals, extracts JSON tags (`application`, `environment`, `business_unit`), and flags untagged spend (`is_untagged`).
  - `stg_aws_cur_cost.sql`: Stages raw AWS CUR Parquet records, applies the 7-branch commitment amortization macros, and isolates unused Reserved Instance fees (`RIFee`).
- `dbt_finops/macros/aws_cur_effective_cost.sql`: Implements `aws_cur_amortized_cost` and `aws_cur_net_amortized_cost` across all 7 AWS CUR commitment line-item branches (`SavingsPlanCoveredUsage`, `SavingsPlanRecurringFee`, `SavingsPlanNegation`, `SavingsPlanUpfrontFee`, `DiscountedUsage`, `RIFee`, and Reserved Instance `Fee`).
- `dbt_finops/macros/cross_db_helpers.sql`: Enforces explicit UTC date extraction (`AT TIME ZONE 'UTC'` on PostgreSQL, `DATE(CAST(col AS TIMESTAMP), 'UTC')` on BigQuery) so local session timezones do not shift late-night UTC usage across monthly billing boundaries.

### 2. Standard FinOps Outputs (`dbt_finops/models/marts/`)
- `fct_cloud_cost_daily.sql`: Conformed daily cost mart uniting FOCUS 1.0 and raw AWS CUR by `dataset_source`, `charge_date`, `provider_name`, `sub_account_id`, `service_name`, `charge_category`, `pricing_category`, `commitment_discount_type`, and extracted resource tags (`tag_application`, `tag_environment`, `tag_business_unit`, `is_untagged`).
- `mrt_finops_kpis_summary.sql`: Standard FinOps KPI table reporting:
  - Cost by dataset and provider (cash vs amortized effective spend).
  - Tag coverage (`tagged_usage_spend_usd`, `untagged_usage_spend_usd`, `tag_coverage_pct`).
  - Commitment coverage and utilization (`commitment_covered_list_cost_usd`, `ondemand_list_cost_usd`, `commitment_coverage_pct`, `unused_commitment_waste_usd`).
  - Effective Savings Rate (`effective_savings_rate_pct` computed from list vs effective cost on commitment-covered usage).
- `mrt_segment_unit_economics.sql`: Customer segment margin model joining direct sub-account usage and pro-rata allocated shared infrastructure spend against a labeled synthetic revenue seed (`is_synthetic_revenue = true`).

### 3. Savings Opportunities & Segment Margins
- Quantifies initial rate and usage optimization opportunities across EC2, dev GPU scheduling, and S3 transfer.
- Materializes mrt_segment_unit_economics.sql joining customer segments against pro-rata infrastructure spend.

### 4. Tests, FOCUS Conformance & Source-to-Mart Reconciliation
- `fct_cost_reconciliation_audit.sql`: Audits cash vs amortized totals across `FOCUS_1.0` and `AWS_CUR_2018`, isolating upstream FOCUS integer-rounding loss from commitment amortization timing differences.
- `dbt_finops/tests/`:
  - `assert_focus_spec_conformance.sql`: Validates FOCUS 1.0 mandatory fields, allowed `ChargeCategory` and `PricingCategory` domain values, and UTC billing period boundaries on `fct_cloud_cost_daily`.
  - `assert_cur_macro_all_7_branches.sql`: Verifies `aws_cur_amortized_cost` and `aws_cur_net_amortized_cost` against `seed_aws_cur_all_types.csv` across all 7 AWS commitment line-item types.
  - `assert_aws_cur_3month_reconciliation.sql`: Asserts zero unaccounted variance between raw AWS CUR unblended + amortized upfront fees and modeled `amortized_cost` across each billing month.
  - `assert_focus_reconciliation_with_rounding_audit.sql`: Verifies FOCUS 1.0 Standard Usage reconciliation and isolates upstream integer-rounding rows.
  - `assert_savings_ranges_and_bounds.sql`: Asserts `0 <= low <= base <= high <= monthly_addressable_spend_usd <= current_spend_or_list_exposure_usd` and verifies documentation URLs.

### 5. Statistical Anomaly Detection & Forecast Backtest
- Applies Rolling Median + MAD detector with 3-day persistence rule on FOCUS and raw AWS CUR datasets.
- Evaluates post-spike and workload step-change windows comparing rolling rule-of-thumb against EWMA model.

## Scale & Warehouse Design
Billing exports in multi-account organizations scale to tens of millions of rows per month. The pipeline handles volume through:
- **Streaming Chunked Ingestion:** `ingestion/load_finops_data.py` streams gzipped CSVs and PyArrow Parquet record batches in fixed-size chunks rather than loading full files into memory.
- **Daily Time-Unit Partitioning & Clustering:** `fct_cloud_cost_daily.sql` is configured with daily partitioning on `charge_date` and clustering on `provider_name, sub_account_id, service_name, charge_category` on BigQuery to prune partition scans on date-bounded and service-filtered queries.
- **Incremental Materialization:** `fct_cloud_cost_daily.sql` uses `insert_overwrite` on BigQuery and `delete+insert` on PostgreSQL with `on_schema_change='sync_all_columns'`, reprocessing only partitions from the latest `charge_date` watermark during incremental runs.

## Data Provenance & Production Deployment Differences
- **What is public sample data:**
  - `focus_cost_export` comes from the FinOps Foundation FOCUS 1.0 open sample dataset (`focus_sample_100000.csv.gz`).
  - `aws_cur_export` comes from the AWS Well-Architected Workshop multi-month unsampled CUR Parquet files (`000040-CUR`).
- **What is seeded / estimated:**
  - `seed_finops_savings_assumptions.csv` contains explicit low/base/high engineering reduction factors linked to AWS pricing documentation; savings figures in `mrt_savings_opportunities` are modeled estimates under those stated assumptions, not realized post-change invoices.
  - `seed_synthetic_segment_revenue.csv` contains synthetic segment revenue (`is_synthetic_revenue = true`) to demonstrate unit-economics margin joins.
- **What changes on live production billing data:**
  - **Event-Driven Partition Loading:** Replace HTTP file downloads in `load_finops_data.py` with S3 EventBridge triggers (for AWS Data Exports CUR 2.0 Parquet partitions), passing a `--billing-period` watermark to `dlt` so only newly delivered invoice partitions are merged.
  - **Lookback Window for Late-Arriving Charges:** In `fct_cloud_cost_daily.sql`, replace the `max(charge_date)` incremental filter with a rolling 35-day lookback window (`charge_date >= current_date - 35`) because cloud providers restate current-month support fees, credits, and RI/SP reallocations until invoice finalization.
  - **Account & Tag Governance:** Join against AWS Organizations account metadata and AWS Cost Categories rather than relying solely on resource-level JSON tags.
  - **Right-Sizing Telemetry:** Join billing rows with CPU/GPU/memory utilization metrics from AWS Compute Optimizer or CloudWatch before sizing instance family or scheduling changes.

## CLI Usage
1. Configure environment variables (see `.env.example`):
   ```bash
   export PG_HOST=localhost PG_PORT=5432 PG_USER=your_user PG_PASSWORD=your_password PG_DATABASE=your_db
   ```
2. Run the full pipeline (`dlt` ingestion -> `dbt build` -> statistical evaluation):
   ```bash
   bash pipeline.sh local
   ```
3. Run individual steps:
   ```bash
   .venv/bin/python ingestion/load_finops_data.py --destination postgres --dataset finops_raw
   cd dbt_finops && ../.venv/bin/dbt build --profiles-dir . --target local
   .venv/bin/python analysis/spike_and_forecast_eval.py
   ```

## Roadmap & Status
- [x] Step 1: `dlt` ingestion for FOCUS 1.0 (`focus_cost_export`) and multi-month raw AWS CUR Parquet (`aws_cur_export`)
- [x] Step 2: Conformed staging (`stg_focus_cost`, `stg_aws_cur_cost`), UTC boundary enforcement, and 7-branch CUR amortization macros
- [x] Step 3: Incremental partitioned/clustered daily cost mart (`fct_cloud_cost_daily`) and FinOps KPI summary (`mrt_finops_kpis_summary`)
- [x] Step 4: Automated FOCUS spec conformance, savings range bound checks, and source-to-mart reconciliation tests (`fct_cost_reconciliation_audit`)
- [x] Step 5: Seed-driven low/base/high savings opportunities (`seed_finops_savings_assumptions` -> `mrt_savings_opportunities`) and labeled synthetic segment margin mart (`mrt_segment_unit_economics`)
- [x] Step 6: Rolling Median + MAD anomaly detector with 3-day persistence re-anchoring (`analysis/spike_and_forecast_eval.py`)
- [x] Step 7: Rule-of-thumb vs regime-aware EWMA backtest across stationary and step-change windows
