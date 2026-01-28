import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from . import db, indicators, sources
from .utils import load_json, safe_call


def _get_worker_count(target: int) -> int:
    env_value = int(os.getenv("PIPELINE_MAX_WORKERS", "4") or 4)
    return max(1, min(env_value, target))


def run_pipeline(
    market: str,
    subscription_path: str,
    metadata_path: str,
    days: int,
    verbose: bool = False,
    summary_json: bool = False,
) -> None:
    load_dotenv()
    subscriptions = load_json(subscription_path)
    metadata = load_json(metadata_path)
    watchlist = subscriptions.get(market, [])
    if not watchlist:
        raise ValueError(f"No subscriptions for market '{market}'")

    end_date = datetime.utcnow().date()
    start_date = end_date - timedelta(days=days)
    finmind_token = os.getenv("FINMIND_API_KEY", "")
    totals = {"prices": 0, "indicators": 0, "news": 0, "sentiment": 0, "financials": 0, "symbols": 0}
    totals_by_source = {"prices": {}, "news": {}, "sentiment": {}}
    per_symbol: List[Dict[str, Any]] = []

    def format_sources(label: str, counts: Dict[str, int]) -> str:
        if not counts:
            return f"{label}=0"
        parts = ",".join(f"{key}:{counts[key]}" for key in sorted(counts))
        return f"{label}={parts}"

    def log(level: str, message: str, force: bool = False) -> None:
        if summary_json:
            return
        if not verbose and not force:
            return
        timestamp = datetime.utcnow().isoformat() + "Z"
        print(f"{timestamp} [{level}] {message}")

    db_path = db.get_pipeline_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    init_conn = db.connect(db_path)
    try:
        db.init_pipeline_db(init_conn)
    finally:
        init_conn.close()

    def process_symbol(symbol: str) -> Optional[Dict[str, Any]]:
        log("INFO", f"Pipeline start: market={market} symbol={symbol}", force=True)
        symbol_totals = {
            "symbol": symbol,
            "prices": 0,
            "indicators": 0,
            "news": 0,
            "sentiment": 0,
            "financials": 0,
            "prices_by_source": {},
            "news_by_source": {},
            "sentiment_by_source": {},
        }
        if market == "us":
            price_rows = safe_call(
                f"Price fetch stooq {symbol}",
                lambda: sources.filter_by_date(sources.fetch_stooq_daily(symbol), start_date, end_date),
                [],
                log,
            )
            log("INFO", f"stooq prices: {len(price_rows)}")
            if not price_rows:
                price_rows = safe_call(
                    f"Price fetch yfinance {symbol}",
                    lambda: sources.fetch_yfinance_daily(symbol, start_date, end_date),
                    [],
                    log,
                )
                log("INFO", f"yfinance prices: {len(price_rows)}")
        else:
            finmind_id = sources.get_finmind_id(symbol, metadata)
            price_rows = safe_call(
                f"Price fetch finmind {symbol}",
                lambda: sources.fetch_finmind_daily(finmind_id, start_date, end_date, finmind_token),
                [],
                log,
            )
            log("INFO", f"finmind prices: {len(price_rows)}")
            if not price_rows:
                price_rows = safe_call(
                    f"Price fetch yfinance {symbol}",
                    lambda: sources.fetch_yfinance_daily(symbol, start_date, end_date),
                    [],
                    log,
                )
                log("INFO", f"yfinance prices: {len(price_rows)}")
        if not price_rows:
            log("WARN", f"No prices for {symbol}", force=True)
            return None

        conn = db.connect(db_path)
        try:
            db.save_prices(conn, market, symbol, price_rows)
            indicator_rows = indicators.compute_indicators(price_rows)
            db.save_indicators(conn, market, symbol, indicator_rows)

            symbol_totals["prices"] += len(price_rows)
            symbol_totals["indicators"] += len(indicator_rows)
            log("INFO", f"indicators: {len(indicator_rows)}")
            for row in price_rows:
                source = row.source or "unknown"
                symbol_totals["prices_by_source"][source] = symbol_totals["prices_by_source"].get(source, 0) + 1

            query = sources.get_symbol_query(symbol, metadata, market)
            news_items = safe_call(
                f"News fetch google {symbol}",
                lambda: sources.fetch_google_news(query, market),
                [],
                log,
            )
            for item in news_items:
                item["source"] = "google_news"
            db.save_news(conn, market, symbol, news_items[:10])
            symbol_totals["news"] += len(news_items[:10])
            log("INFO", f"news items: {len(news_items[:10])}")
            for item in news_items[:10]:
                source = item.get("source") or "unknown"
                symbol_totals["news_by_source"][source] = symbol_totals["news_by_source"].get(source, 0) + 1

            def extract_period_end(payload: Any) -> str:
                if not isinstance(payload, dict):
                    return ""
                dates: List[str] = []
                data_items = payload.get("data")
                if isinstance(data_items, list):
                    for item in data_items:
                        if not isinstance(item, dict):
                            continue
                        for key in ("date", "end_date", "period_end", "report_date"):
                            value = item.get(key)
                            if value:
                                dates.append(str(value))
                facts = payload.get("facts")
                if isinstance(facts, dict):
                    for namespace in facts.values():
                        if not isinstance(namespace, dict):
                            continue
                        for metric in namespace.values():
                            units = metric.get("units", {})
                            if not isinstance(units, dict):
                                continue
                            for entries in units.values():
                                if not isinstance(entries, list):
                                    continue
                                for entry in entries:
                                    if not isinstance(entry, dict):
                                        continue
                                    end_value = entry.get("end")
                                    if end_value:
                                        dates.append(str(end_value))
                return max(dates) if dates else ""

            if market == "us":
                cik = sources.get_symbol_cik(symbol, metadata)
                if cik:
                    payload = safe_call(
                        f"Financials fetch sec {symbol}",
                        lambda: sources.fetch_sec_companyfacts(cik),
                        {},
                        log,
                    )
                    period_end = extract_period_end(payload)
                    db.save_financials(
                        conn,
                        market,
                        symbol,
                        period_end,
                        "companyfacts",
                        payload,
                        "sec_edgar",
                    )
                    if payload:
                        symbol_totals["financials"] += 1
                sentiment_items = safe_call(
                    f"Sentiment fetch reddit {symbol}",
                    lambda: sources.fetch_reddit_search(query),
                    [],
                    log,
                )
                for item in sentiment_items:
                    item["source"] = "reddit"
                if not sentiment_items:
                    sentiment_items = safe_call(
                        f"Sentiment fetch stocktwits {symbol}",
                        lambda: sources.fetch_stocktwits(symbol),
                        [],
                        log,
                    )
                    for item in sentiment_items:
                        item["source"] = "stocktwits"
                db.save_sentiment(conn, market, symbol, sentiment_items[:10])
                symbol_totals["sentiment"] += len(sentiment_items[:10])
                log("INFO", f"sentiment items: {len(sentiment_items[:10])}")
                for item in sentiment_items[:10]:
                    source = item.get("source") or "unknown"
                    symbol_totals["sentiment_by_source"][source] = (
                        symbol_totals["sentiment_by_source"].get(source, 0) + 1
                    )
            else:
                if finmind_token:
                    payload = safe_call(
                        f"Financials fetch finmind {symbol}",
                        lambda: sources.fetch_finmind_financials(symbol, start_date, end_date, finmind_token),
                        {},
                        log,
                    )
                    period_end = extract_period_end(payload)
                    db.save_financials(
                        conn,
                        market,
                        symbol,
                        period_end,
                        "financial_statements",
                        payload,
                        "finmind",
                    )
                    if payload:
                        symbol_totals["financials"] += 1
                sentiment_items = safe_call(
                    f"Sentiment fetch ptt {symbol}",
                    lambda: sources.fetch_ptt_search(sources.strip_tw_symbol(symbol)),
                    [],
                    log,
                )
                for item in sentiment_items:
                    item["source"] = "ptt"
                db.save_sentiment(conn, market, symbol, sentiment_items[:10])
                symbol_totals["sentiment"] += len(sentiment_items[:10])
                log("INFO", f"sentiment items: {len(sentiment_items[:10])}")
                for item in sentiment_items[:10]:
                    source = item.get("source") or "unknown"
                    symbol_totals["sentiment_by_source"][source] = (
                        symbol_totals["sentiment_by_source"].get(source, 0) + 1
                    )

            if not summary_json:
                log(
                    "INFO",
                    "Symbol summary:"
                    f" symbol={symbol_totals['symbol']}"
                    f" prices={symbol_totals['prices']}"
                    f" indicators={symbol_totals['indicators']}"
                    f" news={symbol_totals['news']}"
                    f" sentiment={symbol_totals['sentiment']}"
                    f" financials={symbol_totals['financials']}"
                    f" {format_sources('prices_by_source', symbol_totals['prices_by_source'])}"
                    f" {format_sources('news_by_source', symbol_totals['news_by_source'])}"
                    f" {format_sources('sentiment_by_source', symbol_totals['sentiment_by_source'])}",
                    force=True,
                )
            return symbol_totals
        finally:
            conn.close()

    totals["symbols"] = len(watchlist)
    results: List[Dict[str, Any]] = []
    worker_count = _get_worker_count(len(watchlist))
    if worker_count == 1:
        for symbol in watchlist:
            result = process_symbol(symbol)
            if result:
                results.append(result)
    else:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {executor.submit(process_symbol, symbol): symbol for symbol in watchlist}
            for future in as_completed(futures):
                result = future.result()
                if result:
                    results.append(result)

    for symbol_totals in results:
        per_symbol.append(symbol_totals)
        totals["prices"] += symbol_totals["prices"]
        totals["indicators"] += symbol_totals["indicators"]
        totals["news"] += symbol_totals["news"]
        totals["sentiment"] += symbol_totals["sentiment"]
        totals["financials"] += symbol_totals["financials"]
        for source, count in symbol_totals["prices_by_source"].items():
            totals_by_source["prices"][source] = totals_by_source["prices"].get(source, 0) + count
        for source, count in symbol_totals["news_by_source"].items():
            totals_by_source["news"][source] = totals_by_source["news"].get(source, 0) + count
        for source, count in symbol_totals["sentiment_by_source"].items():
            totals_by_source["sentiment"][source] = totals_by_source["sentiment"].get(source, 0) + count

    if summary_json:
        summary_payload = {
            "market": market,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "totals": totals,
            "totals_by_source": totals_by_source,
            "symbols": per_symbol,
        }
        print(json.dumps(summary_payload, ensure_ascii=True))
    else:
        log(
            "INFO",
            "Summary:"
            f" symbols={totals['symbols']}"
            f" prices={totals['prices']}"
            f" indicators={totals['indicators']}"
            f" news={totals['news']}"
            f" sentiment={totals['sentiment']}"
            f" financials={totals['financials']}",
            force=True,
        )
