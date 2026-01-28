import os
from pathlib import Path

from .reporter.runner import run


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Daily stock summary sender.")
    parser.add_argument("--market", required=True, choices=["tw", "us"], help="Market key")
    root = Path(__file__).resolve().parents[2]
    parser.add_argument(
        "--config",
        default=str(root / "config" / "subscriptions.json"),
        help="Path to subscriptions JSON",
    )

    args = parser.parse_args()
    run(args.market, os.path.abspath(args.config))


if __name__ == "__main__":
    main()
