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

### D. Range-Based Savings Opportunities (`mrt_savings_opportunities`)
1. `1_ec2_savings_plan_floor_sizing`: `$372.59/mo` addressable p10 On-Demand floor -> `$74.52` low (20%) / `$104.33` base (28%) / `$130.41` high (35%) monthly savings (`https://aws.amazon.com/savingsplans/compute-pricing/`).
2. `2_dev_gpu_offhours_scheduling`: `$557.49/mo` addressable `environment = 'dev'` GPU spend (374 rows) -> `$195.12` low (35%) / `$278.75` base (50%) / `$356.79` high (64%) monthly savings (`https://docs.aws.amazon.com/solutions/latest/instance-scheduler-on-aws/solution-overview.html`).
3. `3_vpc_idle_public_ipv4_release`: `$1.22/mo` unattached `Idle public IPv4` spend -> `$1.10` low (90%) / `$1.22` base (100%) / `$1.22` high (100%) monthly savings (`https://aws.amazon.com/blogs/aws/new-aws-public-ipv4-address-charge-public-ip-insights/`).
4. `4_s3_egress_transfer_reduction`: `$4.02/mo` S3 transfer spend (`$3.80` internet egress + `$0.21` cross-region transfer) -> `$0.80` low (20%) / `$1.61` base (40%) / `$2.41` high (60%) monthly savings via CloudFront CDN caching, compression, and same-region compute co-location (`https://aws.amazon.com/s3/pricing/`).
5. `5_cur_reserved_instance_unused_waste`: `$48.36/mo` normalized monthly unused RI commitment waste (`$145.09` across Oct-Dec 2018) -> `$24.18` low (50%) / `$36.27` base (75%) / `$42.56` high (88%, net of 12% RI Marketplace fee) monthly savings (`https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ri-Modifying.html`).

### E. Config-Driven Anomaly Detection & Dynamic Backtest (`analysis/config.yaml`, `analysis/spike_and_forecast_eval.py`)
* Hyperparameters and backtest settings configured in `analysis/config.yaml` (`window_size_days: 7`, `z_score_threshold: 3.0`, `persistence_consecutive_days: 3`, `mad_scale_floor_pct: 0.05`, `ewma_smoothing_alpha: 0.45`, `post_spike_eval_window_days: 5`, `trailing_holdout_ratio: 0.15`).
* **Dynamic Post-Spike Recovery Window (`2024-09-10` to `2024-09-23`, 6 evaluated days):**
  * 7-Day Rolling Rule of Thumb MAE (`$15.83/day`) outperforms the reactive EWMA model (`$20.26/day`).
* **Dynamic Workload Step-Change Window (`2024-09-11` to `2024-09-26`, 7 evaluated days):**
  * The **Regime-Aware EWMA Model** (`$35.67/day`) significantly outperforms the naive rolling mean (`$46.66/day`) and spike-stripped median (`$55.26/day`).
* **Dynamic Trailing Out-of-Sample Holdout on Unsampled CUR (`2018-12-19` to `2018-12-31`, 13 evaluated days):**
  * Regime-Aware EWMA Model MAE (`$0.40/day`) outperforms naive rolling mean (`$0.57/day`) and spike-stripped median (`$0.47/day`).

### F. Dedicated Action Impact & Technical Audit Reports
* **Action Impact Report (`analysis/reports/impact_report.md`)**: Strips out technical data engineering clutter and directly reports the problem, solve action, department owner, and expected savings ($ and %) across all 5 rate and usage optimization levers.
* **Technical Audit Report (`analysis/reports/pipeline_audit_report.md`)**: Details hyperparameter configurations, FinOps governance targets, reconciliation audit down to $0.00, rounding variance, and dynamic regime backtest MAE results.
