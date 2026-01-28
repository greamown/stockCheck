from stockcheck.pipeline.runner import run_pipeline


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Daily market data pipeline runner.")
    parser.add_argument("--market", required=True, choices=["tw", "us"], help="Market key")
    parser.add_argument("--days", type=int, default=220, help="Lookback window for indicators")
    parser.add_argument(
        "--config",
        default="config/subscriptions.json",
        help="Path to subscriptions JSON",
    )
    parser.add_argument(
        "--metadata",
        default="config/symbol_metadata.json",
        help="Path to symbol metadata JSON",
    )
    parser.add_argument("--verbose", action="store_true", help="Print detailed pipeline logs")
    parser.add_argument("--summary-json", action="store_true", help="Emit summary as JSON only")

    args = parser.parse_args()
    run_pipeline(args.market, args.config, args.metadata, args.days, args.verbose, args.summary_json)
