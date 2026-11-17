# Cloud FinOps Pipeline Run & Yield Report

Generated at: `2026-11-17 02:31:26 UTC`
Target Database: `cloud_finops_db` (`localhost`)

---

## 1. Active Configuration & Thresholds

| Section | Parameter | Value | Description |
| :--- | :--- | :--- | :--- |
| Anomaly Detection | `window_size_days` | `7d` | Rolling baseline window size |
| Anomaly Detection | `z_score_threshold` | `3.0` | MAD Z-score threshold for anomaly flag |
| Anomaly Detection | `persistence_consecutive_days` | `3d` | Threshold to distinguish persistent shift from 1-day spike |
| Anomaly Detection | `mad_scale_floor_pct` | `5.0%` | Minimum scale floor to avoid division by zero |
| Anomaly Detection | `ewma_smoothing_alpha` | `0.45` | EWMA smoothing rate for regime-aware forecast |
| Backtest | `post_spike_eval_window_days` | `5d` | Dynamic recovery evaluation window following stripped spikes |
| Backtest | `trailing_holdout_ratio` | `15%` | Trailing timeline ratio evaluated for out-of-sample holdout |
| Governance Target | `min_tag_coverage_pct` | `90.0%` | Target threshold for tagged usage spend |
| Governance Target | `min_commitment_coverage_pct` | `70.0%` | Target threshold for commitment discount coverage |
| Governance Target | `max_unattached_ipv4_usd` | `$0.00/mo` | Maximum allowable spend on unattached idle Elastic IPs |

---

## 2. Standard FinOps KPI Scorecard & Health Checks

| Dataset Source | Provider | Months | Billed Cost | Effective Cost | Tag Coverage | Commitment Coverage | Unused Waste | Effective Savings Rate |
| :--- | :--- | :---: | ---: | ---: | :---: | :---: | ---: | ---: |
| `AWS_CUR_2018` | AWS | 3 | $7,978.18 | $8,368.36 | 0.0% [WARN: <90%] | 8.4% [WARN: <70%] | $145.09 | 82.7% |
| `FOCUS_1.0` | AWS | 1 | $833.61 | $304.32 | 92.8% [PASS] | 1.8% [WARN: <70%] | $0.00 | 75.6% |
| `FOCUS_1.0` | Google Cloud | 1 | $0.02 | $0.00 | 0.0% [WARN: <90%] | 0.0% [WARN: <70%] | $0.00 | 0.0% |
| `FOCUS_1.0` | Microsoft | 1 | $567.21 | $587.28 | 97.1% [PASS] | 0.0% [WARN: <70%] | $0.00 | 55.0% |
| `FOCUS_1.0` | Oracle | 2 | $26.08 | $23.00 | 100.0% [PASS] | 0.0% [WARN: <70%] | $0.00 | 0.0% |

---

## 3. Quantified Savings Opportunities (Range Breakdown)

| Opportunity ID | Lever Category | Monthly Addressable Spend | Low Savings | Base Savings | High Savings | AWS Documentation Reference |
| :--- | :--- | ---: | ---: | ---: | ---: | :--- |
| `1_ec2_savings_plan_floor_sizing` | Rate Optimization | $372.59/mo | $74.52 (20%) | **$104.33** (28%) | $130.41 (35%) | [1yr Compute Savings Plan discount on p10 daily On-Demand floor](https://aws.amazon.com/savingsplans/compute-pricing/) |
| `2_dev_gpu_offhours_scheduling` | Usage Optimization | $557.49/mo | $195.12 (35%) | **$278.75** (50%) | $356.79 (64%) | [Non-production GPU instance off-hours scheduling reduction](https://docs.aws.amazon.com/solutions/latest/instance-scheduler-on-aws/solution-overview.html) |
| `3_vpc_idle_public_ipv4_release` | Usage Optimization | $1.22/mo | $1.10 (90%) | **$1.22** (100%) | $1.22 (100%) | [Unattached idle public IPv4 address release recovery rate](https://aws.amazon.com/blogs/aws/new-aws-public-ipv4-address-charge-public-ip-insights/) |
| `4_s3_egress_transfer_reduction` | Usage Optimization | $4.02/mo | $0.80 (20%) | **$1.61** (40%) | $2.41 (60%) | [S3 internet egress and cross-region transfer reduction rate](https://aws.amazon.com/s3/pricing/) |
| `5_cur_reserved_instance_unused_waste` | Rate Optimization | $48.36/mo | $24.18 (50%) | **$36.27** (75%) | $42.56 (88%) | [Unused Reserved Instance commitment recovery rate](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ri-Modifying.html) |
| **Total Realizable Opportunity** | **All Levers** | - | **$295.72/mo** | **$422.18/mo** | **$533.39/mo** | - |

---

## 4. Source-to-Mart Reconciliation Audit

| Dataset Source | Slice / Group | Total Cash Cost | Total Amortized Cost | Raw Variance | Variance After Rounding Adjustment |
| :--- | :--- | ---: | ---: | ---: | ---: |
| `AWS_CUR_2018` | 2018-10-01 | $4,064.48 | $4,195.95 | $-131.4744 | `$0.000012` |
| `AWS_CUR_2018` | 2018-11-01 | $3,505.33 | $3,632.56 | $-127.2332 | `$-0.000002` |
| `AWS_CUR_2018` | 2018-12-01 | $408.37 | $539.85 | $-131.4743 | `$0.000000` |
| `FOCUS_1.0` | AWS | $0.00 | $0.00 | $0.0000 | `$0.000000` |
| `FOCUS_1.0` | AWS | $0.00 | $0.00 | $0.0000 | `$0.000000` |
| `FOCUS_1.0` | AWS | $0.00 | $9.00 | $-9.0000 | `$-9.000000` |
| `FOCUS_1.0` | AWS | $1.18 | $0.00 | $1.1765 | `$0.000000` |
| `FOCUS_1.0` | AWS | $2,026.57 | $1,484.32 | $542.2496 | `$0.680000` |
| `FOCUS_1.0` | AWS | $-2.08 | $-2.00 | $-0.0841 | `$0.000000` |
| `FOCUS_1.0` | AWS | $-1,194.37 | $-1,187.00 | $-7.3691 | `$0.000000` |
| `FOCUS_1.0` | AWS | $2.32 | $0.00 | $2.3180 | `$2.000000` |
| `FOCUS_1.0` | Google Cloud | $0.02 | $0.00 | $0.0165 | `$0.000000` |
| `FOCUS_1.0` | Microsoft | $0.00 | $0.00 | $0.0000 | `$0.000000` |
| `FOCUS_1.0` | Microsoft | $0.00 | $0.01 | $-0.0110 | `$-0.011000` |
| `FOCUS_1.0` | Microsoft | $0.00 | $20.06 | $-20.0586 | `$-20.058600` |
| `FOCUS_1.0` | Microsoft | $567.21 | $567.21 | $0.0000 | `$-30.210300` |
| `FOCUS_1.0` | Oracle | $19.42 | $15.00 | $4.4164 | `$0.000000` |
| `FOCUS_1.0` | Oracle | $6.67 | $8.00 | $-1.3332 | `$0.000000` |

---

## 5. Statistical Anomaly Detection & Dynamic Out-of-Sample Backtest

### A. Top Detected Anomalies

| Dataset | Date | Actual Spend | Rolling 7d Median | MAD Z-Score | Classification | Action Taken |
| :--- | :--- | ---: | ---: | ---: | :--- | :--- |
| `FOCUS AWS` | `2024-09-09` | $40.72 | $21.77 | +4.32 | `transient_spike_stripped` | Stripped to median baseline |
| `FOCUS AWS` | `2024-09-11` | $39.19 | $21.77 | +3.97 | `regime_shift_reanchored` | Re-anchored baseline |
| `FOCUS AWS` | `2024-09-12` | $67.42 | $21.77 | +10.42 | `regime_shift_reanchored` | Re-anchored baseline |
| `FOCUS AWS` | `2024-09-13` | $62.95 | $21.77 | +9.58 | `regime_shift_reanchored` | Re-anchored baseline |
| `FOCUS AWS` | `2024-09-14` | $78.95 | $25.67 | +3.10 | `regime_shift_reanchored` | Re-anchored baseline |
| `AWS CUR` | `2018-10-10` | $161.34 | $106.24 | +10.37 | `regime_shift_reanchored` | Re-anchored baseline |
| `AWS CUR` | `2018-10-11` | $161.50 | $106.24 | +10.40 | `regime_shift_reanchored` | Re-anchored baseline |
| `AWS CUR` | `2018-10-12` | $161.52 | $106.24 | +10.41 | `regime_shift_reanchored` | Re-anchored baseline |
| `AWS CUR` | `2018-10-13` | $161.50 | $111.99 | +5.80 | `regime_shift_reanchored` | Re-anchored baseline |
| `AWS CUR` | `2018-10-16` | $103.81 | $161.50 | -7.14 | `transient_spike_stripped` | Stripped to median baseline |

### B. Dynamic Regime Forecast Backtest (Mean Absolute Error Comparison)

| Evaluation Window | Scope / Window Dates | Days | Naive 7-Day Rolling Mean MAE | Spike-Stripped 7-Day Median MAE | Regime-Aware EWMA Model MAE | Winning Model |
| :--- | :--- | :---: | ---: | ---: | ---: | :--- |
| Post-Spike Recovery (FOCUS) | `2024-09-10` to `2024-09-23` | 6 | $15.83/day | $19.49/day | $20.26/day | **Naive Rolling Mean** |
| Workload Step-Change (FOCUS) | `2024-09-11` to `2024-09-26` | 7 | $46.66/day | $55.26/day | $35.67/day | **Regime-Aware EWMA** |
| Trailing Out-of-Sample (AWS CUR) | `2018-12-19` to `2018-12-31` | 13 | $0.57/day | $0.47/day | $0.40/day | **Regime-Aware EWMA** |

---

*Report dynamically compiled by `analysis/spike_and_forecast_eval.py` from clean PostgreSQL marts.*
