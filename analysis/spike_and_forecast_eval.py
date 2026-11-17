import math
import os
from pathlib import Path
import statistics
from dataclasses import dataclass
from typing import List, Tuple, Dict, Any, Set

import psycopg2
import yaml

CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"


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
    }
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            user_config = yaml.safe_load(f) or {}
            for section in ("anomaly_detection", "backtest"):
                if section in user_config and isinstance(user_config[section], dict):
                    config[section].update(user_config[section])
    return config


def fetch_daily_series_from_postgres() -> Tuple[List[DailyObservation], List[DailyObservation]]:
    conn = psycopg2.connect(
        host=os.environ["PG_HOST"],
        port=int(os.environ.get("PG_PORT", "5432")),
        user=os.environ["PG_USER"],
        password=os.environ["PG_PASSWORD"],
        dbname=os.environ["PG_DATABASE"],
    )
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
        # Enforce configurable scale floor so zero-variance sequences never cause division by zero
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

        # Update EWMA state with spike-stripped or shift-reanchored baseline
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
    # 1. Post-Spike Recovery Window: Evaluates normal days immediately following stripped transient spikes
    spike_recovery_indices: Set[int] = set()
    for idx, res in enumerate(anomaly_results):
        if res.classification == "transient_spike_stripped":
            for offset in range(1, post_spike_eval_days + 1):
                eval_idx = idx + offset
                if eval_idx < len(series) and anomaly_results[eval_idx].classification == "normal":
                    spike_recovery_indices.add(eval_idx)

    # 2. Workload Shift Window: Evaluates days tagged as confirmed multi-day regime shifts
    shift_indices = {
        idx for idx, res in enumerate(anomaly_results)
        if res.classification == "regime_shift_reanchored" and idx >= window_size
    }

    # 3. Trailing Out-of-Sample Window: Evaluates the final configured percentage of the series
    holdout_len = max(window_size, int(len(series) * trailing_holdout_ratio))
    trailing_indices = set(range(max(window_size, len(series) - holdout_len), len(series)))

    return {
        "post_spike": evaluate_forecast_on_indices(series, anomaly_results, spike_recovery_indices, window_size, ewma_alpha),
        "regime_shift": evaluate_forecast_on_indices(series, anomaly_results, shift_indices, window_size, ewma_alpha),
        "trailing_holdout": evaluate_forecast_on_indices(series, anomaly_results, trailing_indices, window_size, ewma_alpha),
    }


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


if __name__ == "__main__":
    main()
