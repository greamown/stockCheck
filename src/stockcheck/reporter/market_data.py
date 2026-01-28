import os
import time
from datetime import datetime
from typing import Dict, List, Optional

import yfinance as yf

from .models import TickerSnapshot


def get_yfinance_settings() -> Dict[str, float]:
    retries = int(os.getenv("YFINANCE_RETRIES", "3") or 3)
    delay_sec = float(os.getenv("YFINANCE_DELAY_SEC", "1.5") or 1.5)
    return {"retries": retries, "delay_sec": delay_sec}


def fetch_history(ticker: yf.Ticker, period: str, retries: Optional[int] = None, delay_sec: Optional[float] = None):
    settings = get_yfinance_settings()
    retries = settings["retries"] if retries is None else retries
    delay_sec = settings["delay_sec"] if delay_sec is None else delay_sec

    last_error = None
    for attempt in range(1, retries + 1):
        try:
            return ticker.history(period=period)
        except Exception as exc:
            last_error = exc
            print(f"History fetch failed period={period} attempt={attempt}: {exc}")
            time.sleep(delay_sec)
    if last_error:
        raise last_error
    return ticker.history(period=period)


def get_price_snapshot(symbol: str, report_date: datetime.date) -> TickerSnapshot:
    ticker = yf.Ticker(symbol)
    history = fetch_history(ticker, "2d")
    if history.empty:
        raise ValueError(f"No price data for {symbol}")

    latest = history.iloc[-1]
    previous = history.iloc[-2] if len(history) > 1 else latest
    price = float(latest["Close"])
    previous_close = float(previous["Close"])
    change = price - previous_close
    change_pct = (change / previous_close) * 100 if previous_close else 0.0

    volume = float(latest.get("Volume", 0.0) or 0.0)

    long_history = fetch_history(ticker, "1y")
    ma50 = float(long_history["Close"].tail(50).mean()) if not long_history.empty else 0.0
    ma200 = float(long_history["Close"].tail(200).mean()) if not long_history.empty else 0.0

    earnings_date = ""
    earnings_today = False
    news_items = []
    is_index = symbol.startswith("^")
    if not is_index:
        try:
            calendar = ticker.calendar
            if not calendar.empty:
                earnings_ts = calendar.iloc[0, 0]
                earnings_date = str(earnings_ts.date())
                earnings_today = earnings_ts.date() == report_date
        except Exception:
            earnings_date = ""
            earnings_today = False

        try:
            for item in (ticker.news or [])[:3]:
                news_items.append(
                    {
                        "title": item.get("title", ""),
                        "link": item.get("link", ""),
                        "publisher": item.get("publisher", ""),
                    }
                )
        except Exception:
            news_items = []

    return TickerSnapshot(
        symbol=symbol,
        price=price,
        change=change,
        change_pct=change_pct,
        previous_close=previous_close,
        volume=volume,
        ma50=ma50,
        ma200=ma200,
        earnings_date=earnings_date,
        earnings_today=earnings_today,
        news=news_items,
    )


def collect_market_data(symbols: List[str], report_date: datetime.date) -> List[TickerSnapshot]:
    snapshots = []
    for symbol in symbols:
        try:
            snapshot = get_price_snapshot(symbol, report_date)
        except Exception as exc:
            print(f"Failed to fetch {symbol}: {exc}")
            continue
        print(f"Fetched {symbol} price={snapshot.price:.2f}")
        snapshots.append(snapshot)
    return snapshots
