"""Declarative data quality checks on the raw layer.

Each check is a query returning the *failing rows*; a check passes when it returns none.
"""

from dataclasses import dataclass

import duckdb
import pandas as pd

from .constants import CATEGORIES, COUNTRY_CURRENCY, ORDER_STATUSES


class DataQualityError(Exception):
    """Raised when at least one check fails. The message lists only the failed checks."""


@dataclass(frozen=True)
class Check:
    name: str
    kind: str
    failing_rows_sql: str


@dataclass
class Result:
    check: Check
    failed_rows: int
    sample: pd.DataFrame

    @property
    def passed(self) -> bool:
        return self.failed_rows == 0


def not_null(table: str, col: str) -> Check:
    sql = f"select * from raw.{table} where {col} is null"
    return Check(f"{table}.{col} not null", "not_null", sql)


def unique(table: str, *cols: str) -> Check:
    c = ", ".join(cols)
    sql = f"select {c}, count(*) as n from raw.{table} group by {c} having count(*) > 1"
    return Check(f"{table}.{'+'.join(cols)} unique", "unique", sql)


def relationship(table: str, col: str, to_table: str, to_col: str) -> Check:
    sql = (
        f"select t.* from raw.{table} t left join raw.{to_table} u on t.{col} = u.{to_col} "
        f"where t.{col} is not null and u.{to_col} is null"
    )
    return Check(f"{table}.{col} references {to_table}.{to_col}", "relationship", sql)


def accepted_values(table: str, col: str, values) -> Check:
    lst = ", ".join(f"'{v}'" for v in values)
    sql = f"select * from raw.{table} where {col} is not null and {col} not in ({lst})"
    return Check(f"{table}.{col} in accepted values", "accepted_values", sql)


def expression(table: str, name: str, ok_expr: str) -> Check:
    """Every row must satisfy ok_expr (a NULL result counts as a failure)."""
    sql = f"select * from raw.{table} where not coalesce(({ok_expr}), false)"
    return Check(f"{table}: {name}", "expression", sql)


def default_checks() -> list[Check]:
    return [
        not_null("customers", "customer_id"),
        unique("customers", "customer_id"),
        not_null("customers", "signup_date"),
        accepted_values("customers", "country", COUNTRY_CURRENCY),
        not_null("products", "product_id"),
        unique("products", "product_id"),
        accepted_values("products", "category", CATEGORIES),
        expression("products", "list_price_eur > 0", "list_price_eur > 0"),
        not_null("orders", "order_id"),
        unique("orders", "order_id"),
        not_null("orders", "customer_id"),
        not_null("orders", "order_date"),
        relationship("orders", "customer_id", "customers", "customer_id"),
        Check(  # int_order_lines inner-joins FX: an order without a rate would vanish from the marts
            "orders.currency+month references fx_rates.currency+month",
            "relationship",
            "select o.* from raw.orders o left join raw.fx_rates f on f.currency = o.currency "
            "and date_trunc('month', f.month::date) = date_trunc('month', o.order_date::date) "
            "where f.currency is null",
        ),
        accepted_values("orders", "status", ORDER_STATUSES),
        accepted_values("orders", "currency", set(COUNTRY_CURRENCY.values())),
        not_null("order_items", "order_item_id"),
        unique("order_items", "order_item_id"),
        relationship("order_items", "order_id", "orders", "order_id"),
        relationship("order_items", "product_id", "products", "product_id"),
        expression("order_items", "quantity > 0", "quantity > 0"),
        expression("order_items", "unit_price > 0", "unit_price > 0"),
        expression(
            "order_items", "discount_pct in [0, 1)", "discount_pct >= 0 and discount_pct < 1"
        ),
        unique("returns", "return_id"),
        unique("returns", "order_item_id"),
        relationship("returns", "order_item_id", "order_items", "order_item_id"),
        unique("fx_rates", "month", "currency"),
        expression("fx_rates", "eur_per_unit > 0", "eur_per_unit > 0"),
    ]


def run_checks(con: duckdb.DuckDBPyConnection, checks: list[Check] | None = None) -> list[Result]:
    results = []
    for chk in checks or default_checks():
        n = con.execute(f"select count(*) from ({chk.failing_rows_sql})").fetchone()[0]
        sample = con.execute(f"{chk.failing_rows_sql} limit 5").df() if n else pd.DataFrame()
        results.append(Result(chk, n, sample))
    return results


def format_report(results: list[Result]) -> str:
    failed = [r for r in results if not r.passed]
    lines = [f"Data quality: {len(results) - len(failed)}/{len(results)} checks passed"]
    for r in results:
        if r.passed:
            lines.append(f"  PASS  {r.check.name}")
        else:
            lines.append(f"  FAIL  {r.check.name}  ({r.failed_rows} failing rows)")
            lines.append("        " + r.sample.to_string(index=False).replace("\n", "\n        "))
    return "\n".join(lines)


def assert_ok(results: list[Result]) -> None:
    failed = [r for r in results if not r.passed]
    if failed:  # the full report is logged by the runner; the error repeats only the failures
        detail = format_report(failed).split("\n", 1)[1]  # drop the "x/y passed" header
        raise DataQualityError(f"{len(failed)} of {len(results)} checks failed:\n{detail}")


def to_frame(results: list[Result]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"check_name": r.check.name, "kind": r.check.kind, "failed_rows": r.failed_rows}
            for r in results
        ]
    )
