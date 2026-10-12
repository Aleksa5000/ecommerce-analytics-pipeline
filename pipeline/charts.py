"""Plotly figure builders shared by the dashboard and the static report."""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

BLUE, AMBER, GREY = "#2563eb", "#f59e0b", "#94a3b8"


def _style(fig: go.Figure, height: int = 340) -> go.Figure:
    fig.update_layout(
        template="plotly_white", height=height, margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(orientation="h", y=1.12, x=0), font=dict(size=13),
    )  # fmt: skip
    return fig


def revenue_trend(daily: pd.DataFrame) -> go.Figure:
    d = daily.assign(rolling=daily["net_eur"].rolling(28, min_periods=7).mean())
    fig = go.Figure()
    fig.add_bar(x=d["order_date"], y=d["net_eur"], name="Daily net revenue", marker_color="#bfdbfe")
    fig.add_scatter(x=d["order_date"], y=d["rolling"], name="28-day average",
                    line=dict(color=BLUE, width=2.5))  # fmt: skip
    fig.update_yaxes(title="EUR", tickformat=",")
    return _style(fig)


def customers_new_vs_returning(m: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_bar(x=m["order_month"], y=m["new_customers"], name="New", marker_color=BLUE)
    fig.add_bar(x=m["order_month"], y=m["returning_customers"], name="Returning",
                marker_color=AMBER)  # fmt: skip
    fig.update_layout(barmode="stack")
    fig.update_yaxes(title="Active customers")
    return _style(fig)


def cohort_heatmap(c: pd.DataFrame) -> go.Figure:
    pivot = c.pivot(index="cohort_month", columns="month_number", values="retention")
    labels = [d.strftime("%Y-%m") for d in pd.to_datetime(pivot.index)]
    fig = go.Figure(go.Heatmap(
        z=pivot.to_numpy() * 100, x=pivot.columns, y=labels, colorscale="Blues",
        zmin=0, zmax=25, colorbar=dict(title="% active"),
        hovertemplate="Cohort %{y}<br>Month +%{x}: %{z:.1f}%<extra></extra>",
    ))  # fmt: skip
    fig.update_yaxes(autorange="reversed", title="Cohort (first order)")
    fig.update_xaxes(title="Months since first order", dtick=1)
    return _style(fig, height=520)


def rfm_segments(seg: pd.DataFrame) -> go.Figure:
    fig = px.bar(seg, x="segment", y="customers", text="customers", color_discrete_sequence=[BLUE])
    fig.update_traces(textposition="outside", cliponaxis=False)
    fig.update_xaxes(title=None)
    fig.update_yaxes(title="Customers")
    return _style(fig)


def returns_by_category(r: pd.DataFrame) -> go.Figure:
    fig = px.bar(r, x="return_rate", y="category", orientation="h", color_discrete_sequence=[AMBER])
    fig.update_xaxes(tickformat=".0%", title="Return rate (returned lines / lines)")
    fig.update_yaxes(title=None, categoryorder="total ascending")
    return _style(fig, height=300)


def revenue_by_country(c: pd.DataFrame) -> go.Figure:
    fig = px.bar(c, x="country", y="net_eur", color_discrete_sequence=[BLUE])
    fig.update_yaxes(title="Net revenue (EUR)", tickformat=",")
    fig.update_xaxes(title=None)
    return _style(fig, height=300)
