import argparse
from pathlib import Path

from .config import ROOT, Settings
from .quality import DataQualityError
from .runner import lineage_mermaid, run_pipeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m pipeline", description="E-commerce analytics pipeline"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="generate (if needed), extract, check, transform")
    run.add_argument("--regenerate", action="store_true", help="regenerate raw files")
    rep = sub.add_parser("report", help="export the self-contained HTML report")
    rep.add_argument("--out", type=Path, default=ROOT / "docs" / "report.html")
    sub.add_parser("lineage", help="print the model lineage as a mermaid graph")
    args = parser.parse_args(argv)
    settings = Settings.from_env()

    if args.cmd == "lineage":
        print(lineage_mermaid(settings.sql_dir))
        return 0
    try:
        if args.cmd == "run":
            run_pipeline(settings, force_generate=args.regenerate)
            print(f"\nDone. Warehouse: {settings.db_path}")
        else:
            from .report import build_report

            if not settings.db_path.exists():
                run_pipeline(settings)
            print(f"Report written to {build_report(settings.db_path, args.out)}")
    except DataQualityError as exc:
        print(f"\nPIPELINE ABORTED - data quality checks failed\n{exc}")
        return 2
    return 0
