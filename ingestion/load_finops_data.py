import argparse
import csv
import gzip
import io
import os
import urllib.request
from pathlib import Path
from typing import Iterator, Dict, Any, List

import dlt
from dotenv import load_dotenv
import pyarrow.parquet as pq

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ENV_PATH)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

FOCUS_100K_URL = (
    "https://raw.githubusercontent.com/FinOps-Open-Cost-and-Usage-Spec/"
    "FOCUS-Sample-Data/main/FOCUS-1.0/focus_sample_100000.csv.gz"
)

CUR_PARQUET_URLS = [
    (
        "2018-10",
        "https://raw.githubusercontent.com/First-Cloud-Journey/000040-CUR/main/Oct2018-WorkshopCUR-00001.snappy.parquet",
    ),
    (
        "2018-11",
        "https://raw.githubusercontent.com/First-Cloud-Journey/000040-CUR/main/Nov2018-WorkshopCUR-00001.snappy.parquet",
    ),
    (
        "2018-12",
        "https://raw.githubusercontent.com/First-Cloud-Journey/000040-CUR/main/Dec2018-WorkshopCUR-00001.snappy.parquet",
    ),
]

CUR_SELECTED_COLUMNS = [
    "identity_line_item_id",
    "identity_time_interval",
    "bill_billing_period_start_date",
    "line_item_usage_account_id",
    "line_item_usage_start_date",
    "line_item_usage_end_date",
    "line_item_product_code",
    "line_item_line_item_type",
    "line_item_usage_type",
    "line_item_operation",
    "line_item_resource_id",
    "line_item_unblended_cost",
    "line_item_blended_cost",
    "pricing_term",
    "product_instance_type",
    "product_region",
    "reservation_reservation_a_r_n",
    "reservation_effective_cost",
    "reservation_amortized_upfront_cost_for_usage",
    "reservation_recurring_fee_for_usage",
    "reservation_unused_amortized_upfront_fee_for_billing_period",
    "reservation_unused_recurring_fee",
]


def ensure_cached_file(url: str, local_name: str) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    target = DATA_DIR / local_name
    if not target.exists():
        print(f"Downloading {url} -> {target} ...")
        urllib.request.urlretrieve(url, target)
    return target


@dlt.resource(
    name="focus_cost_export",
    write_disposition="replace",
    primary_key="Id",
)
def extract_focus_cost_export() -> Iterator[List[Dict[str, Any]]]:
    gz_path = ensure_cached_file(FOCUS_100K_URL, "focus_sample_100000.csv.gz")
    batch: List[Dict[str, Any]] = []
    batch_size = 10000
    with gzip.open(gz_path, mode="rt", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            batch.append(row)
            if len(batch) >= batch_size:
                yield batch
                batch = []
        if batch:
            yield batch


@dlt.resource(
    name="aws_cur_export",
    write_disposition="replace",
    primary_key=["identity_line_item_id", "identity_time_interval"],
)
def extract_aws_cur_export() -> Iterator[List[Dict[str, Any]]]:
    for period, url in CUR_PARQUET_URLS:
        fname = f"cur_{period}.snappy.parquet"
        pq_path = ensure_cached_file(url, fname)
        table = pq.read_table(pq_path, columns=CUR_SELECTED_COLUMNS)
        for rb in table.to_batches(max_chunksize=15000):
            yield rb.to_pylist()


def build_destination(dest_type: str):
    if dest_type == "postgres":
        host = os.environ["PG_HOST"]
        port = int(os.environ.get("PG_PORT", "5432"))
        user = os.environ["PG_USER"]
        password = os.environ["PG_PASSWORD"]
        database = os.environ["PG_DATABASE"]
        creds = f"postgresql://{user}:{password}@{host}:{port}/{database}"
        return dlt.destinations.postgres(credentials=creds)
    if dest_type == "duckdb":
        db_path = str(DATA_DIR / "finops.duckdb")
        return dlt.destinations.duckdb(credentials=db_path)
    if dest_type == "bigquery":
        return "bigquery"
    raise ValueError(f"Unsupported destination: {dest_type}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest FOCUS 1.0 and raw AWS CUR into warehouse via dlt.")
    parser.add_argument(
        "--destination",
        choices=["postgres", "duckdb", "bigquery"],
        default="postgres",
        help="Target dlt destination.",
    )
    parser.add_argument(
        "--dataset",
        default="finops_raw",
        help="Target schema / dataset name.",
    )
    args = parser.parse_args()

    pipeline = dlt.pipeline(
        pipeline_name="cloud_finops_ingestion",
        destination=build_destination(args.destination),
        dataset_name=args.dataset,
    )

    print(f"Running dlt ingestion -> destination={args.destination}, dataset={args.dataset}")
    load_info = pipeline.run([extract_focus_cost_export(), extract_aws_cur_export()])
    print(load_info)


if __name__ == "__main__":
    main()

