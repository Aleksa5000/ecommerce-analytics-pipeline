"""Deterministic synthetic e-commerce data generator.

Same (seed, order_lines) always yields byte-identical files. Everything is drawn from a single
numpy Generator in a fixed order.
"""

from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

from .constants import CATEGORIES, CHANNELS, COUNTRY_CURRENCY, TABLES

START = pd.Timestamp("2023-01-01")
END = pd.Timestamp("2025-12-31")

# Black-Friday / Christmas peak, summer dip.
SEASON = {1: .85, 2: .8, 3: .9, 4: .95, 5: 1.0, 6: .95, 7: .9, 8: .9, 9: 1.0, 10: 1.1,
          11: 1.6, 12: 1.4}  # fmt: skip
COUNTRY_WEIGHTS = {
    "DE": 0.26,
    "US": 0.20,
    "FR": 0.18,
    "GB": 0.18,
    "ES": 0.08,
    "PL": 0.06,
    "SE": 0.04,
}
BASE_FX = {"EUR": 1.0, "GBP": 1.17, "USD": 0.92, "PLN": 0.23, "SEK": 0.088}  # EUR per 1 unit
CATEGORY_PRICE_EUR = {"Apparel": 45, "Electronics": 220, "Home": 60, "Beauty": 25, "Sports": 55,
                      "Books": 18}  # fmt: skip
CATEGORY_RETURN_RATE = {"Apparel": .18, "Electronics": .07, "Home": .05, "Beauty": .04,
                        "Sports": .09, "Books": .02}  # fmt: skip
NOUNS = {
    "Apparel": ["T-Shirt", "Hoodie", "Jeans", "Jacket", "Sneakers", "Dress"],
    "Electronics": ["Headphones", "Speaker", "Smartwatch", "Charger", "Webcam", "Tablet"],
    "Home": ["Lamp", "Cushion", "Vase", "Blanket", "Mug Set", "Shelf"],
    "Beauty": ["Serum", "Moisturizer", "Perfume", "Lip Balm", "Shampoo", "Face Mask"],
    "Sports": ["Yoga Mat", "Dumbbells", "Water Bottle", "Running Belt", "Backpack", "Jump Rope"],
    "Books": ["Novel", "Cookbook", "Biography", "Atlas", "Thriller", "Guide"],
}
ADJECTIVES = ["Classic", "Urban", "Essential", "Premium", "Active", "Heritage"]
PRODUCTS_PER_CATEGORY = 20
RETURN_REASONS = ["wrong_size", "defective", "not_as_described", "changed_mind"]


def _season_array(dates: pd.DatetimeIndex) -> np.ndarray:
    return np.array([SEASON[m] for m in dates.month])


def _fx_rates(rng: np.random.Generator) -> pd.DataFrame:
    months = pd.date_range(START, END, freq="MS")
    frames = []
    for cur, base in BASE_FX.items():
        walk = np.cumsum(rng.normal(0, 0.012, len(months)))
        rate = base * np.exp(walk) if cur != "EUR" else np.ones(len(months))
        frames.append(pd.DataFrame({"month": months, "currency": cur,
                                    "eur_per_unit": rate.round(5)}))  # fmt: skip
    return pd.concat(frames, ignore_index=True)


def _products(rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    for cat in CATEGORIES:
        combos = list(product(ADJECTIVES, NOUNS[cat]))
        picks = rng.permutation(len(combos))[:PRODUCTS_PER_CATEGORY]
        prices = rng.lognormal(np.log(CATEGORY_PRICE_EUR[cat]), 0.45, PRODUCTS_PER_CATEGORY)
        for i, p in zip(picks, prices, strict=True):
            adj, noun = combos[i]
            rows.append((f"{adj} {noun}", cat, max(round(p) - 0.01, 1.99)))
    df = pd.DataFrame(rows, columns=["product_name", "category", "list_price_eur"])
    df.insert(0, "product_id", np.arange(1, len(df) + 1))
    return df


def _customers(rng: np.random.Generator, n: int) -> pd.DataFrame:
    days = pd.date_range(START, END)
    trend = 1 + 0.8 * np.linspace(0, 1, len(days))
    w = trend * _season_array(days) * np.where(days.dayofweek >= 5, 1.15, 1.0)
    signup = days[rng.choice(len(days), n, p=w / w.sum())]
    countries = rng.choice(list(COUNTRY_WEIGHTS), n, p=list(COUNTRY_WEIGHTS.values()))
    return pd.DataFrame({
        "customer_id": np.arange(1, n + 1),
        "email": [f"customer{i}@example.com" for i in range(1, n + 1)],
        "country": countries,
        "signup_date": signup,
        "acquisition_channel": rng.choice(CHANNELS, n, p=[.3, .25, .2, .15, .1]),
    })  # fmt: skip


def _orders(rng: np.random.Generator, customers: pd.DataFrame) -> pd.DataFrame:
    n = len(customers)
    k = rng.geometric(0.55, n)  # attempted orders per customer (mean ~1.8)
    cid = np.repeat(np.arange(n), k)
    start_idx = np.cumsum(k) - k
    first = np.zeros(len(cid), dtype=bool)
    first[start_idx] = True
    gaps = np.where(first, rng.integers(0, 15, len(cid)), 7 + rng.exponential(70, len(cid)))
    cs = np.cumsum(gaps)
    offset = np.repeat(cs[start_idx] - gaps[start_idx], k)
    dates = customers["signup_date"].to_numpy()[cid] + pd.to_timedelta(np.floor(cs - offset), "D")
    dates = pd.DatetimeIndex(dates)
    season = _season_array(dates)
    # Repeat purchases are thinned outside the peak season; first orders are kept.
    keep = (dates <= END) & (
        first | (rng.random(len(cid)) < 0.5 + 0.5 * season / max(SEASON.values()))
    )
    df = pd.DataFrame({"customer_id": customers["customer_id"].to_numpy()[cid][keep],
                       "order_date": dates[keep]})  # fmt: skip
    df = df.sort_values(["order_date", "customer_id"], kind="stable", ignore_index=True)
    df.insert(0, "order_id", np.arange(1, len(df) + 1))
    country = customers.set_index("customer_id")["country"].reindex(df["customer_id"]).to_numpy()
    df["currency"] = [COUNTRY_CURRENCY[c] for c in country]
    df["status"] = np.where(rng.random(len(df)) < 0.03, "cancelled", "completed")
    return df


def _order_items(rng, orders, products, fx) -> tuple[pd.DataFrame, pd.DataFrame]:
    n_items = rng.choice([1, 2, 3, 4, 5], len(orders), p=[0.45, 0.28, 0.14, 0.08, 0.05])
    idx = np.repeat(np.arange(len(orders)), n_items)
    m = len(idx)
    popularity = rng.pareto(1.6, len(products)) + 1
    pid = rng.choice(products["product_id"].to_numpy(), m, p=popularity / popularity.sum())
    dates = orders["order_date"].to_numpy()[idx]
    month = pd.DatetimeIndex(dates).to_period("M").to_timestamp()
    black_friday = np.asarray(month.month == 11)
    disc = np.where(
        black_friday,
        rng.choice([0, 0.1, 0.2, 0.3], m, p=[0.35, 0.2, 0.25, 0.2]),
        rng.choice([0, 0.1, 0.2, 0.3], m, p=[0.7, 0.15, 0.1, 0.05]),
    )
    qty = rng.choice([1, 2, 3], m, p=[0.8, 0.15, 0.05])
    key = pd.MultiIndex.from_arrays([month, orders["currency"].to_numpy()[idx]])
    rate = fx.set_index(["month", "currency"])["eur_per_unit"].reindex(key).to_numpy()
    price_eur = products.set_index("product_id")["list_price_eur"].reindex(pid).to_numpy()
    items = pd.DataFrame({
        "order_item_id": np.arange(1, m + 1),
        "order_id": orders["order_id"].to_numpy()[idx],
        "product_id": pid,
        "quantity": qty,
        "unit_price": (price_eur / rate).round(2),
        "discount_pct": disc,
    })  # fmt: skip
    cat = products.set_index("product_id")["category"].reindex(pid).to_numpy()
    p_ret = np.array([CATEGORY_RETURN_RATE[c] for c in cat])
    completed = (orders["status"].to_numpy() == "completed")[idx]
    ret = (rng.random(m) < p_ret) & completed
    returns = pd.DataFrame({
        "order_item_id": items["order_item_id"].to_numpy()[ret],
        "return_date": pd.DatetimeIndex(dates[ret]) + pd.to_timedelta(rng.integers(5, 31, ret.sum()), "D"),
        "reason": rng.choice(RETURN_REASONS, ret.sum()),
    })  # fmt: skip
    returns.insert(0, "return_id", np.arange(1, len(returns) + 1))
    return items, returns


def generate_frames(order_lines: int = 50_000, seed: int = 42) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    fx = _fx_rates(rng)
    products = _products(rng)
    # ~2.0 lines/order, ~1.5 surviving orders/customer after date truncation and thinning
    customers = _customers(rng, max(int(order_lines / 3.05), 10))
    orders = _orders(rng, customers)
    items, returns = _order_items(rng, orders, products, fx)
    frames = {"customers": customers, "products": products, "orders": orders,
              "order_items": items, "returns": returns, "fx_rates": fx}  # fmt: skip
    for df in frames.values():  # plain dates (no time component) in the files
        for col in df.columns[df.dtypes.astype(str).str.startswith("datetime")]:
            df[col] = df[col].dt.date
    return frames


def generate(out_dir: Path, order_lines: int = 50_000, seed: int = 42, fmt: str = "csv") -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = generate_frames(order_lines, seed)
    for name in TABLES:
        path = out_dir / f"{name}.{fmt}"
        if fmt == "csv":
            frames[name].to_csv(path, index=False, lineterminator="\n")
        else:
            frames[name].to_parquet(path, index=False)
    return {name: len(df) for name, df in frames.items()}
