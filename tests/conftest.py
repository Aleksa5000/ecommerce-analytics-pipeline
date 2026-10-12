"""Tiny hand-built dataset (see FIXTURE NOTES in test_marts.py) loaded into the raw schema."""

from datetime import date

import duckdb
import pandas as pd
import pytest

from pipeline.config import ROOT


def d(s: str) -> date:
    return date.fromisoformat(s)


def raw_frames() -> dict[str, pd.DataFrame]:
    fx = [(d(f"2024-0{m}-01"), cur, rate) for m in (1, 2, 3)
          for cur, rate in (("EUR", 1.0), ("GBP", 1.2), ("USD", 0.9), ("PLN", 0.23), ("SEK", 0.09))]  # fmt: skip
    return {
        "customers": pd.DataFrame(
            [
                (1, "a@x.com", "DE", d("2024-01-02"), "organic"),
                (2, "b@x.com", "DE", d("2024-01-05"), "social"),
                (3, "c@x.com", "GB", d("2024-01-10"), "email"),
            ],
            columns=["customer_id", "email", "country", "signup_date", "acquisition_channel"],
        ),
        "products": pd.DataFrame(
            [(10, "Shirt", "Apparel", 50.0), (20, "Phone", "Electronics", 200.0)],
            columns=["product_id", "product_name", "category", "list_price_eur"],
        ),
        "orders": pd.DataFrame(
            [
                (1, 1, d("2024-01-10"), "EUR", "completed"),
                (2, 2, d("2024-01-15"), "EUR", "completed"),
                (3, 1, d("2024-02-05"), "EUR", "completed"),
                (4, 3, d("2024-02-10"), "GBP", "completed"),
                (5, 2, d("2024-02-20"), "EUR", "cancelled"),
                (6, 3, d("2024-03-03"), "GBP", "completed"),
            ],
            columns=["order_id", "customer_id", "order_date", "currency", "status"],
        ),
        "order_items": pd.DataFrame(
            [
                (1, 1, 10, 2, 50.0, 0.0),
                (2, 1, 20, 1, 200.0, 0.1),
                (3, 2, 10, 1, 50.0, 0.0),
                (4, 3, 10, 1, 50.0, 0.0),
                (5, 4, 20, 1, 100.0, 0.0),
                (6, 5, 10, 5, 50.0, 0.0),
                (7, 6, 10, 2, 40.0, 0.25),
            ],
            columns=[
                "order_item_id",
                "order_id",
                "product_id",
                "quantity",
                "unit_price",
                "discount_pct",
            ],  # fmt: skip
        ),
        "returns": pd.DataFrame(
            [(1, 3, d("2024-01-20"), "defective")],
            columns=["return_id", "order_item_id", "return_date", "reason"],
        ),
        "fx_rates": pd.DataFrame(fx, columns=["month", "currency", "eur_per_unit"]),
    }


def load_raw(con: duckdb.DuckDBPyConnection, frames: dict[str, pd.DataFrame]) -> None:
    con.execute("create schema if not exists raw")
    for name, df in frames.items():
        con.register("tmp_df", df)
        con.execute(f"create or replace table raw.{name} as select * from tmp_df")
        con.unregister("tmp_df")


@pytest.fixture
def raw_con():
    con = duckdb.connect()
    load_raw(con, raw_frames())
    yield con
    con.close()


@pytest.fixture
def mart_con(raw_con):
    from pipeline.runner import run_models

    run_models(raw_con, ROOT / "sql")
    return raw_con
