"""Tiny dbt-style SQL model runner: {{ ref('model') }} / {{ source('table') }}, topological order."""

import re
import time
from dataclasses import dataclass
from graphlib import TopologicalSorter
from pathlib import Path

import duckdb

from . import quality
from .config import Settings
from .constants import TABLES
from .generator import generate

LAYERS = ["staging", "intermediate", "marts"]
REF = re.compile(r"\{\{\s*ref\('(\w+)'\)\s*\}\}")
SOURCE = re.compile(r"\{\{\s*source\('(\w+)'\)\s*\}\}")


@dataclass(frozen=True)
class Model:
    name: str
    layer: str
    sql: str
    refs: tuple[str, ...]
    sources: tuple[str, ...]


def load_models(sql_dir: Path) -> list[Model]:
    """Parse every sql/<layer>/<name>.sql and return the models in dependency order."""
    models = {}
    for layer in LAYERS:
        for path in sorted((Path(sql_dir) / layer).glob("*.sql")):
            text = path.read_text(encoding="utf-8")
            models[path.stem] = Model(
                path.stem,
                layer,
                text,
                tuple(dict.fromkeys(REF.findall(text))),
                tuple(SOURCE.findall(text)),
            )
    if not models:  # e.g. a non-editable install: sql/ is not packaged
        raise FileNotFoundError(f"No SQL models under {sql_dir}")
    missing = {r for m in models.values() for r in m.refs} - models.keys()
    if missing:
        raise ValueError(f"Unknown ref(): {sorted(missing)}")
    order = TopologicalSorter({n: m.refs for n, m in models.items()}).static_order()
    return [models[n] for n in order]


def render(model: Model, models: dict[str, Model]) -> str:
    sql = REF.sub(lambda m: f"{models[m.group(1)].layer}.{m.group(1)}", model.sql)
    return SOURCE.sub(lambda m: f"raw.{m.group(1)}", sql)


def run_models(con: duckdb.DuckDBPyConnection, sql_dir: Path, log=lambda _: None) -> list[Model]:
    ordered = load_models(sql_dir)
    by_name = {m.name: m for m in ordered}
    for layer in LAYERS:
        con.execute(f"create schema if not exists {layer}")
    for m in ordered:
        t0 = time.perf_counter()
        con.execute(f"create or replace table {m.layer}.{m.name} as\n{render(m, by_name)}")
        n = con.execute(f"select count(*) from {m.layer}.{m.name}").fetchone()[0]
        log(f"  {m.layer}.{m.name:<28} {n:>8,} rows  {time.perf_counter() - t0:.2f}s")
    return ordered


def extract(con: duckdb.DuckDBPyConnection, data_dir: Path, fmt: str, log=lambda _: None) -> None:
    con.execute("create schema if not exists raw")
    reader = "read_csv" if fmt == "csv" else "read_parquet"
    for table in TABLES:
        path = Path(data_dir) / f"{table}.{fmt}"
        con.execute(
            f"create or replace table raw.{table} as select * from {reader}(?)", [str(path)]
        )
        n = con.execute(f"select count(*) from raw.{table}").fetchone()[0]
        log(f"  raw.{table:<12} {n:>8,} rows")


def lineage_mermaid(sql_dir: Path) -> str:
    lines = ["graph LR"]
    for m in load_models(sql_dir):
        lines += [f"  raw_{s}[(raw.{s})] --> {m.name}" for s in m.sources]
        lines += [f"  {r} --> {m.name}" for r in m.refs]
    return "\n".join(lines)


def run_pipeline(settings: Settings, force_generate: bool = False, log=print):
    """generate (if needed) -> extract -> data quality gate -> transform."""
    s = settings
    ext = s.file_format
    if force_generate or not all((s.data_dir / f"{t}.{ext}").exists() for t in TABLES):
        log(f"[1/4] Generating synthetic data (~{s.order_lines:,} order lines, seed {s.seed})")
        generate(s.data_dir, s.order_lines, s.seed, ext)
    else:
        log(f"[1/4] Reusing raw files in {s.data_dir}")
    s.db_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(s.db_path)) as con:
        log("[2/4] Extract -> DuckDB raw schema")
        extract(con, s.data_dir, ext, log)
        log("[3/4] Data quality checks")
        results = quality.run_checks(con)
        con.execute("create schema if not exists ops")
        dq_df = quality.to_frame(results)  # noqa: F841 (read by DuckDB replacement scan)
        con.execute("create or replace table ops.dq_results as select * from dq_df")
        log(quality.format_report(results))
        quality.assert_ok(results)  # fail loudly, before anything is transformed
        log("[4/4] Transform (staging -> intermediate -> marts)")
        run_models(con, s.sql_dir, log)
    return results
