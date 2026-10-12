"""Filtered read queries over the marts. Shared by the Streamlit dashboard and the HTML report."""

from dataclasses import dataclass, replace
from datetime import date

import duckdb
import pandas as pd

from .constants import SEGMENT_ORDER


@dataclass(frozen=True)  # hashable -> usable as a Streamlit cache key
class Filters:
    start: date | None = None
    end: date | None = None
    countries: tuple[str, ...] | None = None  # None = all
    categories: tuple[str, ...] | None = None


def _where(f: Filters, date_col: str = "order_date", month: bool = False, category: bool = True):
    clauses, params = [], []
    if f.start and f.end:
        if month:  # month-grain tables: snap the start to its month
            clauses.append(f"{date_col} between date_trunc('month', ?::date) and ?::date")
        else:
            clauses.append(f"{date_col} between ? and ?")
        params += [f.start, f.end]
    if f.countries is not None:
        clauses.append("list_contains(?, country)")
        params.append(list(f.countries))
    if category and f.categories is not None:
        clauses.append("list_contains(?, category)")
        params.append(list(f.categories))
    return ("where " + " and ".join(clauses)) if clauses else "", params


def _q(con: duckdb.DuckDBPyConnection, sql: str, params: list) -> pd.DataFrame:
    return con.execute(sql, params).df()


def bounds(con) -> tuple[date, date]:
    lo, hi = con.execute(
        "select min(order_date), max(order_date) from marts.fct_order_lines"
    ).fetchone()
    return lo, hi


def options(con) -> tuple[list[str], list[str]]:
    countries = con.execute(
        "select distinct country from marts.mart_daily_revenue order by 1"
    ).fetchall()
    categories = con.execute(
        "select distinct category from marts.mart_daily_revenue order by 1"
    ).fetchall()
    return [r[0] for r in countries], [r[0] for r in categories]


def kpis(con, f: Filters) -> dict:
    w, p = _where(f)
    row = _q(
        con,
        f"""select count(distinct order_id) as orders, count(distinct customer_id) as customers,
                   sum(quantity) as units, sum(gross_eur) as gross_eur, sum(refund_eur) as refund_eur,
                   sum(net_eur) as net_eur, count(*) as lines,
                   count(*) filter (where is_returned) as returned_lines
            from marts.fct_order_lines {w}""",
        p,
    ).iloc[0]
    k = {c: float(row[c]) if pd.notna(row[c]) else 0.0 for c in row.index}
    k["aov_eur"] = k["gross_eur"] / k["orders"] if k["orders"] else 0.0
    k["return_rate"] = k["returned_lines"] / k["lines"] if k["lines"] else 0.0
    return k


def daily_revenue(con, f: Filters) -> pd.DataFrame:
    w, p = _where(f)
    return _q(
        con,
        f"""select order_date, sum(net_eur) as net_eur, sum(gross_eur) as gross_eur
            from marts.mart_daily_revenue {w} group by order_date order by order_date""",
        p,
    )


def revenue_by_country(con, f: Filters) -> pd.DataFrame:
    w, p = _where(f)
    return _q(
        con,
        f"select country, sum(net_eur) as net_eur from marts.mart_daily_revenue {w} "
        "group by country order by net_eur desc",
        p,
    )


def monthly_customers(con, f: Filters) -> pd.DataFrame:
    """New vs returning customers per month (country + date filters; not category-aware)."""
    w, p = _where(f, "order_month", month=True, category=False)
    return _q(
        con,
        f"""select order_month, sum(new_customers) as new_customers,
                   sum(returning_customers) as returning_customers
            from marts.mart_monthly_kpis {w} group by order_month order by order_month""",
        p,
    )


def cohort_retention(con, f: Filters, max_months: int = 12) -> pd.DataFrame:
    w, p = _where(f, "cohort_month", month=True, category=False)
    df = _q(
        con,
        f"""select cohort_month, month_number, sum(active_customers) as active,
                   sum(cohort_size) as cohort_size
            from marts.mart_cohort_retention {w} group by cohort_month, month_number""",
        p,
    )
    df = df[df["month_number"] <= max_months].copy()
    df["retention"] = df["active"] / df["cohort_size"]
    return df.sort_values(["cohort_month", "month_number"])


def rfm_segments(con, f: Filters) -> pd.DataFrame:
    """RFM is a snapshot at the last order date, so only the country filter applies."""
    w, p = _where(replace(f, start=None, end=None), category=False)
    df = _q(
        con,
        f"""select segment, count(*) as customers, round(avg(recency_days), 1) as avg_recency_days,
                   round(avg(frequency), 2) as avg_orders, round(sum(monetary_eur), 2) as net_eur
            from marts.mart_rfm_customers {w} group by segment""",
        p,
    )
    df["segment"] = pd.Categorical(df["segment"], SEGMENT_ORDER, ordered=True)
    return df.sort_values("segment").reset_index(drop=True)


def products(con, f: Filters, limit: int = 25) -> pd.DataFrame:
    w, p = _where(f)
    return _q(
        con,
        f"""select product_name, category, sum(quantity) as units, count(*) as order_lines,
                   round(sum(gross_eur), 2) as gross_eur, round(sum(net_eur), 2) as net_eur,
                   round(count(*) filter (where is_returned) * 1.0 / count(*), 4) as return_rate
            from marts.fct_order_lines {w}
            group by product_id, product_name, category order by net_eur desc limit {int(limit)}""",
        p,
    )


def returns_by_category(con, f: Filters) -> pd.DataFrame:
    """Line grain, so a partial-month date range matches the return-rate KPI card exactly."""
    w, p = _where(f)
    return _q(
        con,
        f"""select category, count(*) as order_lines,
                   count(*) filter (where is_returned) as returned_lines,
                   count(*) filter (where is_returned) * 1.0 / count(*) as return_rate
            from marts.fct_order_lines {w} group by category order by return_rate desc""",
        p,
    )
