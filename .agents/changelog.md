# Architectural Changelog & Engineering Decisions Manual

A chronological record tracing operational triggers, architectural pivots, and technical executions in this repository.

---

## 1. Master Timeline Matrix

| Date | Milestone | Operational Problem / Trigger | Key Tech Implemented |
| :--- | :--- | :--- | :--- |
| **2026-11-14** | Repository Scaffold & Empirical Dataset Audit | Need an isolated repository to implement the FOCUS 1.0 + raw AWS CUR dbt pipeline, reconciliation tests, and Rolling Median + MAD forecast backtest | `dbt_finops/`, `macros/aws_cur_effective_cost.sql`, `.agents/roadmap.md` |
| **2026-11-14** | Full `dlt` + `dbt` Pipeline, Reconciliation Audit, Savings Marts & Persistence Backtest | Execute end-to-end ingestion, fix net-amortized CUR macro, enforce UTC billing boundaries, build incremental cost & margin marts, and verify statistical spike vs regime-shift models | `ingestion/load_finops_data.py`, `dbt_finops/models/`, `dbt_finops/tests/`, `analysis/spike_and_forecast_eval.py`, `pipeline.sh` |
| **2026-11-16** | Conformed CUR-to-FOCUS Daily Mart, Seed-Driven Savings Ranges, S3 Egress Fix & FOCUS Conformance Audit | Unify FOCUS 1.0 and raw AWS CUR into the conformed daily mart, replace hardcoded savings multipliers with a seed table of low/base/high ranges linked to AWS docs, normalize 3-month CUR waste to monthly rate, fix S3 internet egress vs VPC endpoint rationale, add FinOps KPI mart and FOCUS conformance tests | `seeds/seed_finops_savings_assumptions.csv`, `models/marts/fct_cloud_cost_daily.sql`, `models/marts/mrt_finops_kpis_summary.sql`, `models/marts/mrt_savings_opportunities.sql`, `tests/assert_focus_spec_conformance.sql`, `tests/assert_savings_ranges_and_bounds.sql`, `README.md` |
| **2026-11-17** | Centralized Anomaly/Backtest Config & Elimination of Hardcoded Evaluation Dates | Create `analysis/config.yaml`, eliminate hardcoded calendar dates and snapshot dollar strings from Python and dbt marts, parameterize SP floor percentile in `dbt_project.yml` vars, and implement dynamic regime evaluation | `analysis/config.yaml`, `analysis/spike_and_forecast_eval.py`, `dbt_finops/dbt_project.yml`, `models/marts/mrt_savings_opportunities.sql`, `README.md` |
| **2026-11-17** | Dynamic Markdown Run & Yield Report with Governance Targets | Expand `config.yaml` with governance targets, compile dynamic `latest_run_report.md` querying PostgreSQL marts, and surface report path in `pipeline.sh` | `analysis/config.yaml`, `analysis/spike_and_forecast_eval.py`, `analysis/reports/latest_run_report.md`, `pipeline.sh`, `README.md` |
| **2026-11-17** | Dedicated Database Provisioning & Local Environment Configuration | Provision `cloud_finops_db` for user `wsltest`, create gitignored `.env`, integrate `dotenv` loading in ingestion/analysis scripts, and verify standalone `bash pipeline.sh` execution | `.env`, `ingestion/load_finops_data.py`, `analysis/spike_and_forecast_eval.py`, `pipeline.sh` |
| **2026-11-17** | Separation of Action Impact Report & Technical Audit | Separate stakeholder action impact from data engineering audit, generating `impact_report.md` (problems, actions, savings in $ and % by dept) and `pipeline_audit_report.md` | `analysis/config.yaml`, `analysis/spike_and_forecast_eval.py`, `analysis/reports/impact_report.md`, `analysis/reports/pipeline_audit_report.md`, `pipeline.sh`, `README.md` |

---

## 2. Chronological Milestones & Execution Traceability

### Phase 1: Project Initialization & Weekend Plan Audit
* **Date**: November 14, 2026
* **Core Artifacts**: `README.md`, `.gitignore`, `dbt_finops/dbt_project.yml`, `dbt_finops/macros/aws_cur_effective_cost.sql`, `.agents/roadmap.md`
* **Repository Initialization & Plan Evaluation (`README.md`, `dbt_finops/`, `.agents/roadmap.md`)**:
  * **Original Request / Pivot**: Create a dedicated project repository in `My-Work` (`cloud_finops_analytics`) for the FinOps data engineering build and evaluate the Saturday (FOCUS + raw AWS CUR dbt mart & reconciliation) + Sunday (Rolling Median + MAD spike stripping & holdout backtest) execution plan against the actual sample datasets.
  * **Execution (`execute:`)**:
    * Created `/home/phamthong99/projects/My-Work/cloud_finops_analytics` with dedicated directories for `ingestion/`, `dbt_finops/` (`models/staging`, `models/marts`, `macros`, `tests`), `analysis/`, `data/`, and `.agents/`.
    * Added `dbt_finops/macros/aws_cur_effective_cost.sql` and documented the initial dataset audit in `.agents/roadmap.md`.

### Phase 2: End-to-End `dlt` Ingestion, `dbt` FinOps Marts, Reconciliation Tests & Regime-Aware Backtest
* **Date**: November 14, 2026
* **Core Artifacts**: `ingestion/load_finops_data.py`, `dbt_finops/profiles.yml`, `dbt_finops/macros/aws_cur_effective_cost.sql`, `dbt_finops/macros/cross_db_helpers.sql`, `dbt_finops/models/staging/`, `dbt_finops/models/marts/`, `dbt_finops/tests/`, `analysis/spike_and_forecast_eval.py`, `pipeline.sh`
* **Full Pipeline Implementation & Empirical Verification (`execute:`)**:
  * **Original Request / Pivot**: Use `dlt` to ingest both FOCUS 1.0 and raw AWS CUR datasets without relying on third-party cost platforms; fix the `SavingsPlanRecurringFee` branch in `aws_cur_net_amortized_cost` to match the AWS CUR Query Library formula; close the job description gaps (incremental modeling, JSON tag attribution, realized-dollar savings opportunities, and a clearly labeled synthetic revenue segment margin mart); and add a persistence rule to the Rolling Median + MAD detector so multi-day workload step-changes re-anchor the baseline rather than dividing by a zero MAD.
  * **Execution (`execute:`)**:
    * **Fixed `aws_cur_net_amortized_cost` (`dbt_finops/macros/aws_cur_effective_cost.sql`)**: Updated the `SavingsPlanRecurringFee` branch to `(total_commitment_to_date - used_commitment) * COALESCE(COALESCE(net_amortized_upfront, amortized_upfront) / NULLIF(amortized_upfront, 0), 1.0)` with `COALESCE(net_col, standard_col, 0)` fallbacks across all branches, and verified all 7 commitment line-item types via `seed_aws_cur_all_types.csv` and `tests/assert_cur_macro_all_7_branches.sql`.
    * **Built `dlt` Ingestion (`ingestion/load_finops_data.py`)**: Loaded 100,000 FOCUS 1.0 rows (`focus_cost_export`, keyed on `Id`) and 334,911 unsampled raw AWS CUR rows across Oct, Nov, and Dec 2018 (`aws_cur_export`, keyed on composite `["identity_line_item_id", "identity_time_interval"]` after verifying `identity_line_item_id` alone has only 770 distinct values per month) into PostgreSQL `finops_raw` in 17.76s.
    * **Fixed UTC Billing Boundary Leakage (`dbt_finops/macros/cross_db_helpers.sql`)**: Discovered that casting `timestamptz` columns to `DATE` in a `+07:00` local database session shifted `17:00-23:00 UTC` usage on Sept 30 into Oct 1 (`2024-10-01`). Enforced `cast((col at time zone 'UTC') as date)` on PostgreSQL and `date(col, 'UTC')` on BigQuery across all staging models.
    * **Built Staging & Mart Models (`dbt_finops/models/`)**:
      * `stg_focus_cost.sql` & `stg_aws_cur_cost.sql`: Normalized string `'NULL'` literals, extracted JSON `Tags` (`application`, `environment`, `business_unit`, `is_untagged`), and calculated amortized cost and unused RI waste.
      * `fct_cloud_cost_daily.sql`: Configured as an incremental model (`insert_overwrite` partitioned by `charge_date` and clustered on BigQuery; `delete+insert` on PostgreSQL) and verified both full-refresh (`33,278` rows) and incremental execution.
      * `fct_cost_reconciliation_audit.sql` & `tests/`: Verified `$0.0000` reconciliation across all 3 months of raw AWS CUR (`Oct2018`, `Nov2018`, `Dec2018`) and proved that `93,738` of `93,749` AWS Standard Usage rows in FOCUS 1.0 satisfy `EffectiveCost = ROUND(BilledCost, 0)` (`$541.57` rounding loss), while Microsoft Standard Usage reconciles to `$0.0000`. All 26 `dbt build` steps pass (`PASS=26 WARN=0 ERROR=0`).
      * `mrt_savings_opportunities.sql` & `mrt_segment_unit_economics.sql`: Quantified 5 savings cases and joined AWS account spend + pro-rata shared infrastructure cost against `seed_synthetic_segment_revenue.csv` (`is_synthetic_revenue = true`).
    * **Built Statistical Spike Detector & Backtest (`analysis/spike_and_forecast_eval.py`, `pipeline.sh`)**: Implemented Rolling Median + MAD (`z_threshold = 3.0`) with a 5% scale floor and a 3-day persistence rule (`regime_shift_reanchored`), demonstrating that the 7-day rolling rule of thumb wins in stationary post-spike windows (`$18.81/day` vs `$23.19/day` EWMA on Sept 19-23), while the regime-aware EWMA model wins during multi-day workload shifts (`$42.07/day` vs `$46.46/day` on FOCUS Sept 24-30; `$18.62/day` vs `$34.17/day` on CUR Oct 10-15; `$0.52/day` vs `$0.67/day` on CUR Dec 18-31).

### Phase 3: Conformed CUR-to-FOCUS Schema, Seed-Driven Savings Ranges, S3 Egress Fix & FOCUS Spec Conformance
* **Date**: November 16-17, 2026
* **Core Artifacts**: `dbt_finops/seeds/seed_finops_savings_assumptions.csv`, `dbt_finops/models/marts/fct_cloud_cost_daily.sql`, `dbt_finops/models/marts/mrt_finops_kpis_summary.sql`, `dbt_finops/models/marts/mrt_savings_opportunities.sql`, `dbt_finops/tests/`, `README.md`
* **FinOps Audit Remediation (`execute:`)**:
  * **Original Request / Pivot**: Address technical feedback on `mrt_savings_opportunities` and repository structure without adding synthetic GCP filler seeds: (1) unify `FOCUS_1.0` and raw `AWS_CUR` into one conformed schema in `fct_cloud_cost_daily`; (2) expose standard FinOps KPI outputs (cost by service/account/tag, tag coverage, commitment coverage/utilization, and Effective Savings Rate); (3) include automated FOCUS specification conformance and savings bound tests; (4) move hardcoded savings multipliers into a seed table (`seed_finops_savings_assumptions.csv`) with low/base/high ranges linked to official AWS documentation, normalize the 3-month CUR unused RI waste to a monthly rate, and fix the S3 egress engineering rationale (distinguishing internet egress and inter-region transfer from same-region S3 transfer); and (5) update `README.md` to document data provenance, production deployment differences, and warehouse partitioning/incremental scale design.
  * **Execution (`execute:`)**:
    * **Unified Conformed Schema (`fct_cloud_cost_daily.sql`)**: Unioned `stg_focus_cost` (`FOCUS_1.0`, 100,000 rows) and conformed `stg_aws_cur_cost` (`AWS_CUR`, 334,911 rows) into `fct_cloud_cost_daily` (`35,165` conformed daily slice rows) and removed synthetic GCP billing export seeds/models.
    * **Replaced Hardcoded Multipliers with Documented Seed Ranges (`seed_finops_savings_assumptions.csv`, `mrt_savings_opportunities.sql`)**: Removed hardcoded discount multipliers from SQL, joined against `seed_finops_savings_assumptions.csv` (`low_factor`, `base_factor`, `high_factor`, `aws_doc_url`), normalized all 5 levers by `COUNT(DISTINCT billing_period_date)` so 3-month AWS CUR unused RI waste (`$145.09`) is properly normalized to `$48.36/month` (`$24.18` low / `$36.27` base / `$42.56` high), and fixed the S3 transfer rationale to cite CloudFront CDN edge caching, object compression, and same-region compute co-location.
    * **Added Standard FinOps KPI Summary & Conformance Tests (`mrt_finops_kpis_summary.sql`, `assert_focus_spec_conformance.sql`, `assert_savings_ranges_and_bounds.sql`)**: Added a dedicated KPI mart reporting tag coverage, commitment coverage, unused commitment waste, and Effective Savings Rate across `FOCUS_1.0` and `AWS_CUR_2018`, and verified all 39 `dbt build` steps pass (`PASS=39 WARN=0 ERROR=0`).
    * **Updated `README.md`**: Documented the conformed schema, standard FinOps outputs, seed-backed savings ranges, scale mechanics (partitioning, clustering, incremental strategies), and production deployment differences.

### Phase 4: Centralized Anomaly/Backtest Config & Elimination of Hardcoded Evaluation Dates
* **Date**: November 17, 2026
* **Core Artifacts**: `analysis/config.yaml`, `analysis/spike_and_forecast_eval.py`, `dbt_finops/dbt_project.yml`, `dbt_finops/models/marts/mrt_savings_opportunities.sql`, `README.md`
* **Centralized Configuration & Dynamic Evaluation (`execute:`)**:
  * **Original Request / Pivot**: Centralize all assumptions into configuration files rather than hardcoding values across files; remove hardcoded calendar dates (`"2024-09-19"`, `"2024-09-23"`, `"2024-09-24"`, `"2024-09-30"`, `"2018-12-18"`, `"2018-12-31"`) and snapshot strings from `analysis/spike_and_forecast_eval.py` and `mrt_savings_opportunities.sql` so assumptions can be tweaked in one place without altering code.
  * **Execution (`execute:`)**:
    * **Created `analysis/config.yaml`**: Defined all anomaly detection hyperparameters (`window_size_days: 7`, `z_score_threshold: 3.0`, `persistence_consecutive_days: 3`, `mad_scale_floor_pct: 0.05`, `ewma_smoothing_alpha: 0.45`) and dynamic backtest evaluation settings (`post_spike_eval_window_days: 5`, `trailing_holdout_ratio: 0.15`).
    * **Dynamic Regime Evaluation in Python (`analysis/spike_and_forecast_eval.py`)**: Updated script to load `analysis/config.yaml` and dynamically evaluate (1) post-spike recovery windows (days immediately following stripped spikes), (2) confirmed persistent regime shifts, and (3) trailing out-of-sample holdout slices (`int(len(series) * trailing_holdout_ratio)`), eliminating all hardcoded calendar dates and hardcoded dollar strings.
    * **Parameterize dbt Vars & Clean Snapshot Texts (`dbt_project.yml`, `mrt_savings_opportunities.sql`)**: Exposed `sp_floor_percentile: 0.10` in `dbt_project.yml` vars and replaced point-in-time snapshot dollar figures and row counts in `engineering_rationale` and `scope` with clean invariant engineering descriptions.
    * **Verified**: Executed `dbt build` (`PASS=39 WARN=0 ERROR=0`) and `spike_and_forecast_eval.py` with zero errors.

### Phase 5: Dynamic Markdown Run & Yield Report with Governance Targets
* **Date**: November 17, 2026
* **Core Artifacts**: `analysis/config.yaml`, `analysis/spike_and_forecast_eval.py`, `analysis/reports/latest_run_report.md`, `pipeline.sh`, `README.md`
* **Dynamic Report Generation & Pipeline Yield (`execute:`)**:
  * **Original Request / Pivot**: Make the pipeline output a short, precise, comprehensive dynamic Markdown report (`latest_run_report.md`) whenever the pipeline runs, allowing parameters in `config.yaml` to be tweaked to immediately re-evaluate the pipeline yield; expand `config.yaml` with FinOps health thresholds and reporting controls.
  * **Execution (`execute:`)**:
    * **Expanded `analysis/config.yaml`**: Added `finops_targets` (`min_tag_coverage_pct: 90.0`, `min_commitment_coverage_pct: 70.0`, `max_unattached_ipv4_usd: 0.0`) and `reporting` (`output_markdown_path`, `top_anomalies_display_count: 5`).
    * **Implemented Dynamic Report Generator (`analysis/spike_and_forecast_eval.py`)**: Added `generate_markdown_report()` that queries PostgreSQL marts (`mrt_finops_kpis_summary`, `mrt_savings_opportunities`, `fct_cost_reconciliation_audit`) and formats 5 sections: (1) Active Configuration & Thresholds, (2) Standard FinOps KPI Scorecard with Pass/Warn health checks against governance targets, (3) Quantified Savings Opportunities (low/base/high monthly estimates and AWS documentation URLs), (4) Source-to-Mart Reconciliation Audit, and (5) Statistical Anomaly Detection & Dynamic Out-of-Sample Backtest.
    * **Updated `pipeline.sh`**: Surfaced the relative path of `latest_run_report.md` upon completion.
    * **Verified**: Executed `spike_and_forecast_eval.py` via `run_with_env.py` and confirmed `analysis/reports/latest_run_report.md` is compiled with zero errors.

### Phase 6: Dedicated Database Provisioning & Local Environment Configuration
* **Date**: November 17, 2026
* **Core Artifacts**: `.env`, `ingestion/load_finops_data.py`, `analysis/spike_and_forecast_eval.py`, `pipeline.sh`
* **Dedicated Database & Environment Sourcing (`execute:`)**:
  * **Original Request / Pivot**: Resolve the `KeyError: 'PG_HOST'` on bare `bash pipeline.sh` by strictly creating a local `.env` file without fallback logic; provision a new dedicated PostgreSQL database (`cloud_finops_db`) owned by the local `wsltest` user; and ensure standalone Python scripts and `pipeline.sh` read that `.env` directly.
  * **Execution (`execute:`)**:
    * **Provisioned Dedicated PostgreSQL Database**: Connected via PostgreSQL and created database `cloud_finops_db` with ownership granted to user `wsltest`.
    * **Created `.env`**: Configured repository `.env` (`PG_HOST=localhost`, `PG_PORT=5432`, `PG_USER=wsltest`, `PG_DATABASE=cloud_finops_db`, `GCP_PROJECT_ID=finops-analytics-project`), which is safely ignored by `.gitignore`.
    * **Integrated `python-dotenv` in Scripts**: Added explicit `load_dotenv()` calls in `ingestion/load_finops_data.py` and `analysis/spike_and_forecast_eval.py` so running Python scripts standalone or via CLI wrappers automatically sources `.env`.
    * **Empirical Verification**: Executed `bash pipeline.sh local` directly from a fresh terminal shell without any external wrappers or manual environment exports. Confirmed `dlt` ingestion (6.77s), `dbt build` (39/39 nodes passed, `PASS=39 WARN=0 ERROR=0`), and report compilation into `analysis/reports/latest_run_report.md` all exited with code 0.

### Phase 7: Separation of Action Impact Report & Technical Data Engineering Audit
* **Date**: November 17, 2026
* **Core Artifacts**: `analysis/config.yaml`, `analysis/spike_and_forecast_eval.py`, `analysis/reports/impact_report.md`, `analysis/reports/pipeline_audit_report.md`, `pipeline.sh`, `README.md`
* **Dedicated Action Impact Report (`execute:`)**:
  * **Original Request / Pivot**: Separate the technical pipeline audit report from an action-oriented business impact report; strip technical clutter and statistical preamble, focusing exclusively on problem description, solve action, department owner, and expected savings in raw numbers and percentages.
  * **Execution (`execute:`)**:
    * **Updated `analysis/config.yaml`**: Configured distinct output paths for `impact_markdown_path` (`analysis/reports/impact_report.md`) and `audit_markdown_path` (`analysis/reports/pipeline_audit_report.md`).
    * **Implemented `generate_impact_report()` in `analysis/spike_and_forecast_eval.py`**: Added dedicated generator that formats an executive summary table and department-specific breakdowns (Problem, Solve Action, Expected Savings: Low/Base/High in $ and %, and documentation links) across all 5 levers.
    * **Updated `pipeline.sh`**: Outputs the locations of both the Action Impact Report and Technical Audit Report upon run completion.
    * **Empirical Verification**: Executed `bash pipeline.sh local` directly and verified both reports generate cleanly on `cloud_finops_db` with zero errors.
