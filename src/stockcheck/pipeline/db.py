import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import PriceRow


def get_pipeline_db_path() -> str:
    path = os.getenv("PIPELINE_DB_PATH", "")
    if path:
        return path
    root = Path(__file__).resolve().parents[3]
    return str(root / "data" / "market_data.db")


def connect(db_path: str) -> sqlite3.Connection:
    timeout_sec = float(os.getenv("SQLITE_BUSY_TIMEOUT_SEC", "30") or 30)
    conn = sqlite3.connect(db_path, timeout=timeout_sec)
    busy_timeout_ms = int(timeout_sec * 1000)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(f"PRAGMA busy_timeout = {busy_timeout_ms}")
    except sqlite3.OperationalError:
        pass
    return conn


def init_pipeline_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS price_daily (
            market TEXT NOT NULL,
            symbol TEXT NOT NULL,
            date TEXT NOT NULL,
            open REAL NOT NULL,
            high REAL NOT NULL,
            low REAL NOT NULL,
            close REAL NOT NULL,
            volume REAL NOT NULL,
            source TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (market, symbol, date)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS indicators_daily (
            market TEXT NOT NULL,
            symbol TEXT NOT NULL,
            date TEXT NOT NULL,
            sma20 REAL,
            sma50 REAL,
            ema12 REAL,
            ema26 REAL,
            rsi14 REAL,
            macd REAL,
            macd_signal REAL,
            macd_hist REAL,
            bb_mid REAL,
            bb_upper REAL,
            bb_lower REAL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (market, symbol, date)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS news_items (
            market TEXT NOT NULL,
            symbol TEXT NOT NULL,
            published_at TEXT,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            source TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (market, symbol, url)
        )
        """
    )
    financials_exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='financials'"
    ).fetchone()
    if financials_exists:
        info = conn.execute("PRAGMA table_info(financials)").fetchall()
        period_pk = 0
        for row in info:
            if row[1] == "period_end":
                period_pk = row[5]
                break
        if period_pk == 0:
            conn.execute(
                """
                CREATE TABLE financials_v2 (
                    market TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    period_end TEXT NOT NULL,
                    report_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (market, symbol, report_type, period_end)
                )
                """
            )
            conn.execute(
                """
                INSERT INTO financials_v2 (
                    market, symbol, period_end, report_type, payload_json, source, created_at
                )
                SELECT market, symbol, COALESCE(period_end, ''), report_type, payload_json, source, created_at
                FROM financials
                """
            )
            conn.execute("DROP TABLE financials")
            conn.execute("ALTER TABLE financials_v2 RENAME TO financials")
    else:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS financials (
                market TEXT NOT NULL,
                symbol TEXT NOT NULL,
                period_end TEXT NOT NULL,
                report_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                source TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (market, symbol, report_type, period_end)
            )
            """
        )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sentiment_items (
            market TEXT NOT NULL,
            symbol TEXT NOT NULL,
            published_at TEXT,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            source TEXT NOT NULL,
            score REAL NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (market, symbol, url)
        )
        """
    )
    conn.commit()


def save_prices(conn: sqlite3.Connection, market: str, symbol: str, rows: List[PriceRow]) -> None:
    created_at = datetime.utcnow().isoformat() + "Z"
    for row in rows:
        conn.execute(
            """
            INSERT OR REPLACE INTO price_daily
            (market, symbol, date, open, high, low, close, volume, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                market,
                symbol,
                row.date,
                row.open,
                row.high,
                row.low,
                row.close,
                row.volume,
                row.source,
                created_at,
            ),
        )
    conn.commit()


def save_indicators(
    conn: sqlite3.Connection,
    market: str,
    symbol: str,
    indicators: List[Dict[str, Optional[float]]],
) -> None:
    created_at = datetime.utcnow().isoformat() + "Z"
    for item in indicators:
        conn.execute(
            """
            INSERT OR REPLACE INTO indicators_daily
            (market, symbol, date, sma20, sma50, ema12, ema26, rsi14,
             macd, macd_signal, macd_hist, bb_mid, bb_upper, bb_lower, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                market,
                symbol,
                item["date"],
                item["sma20"],
                item["sma50"],
                item["ema12"],
                item["ema26"],
                item["rsi14"],
                item["macd"],
                item["macd_signal"],
                item["macd_hist"],
                item["bb_mid"],
                item["bb_upper"],
                item["bb_lower"],
                created_at,
            ),
        )
    conn.commit()


def save_news(conn: sqlite3.Connection, market: str, symbol: str, items: List[Dict[str, str]]) -> None:
    created_at = datetime.utcnow().isoformat() + "Z"
    for item in items:
        url = item.get("url") or ""
        if not url:
            continue
        conn.execute(
            """
            INSERT OR REPLACE INTO news_items
            (market, symbol, published_at, title, url, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                market,
                symbol,
                item.get("published_at"),
                item.get("title", ""),
                url,
                item.get("source", "google_news"),
                created_at,
            ),
        )
    conn.commit()


def save_financials(
    conn: sqlite3.Connection,
    market: str,
    symbol: str,
    period_end: str,
    report_type: str,
    payload: Dict[str, Any],
    source: str,
) -> None:
    if not payload:
        return
    created_at = datetime.utcnow().isoformat() + "Z"
    conn.execute(
        """
        INSERT OR REPLACE INTO financials
        (market, symbol, period_end, report_type, payload_json, source, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            market,
            symbol,
            period_end or "",
            report_type,
            json.dumps(payload),
            source,
            created_at,
        ),
    )
    conn.commit()


def save_sentiment(conn: sqlite3.Connection, market: str, symbol: str, items: List[Dict[str, str]]) -> None:
    created_at = datetime.utcnow().isoformat() + "Z"
    for item in items:
        url = item.get("url") or ""
        if not url:
            continue
        conn.execute(
            """
            INSERT OR REPLACE INTO sentiment_items
            (market, symbol, published_at, title, url, source, score, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                market,
                symbol,
                item.get("published_at"),
                item.get("title", ""),
                url,
                item.get("source", "reddit"),
                float(item.get("score") or 0.0),
                created_at,
            ),
        )
    conn.commit()
