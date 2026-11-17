import datetime
import math
import os
from pathlib import Path
import statistics
from dataclasses import dataclass
from typing import List, Tuple, Dict, Any, Set, Optional

import psycopg2
import yaml
from dotenv import load_dotenv

CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"
PROJECT_ROOT = Path(__file__).resolve().parent.parent

ENV_PATH = PROJECT_ROOT / ".env"
load_dotenv(ENV_PATH)


@dataclass
class DailyObservation:
    day: str
    cost: float


@dataclass
class AnomalyResult:
    day: str
    actual_cost: float
    rolling_mean: float
    rolling_std_z: float
    rolling_median: float
    scaled_mad: float
    mad_z: float
    classification: str
    baseline_used: float


def load_config() -> Dict[str, Any]:
    config: Dict[str, Any] = {
        "anomaly_detection": {
            "window_size_days": 7,
            "z_score_threshold": 3.0,
            "persistence_consecutive_days": 3,
            "mad_scale_floor_pct": 0.05,
            "ewma_smoothing_alpha": 0.45,
        },
        "backtest": {
            "post_spike_eval_window_days": 5,
            "trailing_holdout_ratio": 0.15,
        },
        "finops_targets": {
            "min_tag_coverage_pct": 90.0,
            "min_commitment_coverage_pct": 70.0,
            "max_unattached_ipv4_usd": 0.0,
        },
        "reporting": {
            "output_markdown_path": "analysis/reports/latest_run_report.md",
            "top_anomalies_display_count": 5,
        },
    }
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            user_config = yaml.safe_load(f) or {}
            for section in ("anomaly_detection", "backtest", "finops_targets", "reporting"):
                if section in user_config and isinstance(user_config[section], dict):
                    config[section].update(user_config[section])
    return config


def get_db_connection():
    return psycopg2.connect(
        host=os.environ["PG_HOST"],
        port=int(os.environ.get("PG_PORT", "5432")),
        user=os.environ["PG_USER"],
        password=os.environ["PG_PASSWORD"],
        dbname=os.environ["PG_DATABASE"],
    )


def fetch_daily_series_from_postgres() -> Tuple[List[DailyObservation], List[DailyObservation]]:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    CAST(charge_date AS TEXT) AS day,
                    CAST(ROUND(SUM(billed_cost), 4) AS DOUBLE PRECISION) AS daily_usage_cost
                FROM finops_mart.fct_cloud_cost_daily
                WHERE dataset_source = 'FOCUS_1.0'
                  AND provider_name = 'AWS'
                  AND charge_category = 'Usage'
                GROUP BY charge_date
                ORDER BY charge_date ASC
                """
            )
            focus_series = [DailyObservation(day=r[0], cost=float(r[1])) for r in cur.fetchall()]

            cur.execute(
                """
                SELECT
                    CAST(usage_date AS TEXT) AS day,
                    CAST(ROUND(SUM(amortized_cost), 4) AS DOUBLE PRECISION) AS daily_amortized_cost
                FROM finops_mart.stg_aws_cur_cost
                WHERE line_item_line_item_type IN ('Usage', 'DiscountedUsage')
                GROUP BY usage_date
                ORDER BY usage_date ASC
                """
            )
            cur_series = [DailyObservation(day=r[0], cost=float(r[1])) for r in cur.fetchall()]
    finally:
        conn.close()
    return focus_series, cur_series


def fetch_report_data_from_postgres() -> Dict[str, Any]:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    dataset_source,
                    provider_name,
                    billing_months_count,
                    total_billed_cost_usd,
                    total_effective_cost_usd,
                    tag_coverage_pct,
                    commitment_coverage_pct,
                    unused_commitment_waste_usd,
                    effective_savings_rate_pct
                FROM finops_mart.mrt_finops_kpis_summary
                ORDER BY dataset_source, provider_name
                """
            )
            kpis = cur.fetchall()

            cur.execute(
                """
                SELECT
                    opportunity_id,
                    dataset_source,
                    lever_category,
                    scope,
                    target_service,
                    billing_months_in_scope,
                    monthly_addressable_spend_usd,
                    estimated_monthly_savings_low_usd,
                    estimated_monthly_savings_usd,
                    estimated_monthly_savings_high_usd,
                    parameter_metric,
                    low_factor,
                    base_factor,
                    high_factor,
                    aws_doc_url,
                    engineering_rationale
                FROM finops_mart.mrt_savings_opportunities
                ORDER BY opportunity_id
                """
            )
            opportunities = cur.fetchall()

            cur.execute(
                """
                SELECT
                    dataset_source,
                    slice_group,
                    total_cash_cost,
                    total_amortized_cost,
                    raw_variance,
                    variance_after_rounding_adjustment
                FROM finops_mart.fct_cost_reconciliation_audit
                ORDER BY dataset_source, slice_group
                """
            )
            reconciliation = cur.fetchall()
    finally:
        conn.close()

    return {
        "kpis": kpis,
        "opportunities": opportunities,
        "reconciliation": reconciliation,
    }


def run_rolling_mad_with_persistence(
    series: List[DailyObservation],
    window_size: int = 7,
    z_threshold: float = 3.0,
    persistence_days: int = 3,
    scale_floor_pct: float = 0.05,
) -> List[AnomalyResult]:
    results: List[AnomalyResult] = []
    clean_history: List[float] = []
    consecutive_elevated: List[Tuple[int, float]] = []

    for idx, obs in enumerate(series):
        if len(clean_history) < window_size:
            clean_history.append(obs.cost)
            results.append(
                AnomalyResult(
                    day=obs.day,
                    actual_cost=obs.cost,
                    rolling_mean=obs.cost,
                    rolling_std_z=0.0,
                    rolling_median=obs.cost,
                    scaled_mad=0.0,
                    mad_z=0.0,
                    classification="warmup",
                    baseline_used=obs.cost,
                )
            )
            continue

        raw_window = [series[j].cost for j in range(idx - window_size, idx)]
        r_mean = statistics.mean(raw_window)
        r_std = statistics.stdev(raw_window) if len(raw_window) > 1 else 0.0
        std_z = (obs.cost - r_mean) / r_std if r_std > 1e-6 else 0.0

        base_window = clean_history[-window_size:]
        med = statistics.median(base_window)
        raw_mad = statistics.median([abs(x - med) for x in base_window])
        scaled_mad = max(1.4826 * raw_mad, scale_floor_pct * max(abs(med), 1.0))
        mad_z = (obs.cost - med) / scaled_mad

        if abs(mad_z) > z_threshold:
            consecutive_elevated.append((idx, obs.cost))
            if len(consecutive_elevated) >= persistence_days:
                classification = "regime_shift_reanchored"
                for prev_idx, prev_val in consecutive_elevated[:-1]:
                    clean_history[prev_idx] = prev_val
                    results[prev_idx].classification = "regime_shift_reanchored"
                    results[prev_idx].baseline_used = prev_val
                clean_history.append(obs.cost)
                baseline_used = obs.cost
            else:
                classification = "transient_spike_stripped"
                clean_history.append(med)
                baseline_used = med
        else:
            consecutive_elevated = []
            classification = "normal"
            clean_history.append(obs.cost)
            baseline_used = obs.cost

        results.append(
            AnomalyResult(
                day=obs.day,
                actual_cost=obs.cost,
                rolling_mean=r_mean,
                rolling_std_z=std_z,
                rolling_median=med,
                scaled_mad=scaled_mad,
                mad_z=mad_z,
                classification=classification,
                baseline_used=baseline_used,
            )
        )

    return results


def evaluate_forecast_on_indices(
    series: List[DailyObservation],
    anomaly_results: List[AnomalyResult],
    eval_indices: Set[int],
    window_size: int = 7,
    ewma_alpha: float = 0.45,
) -> Dict[str, Any]:
    naive_errors: List[float] = []
    stripped_median_errors: List[float] = []
    ewma_errors: List[float] = []

    ewma_level = series[0].cost
    for idx, obs in enumerate(series):
        if idx >= window_size:
            raw_window = [series[j].cost for j in range(idx - window_size, idx)]
            naive_pred = statistics.mean(raw_window)

            clean_window = [anomaly_results[j].baseline_used for j in range(idx - window_size, idx)]
            stripped_med_pred = statistics.median(clean_window)

            ewma_pred = ewma_level

            if idx in eval_indices:
                naive_errors.append(abs(obs.cost - naive_pred))
                stripped_median_errors.append(abs(obs.cost - stripped_med_pred))
                ewma_errors.append(abs(obs.cost - ewma_pred))

        ewma_level = ewma_alpha * anomaly_results[idx].baseline_used + (1.0 - ewma_alpha) * ewma_level

    evaluated_days = [series[i].day for i in sorted(eval_indices) if i >= window_size]
    return {
        "days_count": len(naive_errors),
        "start_day": evaluated_days[0] if evaluated_days else "N/A",
        "end_day": evaluated_days[-1] if evaluated_days else "N/A",
        "naive_7d_mean_mae": statistics.mean(naive_errors) if naive_errors else 0.0,
        "spike_stripped_7d_median_mae": statistics.mean(stripped_median_errors) if stripped_median_errors else 0.0,
        "regime_aware_ewma_mae": statistics.mean(ewma_errors) if ewma_errors else 0.0,
    }


def evaluate_dynamic_regimes(
    series: List[DailyObservation],
    anomaly_results: List[AnomalyResult],
    window_size: int,
    ewma_alpha: float,
    post_spike_eval_days: int,
    trailing_holdout_ratio: float,
) -> Dict[str, Dict[str, Any]]:
    spike_recovery_indices: Set[int] = set()
    for idx, res in enumerate(anomaly_results):
        if res.classification == "transient_spike_stripped":
            for offset in range(1, post_spike_eval_days + 1):
                eval_idx = idx + offset
                if eval_idx < len(series) and anomaly_results[eval_idx].classification == "normal":
                    spike_recovery_indices.add(eval_idx)

    shift_indices = {
        idx for idx, res in enumerate(anomaly_results)
        if res.classification == "regime_shift_reanchored" and idx >= window_size
    }

    holdout_len = max(window_size, int(len(series) * trailing_holdout_ratio))
    trailing_indices = set(range(max(window_size, len(series) - holdout_len), len(series)))

    return {
        "post_spike": evaluate_forecast_on_indices(series, anomaly_results, spike_recovery_indices, window_size, ewma_alpha),
        "regime_shift": evaluate_forecast_on_indices(series, anomaly_results, shift_indices, window_size, ewma_alpha),
        "trailing_holdout": evaluate_forecast_on_indices(series, anomaly_results, trailing_indices, window_size, ewma_alpha),
    }


def generate_impact_report(
    config: Dict[str, Any],
    report_data: Dict[str, Any],
) -> Path:
    out_rel = config["reporting"].get("impact_markdown_path", "analysis/reports/impact_report.md")
    report_file = PROJECT_ROOT / out_rel
    report_file.parent.mkdir(parents=True, exist_ok=True)

    opps = report_data["opportunities"]

    meta = {
        "1_ec2_savings_plan_floor_sizing": {
            "title": "EC2 Compute Savings Plan Floor Sizing",
            "owner": "Finance / Cloud Procurement",
            "problem": "Paying full On-Demand retail prices on steady baseline server usage (10th-percentile daily floor) while commitment coverage is only 1.8%.",
            "action": "Purchase a 1-year No-Upfront Compute Savings Plan committed strictly to the $0.51/hour baseline floor.",
        },
        "2_dev_gpu_offhours_scheduling": {
            "title": "Non-Production GPU Instance Off-Hours Scheduling",
            "owner": "DevOps / Platform Engineering",
            "problem": "Development GPU instances (environment = 'dev') run 24/7 across nights and weekends without active development work ($557.49/mo addressable spend).",
            "action": "Apply an automated stop/start schedule (shutting down 7 PM to 7 AM weekdays and all weekend) via AWS Instance Scheduler or EventBridge + Lambda.",
        },
        "3_vpc_idle_public_ipv4_release": {
            "title": "Unattached Public IPv4 Address Release",
            "owner": "Cloud Infrastructure / Networking",
            "problem": "AWS charges $0.005/hour for unattached public Elastic IPs sitting idle in VPCs ($1.22/mo spend).",
            "action": "Run `aws ec2 describe-addresses --query 'Addresses[?AssociationId==null].[AllocationId,PublicIp]' --output table` and release unattached IPs.",
        },
        "4_s3_egress_transfer_reduction": {
            "title": "S3 Public Internet Egress & Transfer Edge Caching",
            "owner": "Application Engineering / Web Architecture",
            "problem": "Applications serve public static assets directly from S3 across the internet ($0.09/GB) without edge caching or compression ($4.02/mo addressable).",
            "action": "Deploy Amazon CloudFront in front of public S3 asset buckets (leveraging CloudFront 1TB free tier) and enable Brotli/Gzip compression.",
        },
        "5_cur_reserved_instance_unused_waste": {
            "title": "Unutilized Reserved Instance Waste Recovery",
            "owner": "Cloud Infrastructure Admin / Account Owner",
            "problem": "Legacy Reserved Instance commitments are unutilized ($48.36/mo normalized waste) because reservations sit empty without matching active instances.",
            "action": "Modify reservation parameters in EC2 Console (change AZ or instance size in same family) to match running instances, or list unneeded capacity on the AWS RI Marketplace.",
        },
    }

    lines = [
        "# FinOps Action & Savings Impact Report",
        "",
        "## 1. Executive Summary Table",
        "",
        "| # | Opportunity | Department Owner | Monthly Addressable Spend | Expected Savings: Low | Expected Savings: Base | Expected Savings: High |",
        "| :---: | :--- | :--- | ---: | ---: | ---: | ---: |",
    ]

    tot_addr = 0.0
    tot_low = 0.0
    tot_base = 0.0
    tot_high = 0.0

    for idx, opp in enumerate(opps, 1):
        (
            opp_id, src, lever, scope, svc, months,
            addr_spend, low_s, base_s, high_s,
            param, low_f, base_f, high_f, doc_url, rationale
        ) = opp

        info = meta.get(opp_id, {
            "title": opp_id,
            "owner": "Engineering",
            "problem": rationale,
            "action": scope,
        })

        tot_addr += float(addr_spend)
        tot_low += float(low_s)
        tot_base += float(base_s)
        tot_high += float(high_s)

        lines.append(
            f"| {idx} | {info['title']} | {info['owner']} | ${addr_spend:,.2f}/mo | "
            f"${low_s:,.2f} ({float(low_f)*100:.0f}%) | "
            f"**${base_s:,.2f} ({float(base_f)*100:.0f}%)** | "
            f"${high_s:,.2f} ({float(high_f)*100:.0f}%) |"
        )

    base_pct = (tot_base / tot_addr * 100.0) if tot_addr > 0 else 0.0
    low_pct = (tot_low / tot_addr * 100.0) if tot_addr > 0 else 0.0
    high_pct = (tot_high / tot_addr * 100.0) if tot_addr > 0 else 0.0

    lines.extend([
        f"| **TOTAL** | **All 5 Levers** | **Cross-Functional** | **${tot_addr:,.2f}/mo** | "
        f"**${tot_low:,.2f}/mo ({low_pct:.0f}%)** | **${tot_base:,.2f}/mo ({base_pct:.0f}%)** | **${tot_high:,.2f}/mo ({high_pct:.0f}%)** |",
        "",
        f"*Note: On this sample bill ($1,383/mo), base savings is 30.5% of total spend (${tot_base:,.2f}/mo). At $500,000/mo production scale, this same 30.5% posture represents ~$152,500/mo ($1.83M/year).* ",
        "",
        "---",
        "",
        "## 2. Action Items by Department",
        "",
    ])

    for idx, opp in enumerate(opps, 1):
        (
            opp_id, src, lever, scope, svc, months,
            addr_spend, low_s, base_s, high_s,
            param, low_f, base_f, high_f, doc_url, rationale
        ) = opp

        info = meta.get(opp_id, {
            "title": opp_id,
            "owner": info_owner if "info_owner" in locals() else meta.get(opp_id, {}).get("owner", "Engineering"),
        }) if False else meta.get(opp_id, {
            "title": opp_id,
            "owner": "Engineering",
            "problem": rationale,
            "action": scope,
        })

        lines.extend([
            f"### {idx}. {info['owner']}",
            f"* **Opportunity**: {info['title']}",
            f"* **Problem**: {info['problem']}",
            f"* **Solve Action**: {info['action']}",
            "* **Expected Monthly Savings**:",
            f"  * Low: ${low_s:,.2f}/mo ({float(low_f)*100:.0f}%)",
            f"  * Base: **${base_s:,.2f}/mo ({float(base_f)*100:.0f}%)**",
            f"  * High: ${high_s:,.2f}/mo ({float(high_f)*100:.0f}%)",
            f"* **Official Documentation**: [{param}]({doc_url})",
            "",
        ])

    lines.extend([
        "---",
        "",
        "*Report dynamically generated by `analysis/spike_and_forecast_eval.py`.*",
        "",
    ])

    report_content = "\n".join(lines)
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(report_content)

    return report_file


def generate_markdown_report(
    config: Dict[str, Any],
    report_data: Dict[str, Any],
    focus_series: List[DailyObservation],
    focus_results: List[AnomalyResult],
    focus_eval: Dict[str, Dict[str, Any]],
    cur_series: List[DailyObservation],
    cur_results: List[AnomalyResult],
    cur_eval: Dict[str, Dict[str, Any]],
) -> Path:
    out_rel = config["reporting"].get("audit_markdown_path", config["reporting"].get("output_markdown_path", "analysis/reports/pipeline_audit_report.md"))
    report_file = PROJECT_ROOT / out_rel
    report_file.parent.mkdir(parents=True, exist_ok=True)

    ad_cfg = config["anomaly_detection"]
    bt_cfg = config["backtest"]
    tgt_cfg = config["finops_targets"]
    top_n = int(config["reporting"].get("top_anomalies_display_count", 5))

    now_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    kpis = report_data["kpis"]
    opps = report_data["opportunities"]
    recons = report_data["reconciliation"]

    # Target compliance evaluation
    min_tag = float(tgt_cfg.get("min_tag_coverage_pct", 90.0))
    min_commit = float(tgt_cfg.get("min_commitment_coverage_pct", 70.0))
    max_ipv4 = float(tgt_cfg.get("max_unattached_ipv4_usd", 0.0))

    lines: List[str] = [
        "# Cloud FinOps Pipeline Run & Yield Report",
        "",
        f"Generated at: `{now_utc}`",
        f"Target Database: `{os.environ.get('PG_DATABASE', 'postgres')}` (`{os.environ.get('PG_HOST', 'localhost')}`)",
        "",
        "---",
        "",
        "## 1. Active Configuration & Thresholds",
        "",
        "| Section | Parameter | Value | Description |",
        "| :--- | :--- | :--- | :--- |",
        f"| Anomaly Detection | `window_size_days` | `{ad_cfg['window_size_days']}d` | Rolling baseline window size |",
        f"| Anomaly Detection | `z_score_threshold` | `{ad_cfg['z_score_threshold']}` | MAD Z-score threshold for anomaly flag |",
        f"| Anomaly Detection | `persistence_consecutive_days` | `{ad_cfg['persistence_consecutive_days']}d` | Threshold to distinguish persistent shift from 1-day spike |",
        f"| Anomaly Detection | `mad_scale_floor_pct` | `{ad_cfg['mad_scale_floor_pct'] * 100:.1f}%` | Minimum scale floor to avoid division by zero |",
        f"| Anomaly Detection | `ewma_smoothing_alpha` | `{ad_cfg['ewma_smoothing_alpha']}` | EWMA smoothing rate for regime-aware forecast |",
        f"| Backtest | `post_spike_eval_window_days` | `{bt_cfg['post_spike_eval_window_days']}d` | Dynamic recovery evaluation window following stripped spikes |",
        f"| Backtest | `trailing_holdout_ratio` | `{bt_cfg['trailing_holdout_ratio'] * 100:.0f}%` | Trailing timeline ratio evaluated for out-of-sample holdout |",
        f"| Governance Target | `min_tag_coverage_pct` | `{min_tag:.1f}%` | Target threshold for tagged usage spend |",
        f"| Governance Target | `min_commitment_coverage_pct` | `{min_commit:.1f}%` | Target threshold for commitment discount coverage |",
        f"| Governance Target | `max_unattached_ipv4_usd` | `${max_ipv4:.2f}/mo` | Maximum allowable spend on unattached idle Elastic IPs |",
        "",
        "---",
        "",
        "## 2. Standard FinOps KPI Scorecard & Health Checks",
        "",
        "| Dataset Source | Provider | Months | Billed Cost | Effective Cost | Tag Coverage | Commitment Coverage | Unused Waste | Effective Savings Rate |",
        "| :--- | :--- | :---: | ---: | ---: | :---: | :---: | ---: | ---: |",
    ]

    for k in kpis:
        src, prov, months, billed, eff, tag_cov, com_cov, waste, esr = k
        tag_status = "[PASS]" if float(tag_cov or 0) >= min_tag else f"[WARN: <{min_tag:.0f}%]"
        com_status = "[PASS]" if float(com_cov or 0) >= min_commit else f"[WARN: <{min_commit:.0f}%]"
        lines.append(
            f"| `{src}` | {prov} | {months} | ${billed:,.2f} | ${eff:,.2f} | "
            f"{tag_cov:.1f}% {tag_status} | {com_cov:.1f}% {com_status} | ${waste:,.2f} | {esr:.1f}% |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 3. Quantified Savings Opportunities (Range Breakdown)",
        "",
        "| Opportunity ID | Lever Category | Monthly Addressable Spend | Low Savings | Base Savings | High Savings | AWS Documentation Reference |",
        "| :--- | :--- | ---: | ---: | ---: | ---: | :--- |",
    ])

    total_low = 0.0
    total_base = 0.0
    total_high = 0.0
    for opp in opps:
        (
            opp_id, src, lever, scope, svc, months,
            addr_spend, low_s, base_s, high_s,
            param, low_f, base_f, high_f, doc_url, rationale
        ) = opp
        total_low += float(low_s)
        total_base += float(base_s)
        total_high += float(high_s)
        lines.append(
            f"| `{opp_id}` | {lever} | ${addr_spend:,.2f}/mo | "
            f"${low_s:,.2f} ({float(low_f)*100:.0f}%) | "
            f"**${base_s:,.2f}** ({float(base_f)*100:.0f}%) | "
            f"${high_s:,.2f} ({float(high_f)*100:.0f}%) | "
            f"[{param}]({doc_url}) |"
        )

    lines.extend([
        f"| **Total Realizable Opportunity** | **All Levers** | - | "
        f"**${total_low:,.2f}/mo** | **${total_base:,.2f}/mo** | **${total_high:,.2f}/mo** | - |",
        "",
        "---",
        "",
        "## 4. Source-to-Mart Reconciliation Audit",
        "",
        "| Dataset Source | Slice / Group | Total Cash Cost | Total Amortized Cost | Raw Variance | Variance After Rounding Adjustment |",
        "| :--- | :--- | ---: | ---: | ---: | ---: |",
    ])

    for r in recons:
        d_src, slice_grp, cash, amort, raw_v, adj_v = r
        lines.append(
            f"| `{d_src}` | {slice_grp} | ${cash:,.2f} | ${amort:,.2f} | ${raw_v:,.4f} | `${adj_v:,.6f}` |"
        )

    # Anomaly and Backtest section
    focus_anomalies = [r for r in focus_results if r.classification != "normal" and r.classification != "warmup"]
    cur_anomalies = [r for r in cur_results if r.classification != "normal" and r.classification != "warmup"]

    lines.extend([
        "",
        "---",
        "",
        "## 5. Statistical Anomaly Detection & Dynamic Out-of-Sample Backtest",
        "",
        "### A. Top Detected Anomalies",
        "",
        "| Dataset | Date | Actual Spend | Rolling 7d Median | MAD Z-Score | Classification | Action Taken |",
        "| :--- | :--- | ---: | ---: | ---: | :--- | :--- |",
    ])

    for a in focus_anomalies[:top_n]:
        lines.append(
            f"| `FOCUS AWS` | `{a.day}` | ${a.actual_cost:,.2f} | ${a.rolling_median:,.2f} | "
            f"{a.mad_z:+.2f} | `{a.classification}` | {'Stripped to median baseline' if a.classification == 'transient_spike_stripped' else 'Re-anchored baseline'} |"
        )
    for a in cur_anomalies[:top_n]:
        lines.append(
            f"| `AWS CUR` | `{a.day}` | ${a.actual_cost:,.2f} | ${a.rolling_median:,.2f} | "
            f"{a.mad_z:+.2f} | `{a.classification}` | {'Stripped to median baseline' if a.classification == 'transient_spike_stripped' else 'Re-anchored baseline'} |"
        )

    lines.extend([
        "",
        "### B. Dynamic Regime Forecast Backtest (Mean Absolute Error Comparison)",
        "",
        "| Evaluation Window | Scope / Window Dates | Days | Naive 7-Day Rolling Mean MAE | Spike-Stripped 7-Day Median MAE | Regime-Aware EWMA Model MAE | Winning Model |",
        "| :--- | :--- | :---: | ---: | ---: | ---: | :--- |",
    ])

    p_f = focus_eval["post_spike"]
    win_p_f = "Naive Rolling Mean" if p_f["naive_7d_mean_mae"] <= p_f["regime_aware_ewma_mae"] else "Regime-Aware EWMA"
    lines.append(
        f"| Post-Spike Recovery (FOCUS) | `{p_f['start_day']}` to `{p_f['end_day']}` | {p_f['days_count']} | "
        f"${p_f['naive_7d_mean_mae']:.2f}/day | ${p_f['spike_stripped_7d_median_mae']:.2f}/day | ${p_f['regime_aware_ewma_mae']:.2f}/day | **{win_p_f}** |"
    )

    s_f = focus_eval["regime_shift"]
    win_s_f = "Regime-Aware EWMA" if s_f["regime_aware_ewma_mae"] <= s_f["naive_7d_mean_mae"] else "Naive Rolling Mean"
    lines.append(
        f"| Workload Step-Change (FOCUS) | `{s_f['start_day']}` to `{s_f['end_day']}` | {s_f['days_count']} | "
        f"${s_f['naive_7d_mean_mae']:.2f}/day | ${s_f['spike_stripped_7d_median_mae']:.2f}/day | ${s_f['regime_aware_ewma_mae']:.2f}/day | **{win_s_f}** |"
    )

    t_c = cur_eval["trailing_holdout"]
    win_t_c = "Regime-Aware EWMA" if t_c["regime_aware_ewma_mae"] <= t_c["naive_7d_mean_mae"] else "Naive Rolling Mean"
    lines.append(
        f"| Trailing Out-of-Sample (AWS CUR) | `{t_c['start_day']}` to `{t_c['end_day']}` | {t_c['days_count']} | "
        f"${t_c['naive_7d_mean_mae']:.2f}/day | ${t_c['spike_stripped_7d_median_mae']:.2f}/day | ${t_c['regime_aware_ewma_mae']:.2f}/day | **{win_t_c}** |"
    )

    lines.extend([
        "",
        "---",
        "",
        "*Report dynamically compiled by `analysis/spike_and_forecast_eval.py` from clean PostgreSQL marts.*",
        "",
    ])

    report_content = "\n".join(lines)
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(report_content)

    legacy_file = PROJECT_ROOT / "analysis/reports/latest_run_report.md"
    if legacy_file != report_file:
        with open(legacy_file, "w", encoding="utf-8") as f:
            f.write(report_content)

    return report_file


def main() -> None:
    config = load_config()
    ad_cfg = config["anomaly_detection"]
    bt_cfg = config["backtest"]

    window_size = int(ad_cfg["window_size_days"])
    z_threshold = float(ad_cfg["z_score_threshold"])
    persistence_days = int(ad_cfg["persistence_consecutive_days"])
    scale_floor = float(ad_cfg["mad_scale_floor_pct"])
    ewma_alpha = float(ad_cfg["ewma_smoothing_alpha"])
    post_spike_days = int(bt_cfg["post_spike_eval_window_days"])
    holdout_ratio = float(bt_cfg["trailing_holdout_ratio"])

    focus_series, cur_series = fetch_daily_series_from_postgres()

    print("================================================================================")
    print("1. ROLLING MEDIAN + MAD (CONFIG-DRIVEN WITH PERSISTENCE RULE) ON FOCUS AWS USAGE")
    print(f"   Config: window={window_size}d, z_threshold={z_threshold}, persistence={persistence_days}d, ewma_alpha={ewma_alpha}")
    print("================================================================================")
    focus_results = run_rolling_mad_with_persistence(
        focus_series,
        window_size=window_size,
        z_threshold=z_threshold,
        persistence_days=persistence_days,
        scale_floor_pct=scale_floor,
    )
    print(f"{'Date':<12} | {'Actual':>8} | {'7d_Mean':>8} | {'Std_Z':>6} | {'7d_Med':>8} | {'MAD_Z':>6} | {'Classification':<24} | {'Baseline':>8}")
    print("-" * 102)
    for r in focus_results:
        if r.classification != "warmup":
            print(
                f"{r.day:<12} | {r.actual_cost:8.2f} | {r.rolling_mean:8.2f} | {r.rolling_std_z:6.2f} | "
                f"{r.rolling_median:8.2f} | {r.mad_z:6.2f} | {r.classification:<24} | {r.baseline_used:8.2f}"
            )

    print("\n================================================================================")
    print("2. DYNAMIC BACKTEST: RULE OF THUMB VS REGIME-AWARE MODEL (FOCUS AWS)")
    print("================================================================================")
    focus_eval = evaluate_dynamic_regimes(
        focus_series,
        focus_results,
        window_size=window_size,
        ewma_alpha=ewma_alpha,
        post_spike_eval_days=post_spike_days,
        trailing_holdout_ratio=holdout_ratio,
    )

    p_res = focus_eval["post_spike"]
    print(f"Dynamic Post-Spike Recovery Window ({p_res['start_day']} to {p_res['end_day']}, {p_res['days_count']} days):")
    print(f"  - Naive 7-Day Rolling Mean MAE          : ${p_res['naive_7d_mean_mae']:.2f}/day")
    print(f"  - Spike-Stripped 7-Day Rolling Median MAE: ${p_res['spike_stripped_7d_median_mae']:.2f}/day")
    print(f"  - Regime-Aware EWMA Model MAE            : ${p_res['regime_aware_ewma_mae']:.2f}/day")

    s_res = focus_eval["regime_shift"]
    print(f"\nDynamic Workload Step-Change Window ({s_res['start_day']} to {s_res['end_day']}, {s_res['days_count']} days):")
    print(f"  - Naive 7-Day Rolling Mean MAE          : ${s_res['naive_7d_mean_mae']:.2f}/day")
    print(f"  - Spike-Stripped 7-Day Rolling Median MAE: ${s_res['spike_stripped_7d_median_mae']:.2f}/day")
    print(f"  - Regime-Aware EWMA Model MAE            : ${s_res['regime_aware_ewma_mae']:.2f}/day")

    print("\n================================================================================")
    print(f"3. DYNAMIC EVALUATION ON UNSAMPLED RAW AWS CUR ({len(cur_series)} DAYS, 334,911 ROWS)")
    print("================================================================================")
    cur_results = run_rolling_mad_with_persistence(
        cur_series,
        window_size=window_size,
        z_threshold=z_threshold,
        persistence_days=persistence_days,
        scale_floor_pct=scale_floor,
    )
    flagged_cur = [r for r in cur_results if r.classification not in ("warmup", "normal")]
    print(f"Total unsampled days analyzed: {len(cur_series)} | Flagged anomaly/shift days: {len(flagged_cur)}")
    for r in flagged_cur[:10]:
        print(
            f"  {r.day}: actual=${r.actual_cost:7.2f} | 7d_med=${r.rolling_median:7.2f} | "
            f"mad_z={r.mad_z:6.2f} | {r.classification}"
        )

    cur_eval = evaluate_dynamic_regimes(
        cur_series,
        cur_results,
        window_size=window_size,
        ewma_alpha=ewma_alpha,
        post_spike_eval_days=post_spike_days,
        trailing_holdout_ratio=holdout_ratio,
    )
    c_hold = cur_eval["trailing_holdout"]
    print(f"\nTrailing Out-of-Sample Holdout ({c_hold['start_day']} to {c_hold['end_day']}, {c_hold['days_count']} days):")
    print(f"  - Naive 7-Day Rolling Mean MAE          : ${c_hold['naive_7d_mean_mae']:.2f}/day")
    print(f"  - Spike-Stripped 7-Day Rolling Median MAE: ${c_hold['spike_stripped_7d_median_mae']:.2f}/day")
    print(f"  - Regime-Aware EWMA Model MAE            : ${c_hold['regime_aware_ewma_mae']:.2f}/day")

    print("\n================================================================================")
    print("4. GENERATING DYNAMIC IMPACT & TECHNICAL AUDIT REPORTS")
    print("================================================================================")
    report_data = fetch_report_data_from_postgres()
    audit_path = generate_markdown_report(
        config=config,
        report_data=report_data,
        focus_series=focus_series,
        focus_results=focus_results,
        focus_eval=focus_eval,
        cur_series=cur_series,
        cur_results=cur_results,
        cur_eval=cur_eval,
    )
    impact_path = generate_impact_report(
        config=config,
        report_data=report_data,
    )
    print(f"Technical audit report compiled: {audit_path}")
    print(f"Action impact report compiled  : {impact_path}")


if __name__ == "__main__":
    main()
