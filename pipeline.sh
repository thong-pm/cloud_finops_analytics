#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

if [ -f ".env" ]; then
    set -a
    source .env
    set +a
fi

TARGET="${1:-local}"
PYTHON_BIN="${SCRIPT_DIR}/.venv/bin/python"
DBT_BIN="${SCRIPT_DIR}/.venv/bin/dbt"

echo "[1/3] Running dlt ingestion (focus_cost_export + aws_cur_export)..."
if [ "${TARGET}" = "local" ]; then
    "${PYTHON_BIN}" ingestion/load_finops_data.py --destination postgres --dataset finops_raw
else
    "${PYTHON_BIN}" ingestion/load_finops_data.py --destination bigquery --dataset finops_raw
fi

echo "[2/3] Running dbt build (seeds, staging views, incremental & table marts, reconciliation tests)..."
cd "${SCRIPT_DIR}/dbt_finops"
"${DBT_BIN}" build --profiles-dir . --target "${TARGET}"
cd "${SCRIPT_DIR}"

if [ "${TARGET}" = "local" ]; then
    echo "[3/3] Running statistical anomaly detection, dynamic backtest & markdown report generation..."
    "${PYTHON_BIN}" analysis/spike_and_forecast_eval.py
    echo "Action Impact report available at: analysis/reports/impact_report.md"
    echo "Technical Audit report available at: analysis/reports/pipeline_audit_report.md"
fi

echo "Pipeline completed cleanly for target=${TARGET}."

