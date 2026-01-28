from stockcheck.reporter.runner import run


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Daily stock summary sender.")
    parser.add_argument("--market", required=True, choices=["tw", "us"], help="Market key")
    parser.add_argument(
        "--config",
        default="config/subscriptions.json",
        help="Path to subscriptions JSON",
    )

    args = parser.parse_args()
    run(args.market, args.config)
