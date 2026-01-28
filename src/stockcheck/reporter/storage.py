import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

from stockcheck.pipeline import db as pipeline_db

from .models import TickerSnapshot


def get_db_path() -> str:
    path = os.getenv("REPORT_DB_PATH", "")
    if path:
        return path
    root = Path(__file__).resolve().parents[3]
    return str(root / "data" / "reports.db")


def load_pipeline_context(market: str, symbols: List[str]) -> Dict[str, Any]:
    db_path = pipeline_db.get_pipeline_db_path()
    if not os.path.exists(db_path):
        return {}

    context: Dict[str, Any] = {}
    conn = sqlite3.connect(db_path)
    try:
        for symbol in symbols:
            indicators = conn.execute(
                """
                SELECT date, sma20, sma50, ema12, ema26, rsi14, macd, macd_signal, macd_hist,
                       bb_mid, bb_upper, bb_lower
                FROM indicators_daily
                WHERE market = ? AND symbol = ?
                ORDER BY date DESC
                LIMIT 1
                """,
                (market, symbol),
            ).fetchone()
            news_rows = conn.execute(
                """
                SELECT title, url, published_at, source
                FROM news_items
                WHERE market = ? AND symbol = ?
                ORDER BY published_at DESC
                LIMIT 3
                """,
                (market, symbol),
            ).fetchall()
            sentiment_rows = conn.execute(
                """
                SELECT title, url, published_at, source, score
                FROM sentiment_items
                WHERE market = ? AND symbol = ?
                ORDER BY published_at DESC
                LIMIT 3
                """,
                (market, symbol),
            ).fetchall()
            financial_rows = conn.execute(
                """
                SELECT report_type, source
                FROM financials
                WHERE market = ? AND symbol = ?
                """,
                (market, symbol),
            ).fetchall()

            payload: Dict[str, Any] = {}
            if indicators:
                (
                    date_str,
                    sma20,
                    sma50,
                    ema12,
                    ema26,
                    rsi14,
                    macd,
                    macd_signal,
                    macd_hist,
                    bb_mid,
                    bb_upper,
                    bb_lower,
                ) = indicators
                payload["indicators"] = {
                    "date": date_str,
                    "sma20": sma20,
                    "sma50": sma50,
                    "ema12": ema12,
                    "ema26": ema26,
                    "rsi14": rsi14,
                    "macd": macd,
                    "macd_signal": macd_signal,
                    "macd_hist": macd_hist,
                    "bb_mid": bb_mid,
                    "bb_upper": bb_upper,
                    "bb_lower": bb_lower,
                }
            if news_rows:
                payload["news"] = [
                    {
                        "title": title,
                        "url": url,
                        "published_at": published_at,
                        "source": source,
                    }
                    for title, url, published_at, source in news_rows
                ]
            if sentiment_rows:
                payload["sentiment"] = [
                    {
                        "title": title,
                        "url": url,
                        "published_at": published_at,
                        "source": source,
                        "score": score,
                    }
                    for title, url, published_at, source, score in sentiment_rows
                ]
            if financial_rows:
                payload["financials"] = [
                    {"report_type": report_type, "source": source}
                    for report_type, source in financial_rows
                ]
            if payload:
                context[symbol] = payload
    finally:
        conn.close()

    return context


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reports (
            market TEXT NOT NULL,
            symbol TEXT NOT NULL,
            report_date TEXT NOT NULL,
            price REAL NOT NULL,
            ai_summary TEXT NOT NULL,
            ai_prediction TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (market, symbol, report_date)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS accuracy (
            market TEXT NOT NULL,
            symbol TEXT NOT NULL,
            report_date TEXT NOT NULL,
            report_price REAL NOT NULL,
            compare_date TEXT NOT NULL,
            compare_price REAL NOT NULL,
            ai_prediction TEXT NOT NULL,
            actual_direction TEXT NOT NULL,
            hit INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (market, symbol, report_date)
        )
        """
    )
    conn.commit()


def save_reports(
    conn: sqlite3.Connection,
    market: str,
    report_date: str,
    snapshots: List[TickerSnapshot],
    ai_summary: str,
    predictions: Dict[str, str],
) -> None:
    created_at = datetime.utcnow().isoformat() + "Z"
    for snapshot in snapshots:
        conn.execute(
            """
            INSERT OR REPLACE INTO reports (market, symbol, report_date, price, ai_summary, ai_prediction, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                market,
                snapshot.symbol,
                report_date,
                snapshot.price,
                ai_summary,
                predictions.get(snapshot.symbol, "unknown"),
                created_at,
            ),
        )
    conn.commit()


def compare_predictions(
    conn: sqlite3.Connection,
    market: str,
    report_date: datetime.date,
    snapshots: List[TickerSnapshot],
    predictions: Dict[str, str],
) -> List[str]:
    compare_date = report_date.isoformat()
    notes = []

    for snapshot in snapshots:
        report_dates = conn.execute(
            """
            SELECT report_date
            FROM reports
            WHERE market = ? AND symbol = ? AND report_date < ?
            ORDER BY report_date DESC
            LIMIT 7
            """,
            (market, snapshot.symbol, compare_date),
        ).fetchall()
        if not report_dates:
            continue
        if len(report_dates) >= 7:
            target_date = report_dates[-1][0]
        else:
            target_date = report_dates[0][0]

        cursor = conn.execute(
            """
            SELECT price, ai_prediction FROM reports
            WHERE market = ? AND symbol = ? AND report_date = ?
            """,
            (market, snapshot.symbol, target_date),
        )
        row = cursor.fetchone()
        if not row:
            continue

        report_price, ai_prediction = row
        if ai_prediction == "unknown":
            continue
        ai_prediction = ai_prediction or predictions.get(snapshot.symbol, "unknown")
        if snapshot.price > report_price:
            actual_direction = "up"
        elif snapshot.price < report_price:
            actual_direction = "down"
        else:
            actual_direction = "neutral"

        hit = int(ai_prediction == actual_direction)
        conn.execute(
            """
            INSERT OR REPLACE INTO accuracy (
                market, symbol, report_date, report_price, compare_date, compare_price,
                ai_prediction, actual_direction, hit, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                market,
                snapshot.symbol,
                target_date,
                report_price,
                compare_date,
                snapshot.price,
                ai_prediction,
                actual_direction,
                hit,
                datetime.utcnow().isoformat() + "Z",
            ),
        )
        status = "HIT" if hit else "MISS"
        notes.append(
            f"{snapshot.symbol}: predicted {ai_prediction}, actual {actual_direction} ({status})"
        )

    conn.commit()
    return notes
