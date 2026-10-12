"""Mart calculations verified by hand on the 3-customer fixture in conftest.py.

FIXTURE NOTES (EUR rate: GBP = 1.2 in every month; cancelled orders are excluded)
  O1 c1 DE 2024-01-10  item1 2x Shirt @50          = 100
                       item2 1x Phone @200 -10%    = 180            gross 280
  O2 c2 DE 2024-01-15  item3 1x Shirt @50, RETURNED = 50            gross 50, refund 50
  O3 c1 DE 2024-02-05  item4 1x Shirt @50          = 50
  O4 c3 GB 2024-02-10  item5 1x Phone @100 GBP     = 120 EUR
  O5 c2 DE 2024-02-20  CANCELLED (ignored everywhere)
  O6 c3 GB 2024-03-03  item7 2x Shirt @40 GBP -25% = 60 GBP = 72 EUR
  => gross 572, refunds 50, net 522, 5 completed orders
"""

import pandas as pd
import pytest
from conftest import ROOT, d

from pipeline import analytics as an
from pipeline.runner import lineage_mermaid, load_models, run_models


def q(con, sql):
    return con.execute(sql).df()


def test_currency_normalisation_to_eur(mart_con):
    lines = q(mart_con, "select order_item_id, gross_local, gross_eur from marts.fct_order_lines")
    eur = dict(zip(lines["order_item_id"], lines["gross_eur"], strict=True))
    assert eur[5] == pytest.approx(120.0)  # 100 GBP * 1.2
    assert eur[7] == pytest.approx(72.0)  # 2*40*0.75 = 60 GBP * 1.2
    assert eur[2] == pytest.approx(180.0)  # EUR order, 10% discount
    assert 6 not in eur  # line of the cancelled order


def test_totals(mart_con):
    row = q(
        mart_con,
        "select sum(gross_eur) g, sum(refund_eur) r, sum(net_eur) n from marts.fct_order_lines",
    )
    assert row.iloc[0].tolist() == pytest.approx([572.0, 50.0, 522.0])
    assert an.kpis(mart_con, an.Filters())["orders"] == 5


def test_daily_revenue(mart_con):
    df = q(mart_con, "select * from marts.mart_daily_revenue")
    row = df[(df.order_date == pd.Timestamp("2024-01-10")) & (df.category == "Apparel")].iloc[0]
    assert (row.country, row.orders, row.units, row.gross_eur) == ("DE", 1, 2, 100.0)
    jan15 = df[df.order_date == pd.Timestamp("2024-01-15")].iloc[0]
    assert (jan15.gross_eur, jan15.refund_eur, jan15.net_eur) == (50.0, 50.0, 0.0)
    assert df.net_eur.sum() == pytest.approx(522.0)


def test_monthly_kpis_new_vs_returning(mart_con):
    df = q(mart_con, "select * from marts.mart_monthly_kpis").set_index(["order_month", "country"])
    jan = df.loc[(pd.Timestamp("2024-01-01"), "DE")]
    assert (jan.orders, jan.customers, jan.new_customers, jan.returning_customers) == (2, 2, 2, 0)
    assert (jan.gross_eur, jan.refund_eur, jan.net_eur, jan.aov_eur) == (330, 50, 280, 165)
    feb_de = df.loc[(pd.Timestamp("2024-02-01"), "DE")]
    assert (feb_de.new_customers, feb_de.returning_customers, feb_de.aov_eur) == (0, 1, 50)
    feb_gb = df.loc[(pd.Timestamp("2024-02-01"), "GB")]
    assert (feb_gb.new_customers, feb_gb.returning_customers, feb_gb.aov_eur) == (1, 0, 120)
    mar_gb = df.loc[(pd.Timestamp("2024-03-01"), "GB")]
    assert (mar_gb.returning_customers, mar_gb.gross_eur) == (1, 72)


def test_cohort_retention_matrix_is_complete(mart_con):
    df = q(
        mart_con, "select * from marts.mart_cohort_retention order by cohort_month, month_number"
    )
    got = [(r.cohort_month.strftime("%Y-%m"), r.country, r.month_number, r.cohort_size,
            r.active_customers) for r in df.itertuples()]  # fmt: skip
    assert got == [
        ("2024-01", "DE", 0, 2, 2),
        ("2024-01", "DE", 1, 2, 1),  # c1 orders again in Feb
        ("2024-01", "DE", 2, 2, 0),  # zero rows are present, not missing
        ("2024-02", "GB", 0, 1, 1),
        ("2024-02", "GB", 1, 1, 1),  # c3 orders again in Mar
    ]
    ret = an.cohort_retention(mart_con, an.Filters()).set_index(["cohort_month", "month_number"])
    assert ret.loc[(pd.Timestamp("2024-01-01"), 1), "retention"] == pytest.approx(0.5)


def test_rfm(mart_con):
    df = q(mart_con, "select * from marts.mart_rfm_customers").set_index("customer_id")
    # snapshot = last order (2024-03-03) + 1 day
    assert df.recency_days.to_dict() == {1: 28, 2: 49, 3: 1}
    assert df.frequency.to_dict() == {1: 2, 2: 1, 3: 2}
    assert df.monetary_eur.to_dict() == {1: 330.0, 2: 0.0, 3: 192.0}
    assert df.r_score.to_dict() == {1: 2, 2: 1, 3: 3}
    assert df.m_score.to_dict() == {1: 3, 2: 1, 3: 2}
    assert df.segment.to_dict() == {1: "Hibernating", 2: "Lost", 3: "Needs Attention"}


def test_rfm_tied_recency_shares_one_r_score(raw_con):
    raw_con.execute(
        "insert into raw.customers values (4, 'd@x.com', 'DE', '2024-01-01', 'organic')"
    )
    raw_con.execute("insert into raw.orders values (7, 4, '2024-03-03', 'EUR', 'completed')")
    raw_con.execute("insert into raw.order_items values (8, 7, 10, 1, 50.0, 0.0)")
    run_models(raw_con, ROOT / "sql")
    r = q(raw_con, "select customer_id, r_score from marts.mart_rfm_customers")
    r = r.set_index("customer_id").r_score
    assert r[3] == r[4]  # same last order date as c3, so the same R, whatever the customer_id


def test_top_products_and_returns(mart_con):
    p = q(mart_con, "select * from marts.mart_top_products order by revenue_rank").set_index(
        "product_name"
    )
    assert p.loc["Phone", ["revenue_rank", "units", "gross_eur", "net_eur"]].tolist() == [
        1,
        2,
        300,
        300,
    ]
    shirt = p.loc["Shirt"]
    assert (shirt.revenue_rank, shirt.units, shirt.gross_eur, shirt.net_eur) == (2, 6, 272, 222)
    assert shirt.return_rate == 0.25
    r = q(mart_con, "select * from marts.mart_return_rate_by_category")
    by_cat = r.groupby("category")[["order_lines", "returned_lines"]].sum()
    assert by_cat.loc["Apparel"].tolist() == [4, 1]
    assert by_cat.loc["Electronics"].tolist() == [2, 0]
    ui = an.returns_by_category(mart_con, an.Filters()).set_index("category")
    assert ui.loc["Apparel", "return_rate"] == 0.25


def test_filters(mart_con):
    f = an.Filters(d("2024-02-01"), d("2024-02-29"), ("GB",), ("Electronics",))
    k = an.kpis(mart_con, f)
    assert (k["orders"], k["net_eur"], k["customers"]) == (1, 120.0, 1)
    assert an.daily_revenue(mart_con, f)["net_eur"].tolist() == [120.0]
    # partial month: the return-rate chart uses the exact dates, like the KPI cards
    jan = an.Filters(d("2024-01-01"), d("2024-01-12"))  # O1 only; O2's returned shirt is 01-15
    r = an.returns_by_category(mart_con, jan).set_index("category")
    assert r.loc["Apparel", ["order_lines", "returned_lines"]].tolist() == [1, 0]
    assert an.kpis(mart_con, jan)["return_rate"] == 0.0


def test_all_marts_reconcile(mart_con):
    sums = q(
        mart_con,
        """select (select sum(net_eur) from marts.fct_order_lines) fct,
                  (select sum(net_eur) from marts.mart_daily_revenue) daily,
                  (select sum(net_eur) from marts.mart_monthly_kpis) monthly,
                  (select sum(net_eur) from marts.mart_top_products) prod,
                  (select sum(monetary_eur) from marts.mart_rfm_customers) rfm""",
    ).iloc[0]
    assert sums.tolist() == pytest.approx([522.0] * 5)


def test_model_graph_is_valid_and_ordered():
    names = [m.name for m in load_models(ROOT / "sql")]
    assert names.index("stg_orders") < names.index("int_order_lines") < names.index("int_orders")
    assert names.index("int_orders") < names.index("mart_cohort_retention")
    assert "stg_orders --> int_order_lines" in lineage_mermaid(ROOT / "sql")


def test_empty_sql_dir_fails_instead_of_building_nothing(tmp_path):
    with pytest.raises(FileNotFoundError, match="No SQL models"):
        load_models(tmp_path)
