"""Smoke test: the Streamlit app runs (its first run builds a small warehouse of its own)."""

import re

from streamlit.testing.v1 import AppTest

from pipeline.config import ROOT


def test_dashboard_renders(tmp_path, monkeypatch):
    monkeypatch.setenv("PIPELINE_DATA_DIR", str(tmp_path / "raw"))
    monkeypatch.setenv("PIPELINE_DB_PATH", str(tmp_path / "wh.duckdb"))
    monkeypatch.setenv("PIPELINE_ORDER_LINES", "3000")
    at = AppTest.from_file(str(ROOT / "dashboard" / "app.py"), default_timeout=300).run()
    assert not at.exception
    assert [m.label for m in at.metric][0] == "Net revenue" and len(at.metric) == 5
    # ~3k lines is well under EUR 1M, so the card shows the full amount, not "EUR 0.xxM"
    assert re.fullmatch(r"EUR [1-9][\d,]*", at.metric[0].value)
