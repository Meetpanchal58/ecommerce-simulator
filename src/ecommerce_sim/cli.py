"""Command line: ecommerce-sim load | increment | derive | validate."""
import argparse
import sys
from datetime import date

import pandas as pd

from . import settings as settings_module


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="ecommerce-sim", description="Simulate an e-commerce shop day by day.")
    parser.add_argument("command", choices=["download", "load", "increment", "derive", "validate", "textsql", "docs"],
                        help="download: get the latest ready-made data (updated daily); load: simulate fresh from the start date "
                             "to today; increment: add days up to today; "
                             "derive: build analysis tables (churn, affinity, ...); validate: check the data; "
                             "textsql: Text-to-SQL knowledge base and questions; docs: write docs/schema.md")
    parser.add_argument("--data-dir", help="where to write the data (default: ./data)")
    parser.add_argument("--size", choices=["small", "medium", "full", "large"],
                        help="shop size preset (default: full): small ~4 min, medium ~10 min, full ~18 min, large ~75 min to simulate")
    parser.add_argument("--from", "--start-date", dest="start_date",
                        help="first day of data = the day the shop opens, YYYY-MM-DD (default: 2025-01-01)")
    parser.add_argument("--to", "--today", dest="today", help="last day of data, YYYY-MM-DD (default: today)")
    parser.add_argument("--months", type=int,
                        help="load only the last N months up to --to (sets --from); e.g. --months 6")
    parser.add_argument("--seed", help="random seed (default: 42)")
    parser.add_argument("--products", help="number of product styles (default: 10000)")
    parser.add_argument("--traffic-scale", help="marketing budgets and clicks vs the full shop (full = 1.0)")
    args = parser.parse_args(argv)
    if args.months:
        if args.start_date:
            parser.error("use either --from or --months, not both")
        end = pd.Timestamp(args.today or date.today().isoformat())
        args.start_date = f"{(end - pd.DateOffset(months=args.months)).replace(day=1):%Y-%m-%d}"
    if args.command == "increment" and args.start_date:
        parser.error("--from / --months only apply to load (increment continues the existing data)")
    settings = settings_module.from_environment(
        size=args.size, data_dir=args.data_dir, today=args.today, start_date=args.start_date, seed=args.seed,
        n_products=args.products, traffic_scale=args.traffic_scale)

    if args.command == "download":
        from .download import download
        download(settings.data_dir, args.size or "full")
        return 0
    if args.command in ("load", "increment"):
        from .simulate import run
        run(settings, args.command)
        from .validate import validate
        return 0 if validate(settings.data_dir) else 1
    if args.command == "derive":
        from .derive import derive_all
        derive_all(settings.data_dir)
        return 0
    if args.command == "textsql":
        from .textsql import build
        build(settings.data_dir)
        return 0
    if args.command == "docs":
        from .schema import markdown
        from .store import Store
        store = Store(settings.data_dir)
        from .schema import TABLES
        types = {name: {col: str(dtype) for col, dtype in store.read(name).dtypes.items()} for name in TABLES}
        from pathlib import Path
        Path("docs").mkdir(exist_ok=True)
        Path("docs/schema.md").write_text(markdown(types))
        print("Wrote docs/schema.md")
        return 0
    from .validate import validate
    return 0 if validate(settings.data_dir) else 1


if __name__ == "__main__":
    sys.exit(main())
