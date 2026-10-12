"""Every kind of check must stay silent on clean data and flag exactly the injected defect."""

import pytest

from pipeline import quality
from pipeline.quality import DataQualityError

# (SQL that corrupts the clean fixture, name of the one check that must fail)
BAD_DATA = [
    ("update raw.customers set customer_id = null where customer_id = 3",
     "customers.customer_id not null"),
    ("insert into raw.customers values (1, 'dup@x.com', 'DE', date '2024-01-01', 'organic')",
     "customers.customer_id unique"),
    ("update raw.customers set country = 'XX' where customer_id = 1",
     "customers.country in accepted values"),
    ("update raw.products set category = 'Toys' where product_id = 10",
     "products.category in accepted values"),
    ("update raw.products set list_price_eur = -5 where product_id = 10",
     "products: list_price_eur > 0"),
    ("update raw.orders set customer_id = 99 where order_id = 1",
     "orders.customer_id references customers.customer_id"),
    ("update raw.orders set status = 'shipped' where order_id = 1",
     "orders.status in accepted values"),
    ("update raw.orders set order_date = null where order_id = 1", "orders.order_date not null"),
    ("update raw.order_items set product_id = 777 where order_item_id = 1",
     "order_items.product_id references products.product_id"),
    ("update raw.order_items set order_id = 777 where order_item_id = 1",
     "order_items.order_id references orders.order_id"),
    ("update raw.order_items set quantity = 0 where order_item_id = 1",
     "order_items: quantity > 0"),
    ("update raw.order_items set discount_pct = 1.5 where order_item_id = 1",
     "order_items: discount_pct in [0, 1)"),
    ("update raw.returns set order_item_id = 555 where return_id = 1",
     "returns.order_item_id references order_items.order_item_id"),
    ("insert into raw.fx_rates values (date '2024-01-01', 'GBP', 1.3)",
     "fx_rates.month+currency unique"),
    ("delete from raw.fx_rates where currency = 'GBP' and month = date '2024-02-01'",
     "orders.currency+month references fx_rates.currency+month"),
    ("update raw.orders set order_date = date '2024-04-02' where order_id = 6",  # no FX month
     "orders.currency+month references fx_rates.currency+month"),
]  # fmt: skip


def failing(results):
    return {r.check.name for r in results if not r.passed}


def test_clean_fixture_passes_all_checks(raw_con):
    results = quality.run_checks(raw_con)
    assert len(results) >= 25
    assert failing(results) == set()
    quality.assert_ok(results)


@pytest.mark.parametrize(("corrupt_sql", "expected"), BAD_DATA, ids=[b[1] for b in BAD_DATA])
def test_check_catches_bad_data(raw_con, corrupt_sql, expected):
    raw_con.execute(corrupt_sql)
    assert expected in failing(quality.run_checks(raw_con))


def test_failure_is_loud_and_readable(raw_con):
    raw_con.execute("update raw.orders set customer_id = 99 where order_id = 1")
    with pytest.raises(DataQualityError) as err:
        quality.assert_ok(quality.run_checks(raw_con))
    msg = str(err.value)
    assert "FAIL  orders.customer_id references customers.customer_id" in msg
    assert "1 failing rows" in msg
    assert "99" in msg  # sample of the offending row is shown
    assert msg.startswith("1 of ") and "PASS" not in msg  # only the failure, not the full report


def test_every_check_kind_is_exercised():
    kinds = {c.kind for c in quality.default_checks()}
    assert kinds == {"not_null", "unique", "relationship", "accepted_values", "expression"}
