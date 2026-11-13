"""Command line: ecommerce-sim load | increment | derive | validate."""
import argparse
import sys

from . import settings as settings_module


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="ecommerce-sim", description="Simulate an e-commerce shop day by day.")
    parser.add_argument("command", choices=["load", "increment", "derive", "validate"],
                        help="load: start fresh from the start date to today; increment: add days up to today; "
                             "derive: build analysis tables (churn, affinity, ...); validate: check the data")
    parser.add_argument("--data-dir", help="where to write the data (default: ./data)")
    parser.add_argument("--today", help="last day to simulate, YYYY-MM-DD (default: today)")
    parser.add_argument("--start-date", help="day the shop opens (default: 2025-01-01)")
    parser.add_argument("--seed", help="random seed (default: 42)")
    parser.add_argument("--products", help="number of product styles (default: 10000)")
    parser.add_argument("--launch-customers", help="customers signing up in the opening weeks (default: 9000)")
    args = parser.parse_args(argv)
    settings = settings_module.from_environment(
        data_dir=args.data_dir, today=args.today, start_date=args.start_date, seed=args.seed,
        n_products=args.products, launch_customers=args.launch_customers)

    if args.command in ("load", "increment"):
        from .simulate import run
        run(settings, args.command)
        from .validate import validate
        return 0 if validate(settings.data_dir) else 1
    if args.command == "derive":
        from .derive import derive_all
        derive_all(settings.data_dir)
        return 0
    from .validate import validate
    return 0 if validate(settings.data_dir) else 1


if __name__ == "__main__":
    sys.exit(main())
