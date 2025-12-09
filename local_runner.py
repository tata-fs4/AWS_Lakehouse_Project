"""
Local QA runner to simulate the Airflow/dbt/GE pipeline using sample data.
It validates the raw datasets against the expectation suites, builds staging
frames, and produces the `fct_daily_store_metrics` fact table.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

import pandas as pd

BASE_DIR = Path(__file__).parent
SAMPLES_DIR = BASE_DIR / "samples"
EXPECTATIONS_DIR = BASE_DIR / "great_expectations" / "expectations"

DOMAINS = {
    "erp": {
        "file": SAMPLES_DIR / "erp_orders.csv",
        "dataset": "erp_orders",
        "expectation": EXPECTATIONS_DIR / "erp_orders.json",
    },
    "crm": {
        "file": SAMPLES_DIR / "crm_leads.csv",
        "dataset": "crm_leads",
        "expectation": EXPECTATIONS_DIR / "crm_leads.json",
    },
    "web": {
        "file": SAMPLES_DIR / "web_events.json",
        "dataset": "web_events",
        "expectation": EXPECTATIONS_DIR / "web_events.json",
    },
    "product": {
        "file": SAMPLES_DIR / "products.csv",
        "dataset": "products",
        "expectation": EXPECTATIONS_DIR / "products.json",
    },
}


class ExpectationFailure(Exception):
    pass


def _load_df(domain: str) -> pd.DataFrame:
    file_path = DOMAINS[domain]["file"]
    if file_path.suffix == ".json":
        df = pd.read_json(file_path, lines=True)
    else:
        df = pd.read_csv(file_path)
    return df


def _ensure_date_column(df: pd.DataFrame, column: str = "dt") -> pd.DataFrame:
    df = df.copy()
    df[column] = pd.to_datetime(df[column]).dt.date
    return df


def _validate_expectations(df: pd.DataFrame, expectation_file: Path) -> List[str]:
    """Validate a dataframe against a tiny subset of GE-like expectations."""
    with expectation_file.open() as f:
        cfg = json.load(f)

    messages: List[str] = []

    for exp in cfg.get("expectations", []):
        etype = exp["expectation_type"]
        kwargs = exp.get("kwargs", {})

        if etype == "expect_table_columns_to_match_ordered_list":
            expected = kwargs["column_list"]
            if list(df.columns) != expected:
                raise ExpectationFailure(
                    f"Column order mismatch. Expected {expected}, got {list(df.columns)}"
                )
            messages.append("Column order validated")

        elif etype == "expect_column_values_to_not_be_null":
            column = kwargs["column"]
            if df[column].isnull().any():
                raise ExpectationFailure(f"Null values found in {column}")
            messages.append(f"Column {column} not null validated")

        elif etype == "expect_column_values_to_be_between":
            column = kwargs["column"]
            min_value = kwargs.get("min_value")
            if min_value is not None and (df[column] < min_value).any():
                raise ExpectationFailure(f"Values in {column} below {min_value}")
            messages.append(f"Column {column} minimum {min_value} validated")

        elif etype == "expect_column_values_to_match_regex":
            column = kwargs["column"]
            regex = kwargs["regex"]
            if not df[column].astype(str).str.match(regex).all():
                raise ExpectationFailure(f"Regex validation failed for {column}")
            messages.append(f"Column {column} regex {regex} validated")

        else:
            raise ExpectationFailure(f"Unsupported expectation type: {etype}")

    return messages


def stage_frames(raw_frames: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    staging = {}

    orders = _ensure_date_column(raw_frames["erp"]).assign(
        order_id=lambda d: d["order_id"].astype(int),
        order_value=lambda d: d["order_value"].astype(float),
    )
    staging["stg_erp_orders"] = orders[
        ["order_id", "customer_id", "store_id", "dt", "order_value", "status"]
    ]

    crm = _ensure_date_column(raw_frames["crm"])
    staging["stg_crm_leads"] = crm[
        ["lead_id", "name", "email", "source", "status", "store_id", "dt"]
    ]

    products = _ensure_date_column(raw_frames["product"])
    staging["stg_products"] = products[
        ["product_id", "name", "category", "price", "active", "store_id", "dt"]
    ]

    web = _ensure_date_column(raw_frames["web"])
    staging["stg_web_events"] = web[
        ["event_id", "visitor_id", "store_id", "dt", "page", "event_type", "metadata"]
    ]

    return staging


def build_fact(staging: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    orders = staging["stg_erp_orders"].groupby(["store_id", "dt"]).agg(
        revenue=("order_value", "sum"),
        order_count=("order_id", "count"),
    )

    leads = staging["stg_crm_leads"].groupby(["store_id", "dt"]).agg(
        converted_leads=("status", lambda s: (s == "converted").sum())
    )

    web = staging["stg_web_events"].groupby(["store_id", "dt"]).agg(
        sessions=("event_id", "count")
    )

    fact = orders.join(leads, how="outer").join(web, how="outer").reset_index()
    fact[["revenue", "order_count", "converted_leads", "sessions"]] = fact[
        ["revenue", "order_count", "converted_leads", "sessions"]
    ].fillna(0)
    fact["dt"] = pd.to_datetime(fact["dt"]).dt.date
    fact = fact.sort_values(["store_id", "dt"]).reset_index(drop=True)
    return fact


def write_outputs(output_dir: Path, staging: Dict[str, pd.DataFrame], fact: pd.DataFrame) -> None:
    raw_dir = output_dir / "curated"
    raw_dir.mkdir(parents=True, exist_ok=True)

    for name, frame in staging.items():
        frame.to_csv(raw_dir / f"{name}.csv", index=False)

    fact.to_csv(raw_dir / "fct_daily_store_metrics.csv", index=False)


def run_pipeline(output_dir: Path) -> None:
    print(f"Running local pipeline into {output_dir} ...")
    raw_frames: Dict[str, pd.DataFrame] = {}

    for domain, cfg in DOMAINS.items():
        df = _load_df(domain)
        messages = _validate_expectations(df, cfg["expectation"])
        print(f"Validation for {domain} ({cfg['dataset']}): {', '.join(messages)}")
        raw_frames[domain] = df

    staging = stage_frames(raw_frames)
    fact = build_fact(staging)
    write_outputs(output_dir, staging, fact)
    print("Fact table preview:")
    print(fact)
    print(f"Artifacts written to {output_dir / 'curated'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Local QA runner for the lakehouse pipeline")
    parser.add_argument("--output-dir", default=str(BASE_DIR / "local_output"), help="Destination directory for generated artifacts")
    args = parser.parse_args()

    run_pipeline(Path(args.output_dir))
