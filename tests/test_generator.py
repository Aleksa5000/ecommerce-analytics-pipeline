import hashlib

import pandas as pd

from pipeline.constants import TABLES
from pipeline.generator import generate, generate_frames


def _hashes(path):
    return {t: hashlib.sha256((path / f"{t}.csv").read_bytes()).hexdigest() for t in TABLES}


def test_same_seed_is_byte_identical(tmp_path):
    generate(tmp_path / "a", 2000, seed=7)
    generate(tmp_path / "b", 2000, seed=7)
    assert _hashes(tmp_path / "a") == _hashes(tmp_path / "b")


def test_different_seed_differs(tmp_path):
    generate(tmp_path / "a", 2000, seed=7)
    generate(tmp_path / "b", 2000, seed=8)
    assert _hashes(tmp_path / "a")["orders"] != _hashes(tmp_path / "b")["orders"]


def test_size_and_shape():
    f = generate_frames(5000, seed=1)
    assert 0.85 * 5000 <= len(f["order_items"]) <= 1.15 * 5000
    assert f["customers"]["country"].nunique() == 7
    assert set(f["orders"]["status"]) == {"completed", "cancelled"}
    assert 0.03 < len(f["returns"]) / len(f["order_items"]) < 0.12


def test_november_is_peak_season():
    orders = generate_frames(20000, seed=3)["orders"]
    by_month = pd.to_datetime(orders["order_date"]).dt.month.value_counts()
    assert by_month[11] > by_month[[2, 7, 8]].mean() * 1.3


def test_parquet_roundtrip(tmp_path):
    generate(tmp_path, 1000, seed=5, fmt="parquet")
    assert len(pd.read_parquet(tmp_path / "orders.parquet")) > 0
