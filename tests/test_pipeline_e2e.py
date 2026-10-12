import duckdb
import pytest

from pipeline.cli import main
from pipeline.config import Settings
from pipeline.quality import DataQualityError
from pipeline.report import build_report
from pipeline.runner import run_pipeline


@pytest.fixture
def settings(tmp_path):
    return Settings(
        order_lines=3000, data_dir=tmp_path / "raw", db_path=tmp_path / "wh.duckdb", seed=11
    )


def test_end_to_end_and_report(settings, tmp_path):
    results = run_pipeline(settings, log=lambda _: None)
    assert all(r.passed for r in results)
    with duckdb.connect(str(settings.db_path), read_only=True) as con:
        fct, daily = con.execute(
            "select (select sum(net_eur) from marts.fct_order_lines),"
            "(select sum(net_eur) from marts.mart_daily_revenue)"
        ).fetchone()
        assert fct == pytest.approx(daily) and fct > 0
        raw_lines, fct_lines = con.execute(
            "select (select count(*) from raw.order_items join raw.orders using (order_id)"
            " where status = 'completed'), (select count(*) from marts.fct_order_lines)"
        ).fetchone()
        assert raw_lines == fct_lines  # no completed line is lost in a join
        assert con.execute("select count(*) from ops.dq_results").fetchone()[0] >= 25
    out = build_report(settings.db_path, tmp_path / "report.html")
    html = out.read_text(encoding="utf-8")
    assert "Cohort retention" in html
    assert "<script src" not in html and "<link" not in html  # self-contained


def test_corrupt_raw_data_aborts_before_transform(settings, monkeypatch, capsys):
    run_pipeline(settings, log=lambda _: None)
    orders = settings.data_dir / "orders.csv"
    lines = orders.read_text().splitlines()
    first = lines[1].split(",")
    first[1] = "99999999"  # customer that does not exist
    orders.write_text("\n".join([lines[0], ",".join(first), *lines[2:]]) + "\n")
    with pytest.raises(DataQualityError, match="orders.customer_id references"):
        run_pipeline(settings, log=lambda _: None)
    for k, v in {"PIPELINE_DATA_DIR": settings.data_dir, "PIPELINE_DB_PATH": settings.db_path,
                 "PIPELINE_ORDER_LINES": 3000}.items():  # fmt: skip
        monkeypatch.setenv(k, str(v))
    assert main(["run"]) == 2  # CLI exits non-zero with the report
    assert "PIPELINE ABORTED" in capsys.readouterr().out
