"""Streamlit dashboard: `streamlit run dashboard/app.py` (runs the pipeline first if needed)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # run without pip install

import duckdb  # noqa: E402
import streamlit as st  # noqa: E402

from pipeline import analytics as an  # noqa: E402
from pipeline import charts  # noqa: E402
from pipeline.config import Settings  # noqa: E402
from pipeline.runner import run_pipeline  # noqa: E402

st.set_page_config(page_title="E-commerce analytics", page_icon=None, layout="wide")
settings = Settings.from_env()


@st.cache_resource
def connection() -> duckdb.DuckDBPyConnection:
    if not settings.db_path.exists():
        with st.spinner("First run: generating data and building the warehouse..."):
            run_pipeline(settings, log=lambda _: None)
    return duckdb.connect(str(settings.db_path), read_only=True)


@st.cache_data(show_spinner=False)
def get(name: str, f: an.Filters):
    return getattr(an, name)(connection(), f)


con = connection()
lo, hi = an.bounds(con)
all_countries, all_categories = an.options(con)

st.sidebar.header("Filters")
dates = st.sidebar.date_input("Order date", (lo, hi), min_value=lo, max_value=hi)
countries = st.sidebar.multiselect("Country", all_countries, default=all_countries)
categories = st.sidebar.multiselect("Category", all_categories, default=all_categories)
st.sidebar.caption(
    "Category applies to revenue, KPIs, products and returns, not to customer-level views "
    "(cohorts, RFM, new vs returning). Cohorts and new vs returning are monthly, so they "
    "cover the whole months of the date range. The RFM snapshot ignores the date range."
)
if len(dates) != 2 or not countries or not categories:
    st.info("Pick a date range, at least one country and at least one category.")
    st.stop()

f = an.Filters(dates[0], dates[1], tuple(countries), tuple(categories))
k = get("kpis", f)

st.title("E-commerce analytics")
c = st.columns(5)
net = k["net_eur"]
c[0].metric("Net revenue", f"EUR {net / 1e6:,.2f}M" if net >= 1e6 else f"EUR {net:,.0f}")
c[1].metric("Orders", f"{k['orders']:,.0f}")
c[2].metric("Avg order value", f"EUR {k['aov_eur']:,.2f}")
c[3].metric("Customers", f"{k['customers']:,.0f}")
c[4].metric("Return rate", f"{k['return_rate']:.1%}")

t_rev, t_cohort, t_rfm, t_prod = st.tabs(["Revenue", "Cohorts", "RFM segments", "Products"])
with t_rev:
    st.subheader("Revenue trend")
    st.plotly_chart(charts.revenue_trend(get("daily_revenue", f)), width="stretch")
    left, right = st.columns(2)
    left.subheader("Revenue by country")
    left.plotly_chart(charts.revenue_by_country(get("revenue_by_country", f)), width="stretch")
    right.subheader("New vs returning customers")
    right.plotly_chart(
        charts.customers_new_vs_returning(get("monthly_customers", f)), width="stretch"
    )
with t_cohort:
    st.subheader("Cohort retention (share of cohort ordering N months after first order)")
    st.plotly_chart(charts.cohort_heatmap(get("cohort_retention", f)), width="stretch")
with t_rfm:
    seg = get("rfm_segments", f)
    st.subheader("Customers by RFM segment (snapshot at last order date)")
    st.plotly_chart(charts.rfm_segments(seg), width="stretch")
    st.dataframe(seg, hide_index=True, width="stretch")
with t_prod:
    left, right = st.columns([2, 1])
    left.subheader("Top products by net revenue")
    left.dataframe(get("products", f), hide_index=True, width="stretch")
    right.subheader("Return rate by category")
    right.plotly_chart(charts.returns_by_category(get("returns_by_category", f)), width="stretch")
