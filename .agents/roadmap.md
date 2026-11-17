# Weekend Execution Plan & Empirical Verification Audit

## 1. Execution Status (All Steps Completed & Verified)
- [x] **Step 1 (`dlt` Ingestion):** Loaded `FOCUS-1.0/focus_sample_100000.csv.gz` (100,000 rows) and 3 consecutive months of raw AWS Workshop CUR Parquet files (`Oct2018`, `Nov2018`, `Dec2018` = 334,911 unsampled rows) into `finops_raw` via `ingestion/load_finops_data.py`.
- [x] **Step 2 (Conformed Staging, UTC Enforcement & Tag Attribution):** Implemented `stg_focus_cost.sql`, `stg_aws_cur_cost.sql`, `aws_cur_effective_cost.sql`, and `cross_db_helpers.sql`.
- [x] **Step 3 (Conformed Incremental Daily Cost Mart & FinOps KPI Summary):** Materialized `fct_cloud_cost_daily.sql` (35,165 conformed daily slice rows across `FOCUS_1.0` and `AWS_CUR`) and `mrt_finops_kpis_summary.sql` (tag coverage, commitment coverage, unused waste, and Effective Savings Rate).
- [x] **Step 4 (FOCUS Conformance, Savings Range Bounds & Reconciliation Tests):** All 39 dbt nodes (`8 models, 3 seeds, 28 data tests`) pass (`PASS=39 WARN=0 ERROR=0`).
- [x] **Step 5 (Seed-Backed Savings Ranges & Segment Margin Models):** Materialized `mrt_savings_opportunities.sql` joined to `seed_finops_savings_assumptions.csv` (5 opportunities with `low / base / high` monthly estimates and official AWS doc URLs) and `mrt_segment_unit_economics.sql` (10 AWS accounts with pro-rata shared cost allocation and `is_synthetic_revenue = true`).
- [x] **Steps 6-7 (Rolling Median + MAD with Persistence Rule & Backtest):** Executed `analysis/spike_and_forecast_eval.py` against both the 30-day FOCUS AWS series and the 92-day unsampled AWS CUR series.

---

## 2. Key Empirical Findings & Bugs Caught During Execution

### A. Composite Primary Key Trap in Raw AWS CUR (`000040-CUR`)
* In `Dec2018-WorkshopCUR-00001.snappy.parquet` (91,264 rows), `identity_line_item_id` has only **770 distinct values** because AWS CUR reuses the same line item ID across hourly intervals (`identity_time_interval`) within a billing period.
* Using `primary_key="identity_line_item_id"` alone would have deduplicated 91,264 rows down to 770. Configuring `primary_key=["identity_line_item_id", "identity_time_interval"]` in `dlt` preserved all **334,911 rows** across Oct, Nov, and Dec 2018.

### B. Local Timezone Leakage Across Monthly Billing Boundaries
* `dlt` loads timestamp columns into PostgreSQL as `timestamp with time zone` (UTC). When the database session runs in a non-UTC timezone (`+07:00`), a plain `CAST(charge_period_start AS DATE)` shifts hourly usage between `17:00 UTC` and `23:00 UTC` on September 30 into October 1 (`2024-10-01`).
* Enforcing `cast((cast(col as timestamptz) at time zone 'UTC') as date)` on PostgreSQL and `date(cast(col as timestamp), 'UTC')` on BigQuery in `macros/cross_db_helpers.sql` eliminated cross-month date leakage and restored exact 30-day (`2024-09-01`..`2024-09-30`) and 92-day (`2018-10-01`..`2018-12-31`) boundaries.

### C. Reconciliation Audit Results (`fct_cost_reconciliation_audit`)
1. **3-Month Raw AWS CUR (`334,911 rows`):**
   * `2018-10-01` (119,307 rows): `Unblended = 4,064.48`, `Amortized = 4,195.95`, `Reconciliation Diff = 0.000012` (`$0.00`).
   * `2018-11-01` (124,340 rows): `Unblended = 3,505.33`, `Amortized = 3,632.56`, `Reconciliation Diff = -0.000002` (`$0.00`).
   * `2018-12-01` (91,264 rows): `Unblended = 408.37`, `Amortized = 539.85`, `Reconciliation Diff = 0.000000` (`$0.00`).
2. **FOCUS 1.0 Standard Usage Rounding Audit:**
   * **Microsoft Standard Usage (4,949 rows):** `BilledCost = 567.2103`, `EffectiveCost = 567.2103` (`Raw Variance = 0.0000`).
   * **AWS Standard Usage (93,749 rows):** `BilledCost = 2,026.5696`, `EffectiveCost = 1,484.3200` (`Raw Variance = 542.2496`). Of the 93,749 rows, **93,738 rows** satisfy `EffectiveCost = ROUND(BilledCost, 0)` (accounting for `541.5696` of integer-rounding loss), leaving only `0.6800` across 7 Marketplace rows.
