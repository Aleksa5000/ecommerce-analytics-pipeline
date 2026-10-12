import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseModel):
    """Pipeline configuration. Override via PIPELINE_* environment variables."""

    seed: int = 42
    order_lines: int = Field(50_000, ge=500, description="Approximate number of order lines")
    file_format: Literal["csv", "parquet"] = "csv"
    data_dir: Path = ROOT / "data" / "raw"
    db_path: Path = ROOT / "data" / "warehouse.duckdb"
    sql_dir: Path = ROOT / "sql"

    @classmethod
    def from_env(cls) -> "Settings":
        env = {
            "seed": os.getenv("PIPELINE_SEED"),
            "order_lines": os.getenv("PIPELINE_ORDER_LINES"),
            "file_format": os.getenv("PIPELINE_FORMAT"),
            "data_dir": os.getenv("PIPELINE_DATA_DIR"),
            "db_path": os.getenv("PIPELINE_DB_PATH"),
        }
        return cls(**{k: v for k, v in env.items() if v})
