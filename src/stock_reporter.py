import json
import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import requests
import yfinance as yf
from dotenv import load_dotenv

try:
    from google import genai
    from google.genai import errors as genai_errors
except Exception:  # pragma: no cover - optional dependency at runtime
    genai = None
    genai_errors = None

try:
    from linebot.v3.messaging import (
        ApiClient,
        Configuration,
        FlexContainer,
        FlexMessage,
        MessagingApi,
        PushMessageRequest,
        TextMessage,
    )
    LINE_SDK_IMPORT_ERROR = ""
except Exception as exc:  # pragma: no cover - optional dependency at runtime
    ApiClient = None
    Configuration = None
    FlexContainer = None
    FlexMessage = None
    MessagingApi = None
    PushMessageRequest = None
    TextMessage = None
    LINE_SDK_IMPORT_ERROR = str(exc)


@dataclass
class TickerSnapshot:
    symbol: str
    price: float
    change: float
    change_pct: float
    previous_close: float
    volume: float
    ma50: float
    ma200: float
    earnings_date: str
    earnings_today: bool
    news: List[Dict[str, str]]


@dataclass
class InstitutionalSnapshot:
    symbol: str
    date: str
    total_net: float
    net_by_name: Dict[str, float]


def load_subscriptions(path: str) -> Dict[str, List[str]]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def get_market_timezone(market: str) -> ZoneInfo:
    if market == "tw":
        return ZoneInfo("Asia/Taipei")
    return ZoneInfo("America/New_York")


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
        snapshot = get_price_snapshot(symbol, report_date)
        print(f"Fetched {symbol} price={snapshot.price:.2f}")
        snapshots.append(snapshot)
    return snapshots


def snapshot_to_dict(snapshot: TickerSnapshot) -> Dict[str, Any]:
    return {
        "symbol": snapshot.symbol,
        "price": snapshot.price,
        "change": snapshot.change,
        "change_pct": snapshot.change_pct,
        "previous_close": snapshot.previous_close,
        "volume": snapshot.volume,
        "ma50": snapshot.ma50,
        "ma200": snapshot.ma200,
        "earnings_date": snapshot.earnings_date,
        "earnings_today": snapshot.earnings_today,
        "news": snapshot.news,
    }


def build_prompt(
    market: str,
    snapshots: List[TickerSnapshot],
    indices: List[TickerSnapshot],
    institutional: List[InstitutionalSnapshot],
    timestamp: str,
) -> str:
    data = {
        "market": market,
        "timestamp": timestamp,
        "watchlist": [snapshot_to_dict(s) for s in snapshots],
        "indices": [snapshot_to_dict(s) for s in indices],
        "institutional": [
            {
                "symbol": item.symbol,
                "date": item.date,
                "total_net": item.total_net,
                "net_by_name": item.net_by_name,
            }
            for item in institutional
        ],
    }
    return (
        "請用中文輸出，總字數 400~600 字，必須達到 400 字以上，"
        "格式固定三段且不要加標題符號："
        "第一段「大盤」總結指數與市場氛圍；"
        "第二段「重要個股」挑選 2-4 檔有代表性的標的說明漲跌與原因；"
        "第三段「風險」提醒可能的風險/不確定性。"
        "不要使用 Markdown 或 JSON，只輸出純文字。資料如下："
        + json.dumps(data, ensure_ascii=False)
    )


def build_fallback_summary(
    market: str,
    snapshots: List[TickerSnapshot],
    indices: List[TickerSnapshot],
    institutional: List[InstitutionalSnapshot],
) -> str:
    index_lines = []
    for item in indices:
        index_lines.append(
            f"{item.symbol} {item.price:.2f}（{item.change:+.2f}，{item.change_pct:+.2f}%）"
        )
    index_text = "，".join(index_lines) if index_lines else "指數資料不足"

    watchlist_lines = []
    for item in snapshots[:4]:
        trend = "強勢" if item.price >= item.ma50 >= item.ma200 else "偏弱"
        watchlist_lines.append(
            f"{item.symbol} 收於 {item.price:.2f}（{item.change_pct:+.2f}%），"
            f"50/200 日均線 {item.ma50:.2f}/{item.ma200:.2f}，走勢{trend}"
        )
    watchlist_text = "；".join(watchlist_lines) if watchlist_lines else "個股資料不足"

    inst_text = ""
    if institutional:
        inst_lines = []
        for item in institutional[:3]:
            inst_lines.append(f"{item.symbol} 三大法人淨額 {item.total_net:+,.0f}")
        inst_text = "，" + "；".join(inst_lines)

    risk_text = "需留意財報結果、匯率波動與全球大盤情緒變化，若量能不足，短線波動可能放大。"

    market_name = "台股" if market == "tw" else "美股"
    return (
        f"大盤：{market_name} 指數 {index_text}，整體氣氛以區間震盪為主，短線留意量能與"
        f"法人動向{inst_text}。"
        f"重要個股：{watchlist_text}，可觀察是否站回 50 日線或跌破支撐，作為短線動能判斷。"
        f"風險：{risk_text}"
    )


def call_gemini(prompt: str) -> str:
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        return "Gemini API key not set; skipped AI summary."
    if genai is None:
        return "google-genai not installed; skipped AI summary."

    model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    client = genai.Client(api_key=api_key)
    max_tokens = int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "600") or 600)
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config={
                "temperature": 0.3,
                "max_output_tokens": max_tokens,
                "response_mime_type": "text/plain",
            },
        )
        text = getattr(response, "text", "") or ""
        return text.strip() or "Gemini response was empty."
    except Exception as exc:
        message = str(exc)
        if "RESOURCE_EXHAUSTED" in message or "quota" in message.lower():
            print("Gemini quota exhausted; skipping AI summary for now.")
            return "GEMINI_QUOTA_EXCEEDED"
        raise


def call_openrouter(prompt: str) -> str:
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        return "OPENROUTER_API_KEY not set; skipped."

    model_name = os.getenv("OPENROUTER_MODEL", "google/gemma-2-9b-it:free")
    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": os.getenv("OPENROUTER_REFERER", "http://localhost"),
                "X-Title": os.getenv("OPENROUTER_TITLE", "stockCheck"),
            },
            json={
                "model": model_name,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "600") or 600),
            },
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        choice = (payload.get("choices") or [{}])[0]
        content = choice.get("message", {}).get("content", "")
        return content.strip() or "OpenRouter response was empty."
    except requests.HTTPError as exc:
        detail = ""
        try:
            detail = response.text
        except Exception:
            detail = ""
        print(f"OpenRouter request failed: {exc} {detail}")
        return "OPENROUTER_FAILED"


def parse_ai_response(response_text: str, symbols: List[str]) -> Dict[str, Any]:
    summary = response_text.strip()
    predictions = {symbol: "unknown" for symbol in symbols}
    return {"summary": summary, "predictions": predictions, "valid_json": True}


def format_snapshot(snapshot: TickerSnapshot) -> str:
    return (
        f"{snapshot.symbol} {snapshot.price:.2f} "
        f"({snapshot.change:+.2f}, {snapshot.change_pct:+.2f}%) "
        f"MA50 {snapshot.ma50:.2f} MA200 {snapshot.ma200:.2f} "
        f"Earnings {snapshot.earnings_date or 'N/A'}"
    )


def format_institutional(item: InstitutionalSnapshot) -> str:
    details = ", ".join(f"{name} {value:+,.0f}" for name, value in item.net_by_name.items())
    detail_text = f" ({details})" if details else ""
    return f"{item.symbol} {item.date} Net {item.total_net:+,.0f}{detail_text}"


def build_message(
    market: str,
    snapshots: List[TickerSnapshot],
    indices: List[TickerSnapshot],
    institutional: List[InstitutionalSnapshot],
    ai_summary: str,
    predictions: Dict[str, str],
    earnings_reminder: str,
    accuracy_notes: List[str],
) -> str:
    lines = [f"Market: {market}"]
    if earnings_reminder:
        lines.append(f"Earnings Today: {earnings_reminder}")
    lines.extend(["", "Watchlist:"])
    lines.extend(format_snapshot(s) for s in snapshots)
    lines.append("")
    lines.append("Indices:")
    lines.extend(format_snapshot(s) for s in indices)

    if institutional:
        lines.append("")
        lines.append("Institutional (FinMind):")
        lines.extend(format_institutional(item) for item in institutional)

    lines.append("")
    lines.append("AI Summary:")
    lines.append(ai_summary or "N/A")

    if accuracy_notes:
        lines.append("")
        lines.append("Weekly Accuracy Check:")
        lines.extend(accuracy_notes)

    return "\n".join(lines)


def build_flex_contents(message: str) -> Dict[str, Any]:
    return {
        "type": "bubble",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": "Stock Daily Brief",
                    "weight": "bold",
                    "size": "lg",
                }
            ],
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": message[:1000],
                    "wrap": True,
                    "size": "sm",
                }
            ],
        },
    }


def send_line_message(message: str) -> None:
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    user_id = os.getenv("LINE_USER_ID", "")
    if not token or not user_id:
        print("LINE credentials not set; skipping LINE Messaging API push.")
        return
    if ApiClient is None or Configuration is None or MessagingApi is None:
        detail = f" ({LINE_SDK_IMPORT_ERROR})" if LINE_SDK_IMPORT_ERROR else ""
        print(f"line-bot-sdk not installed; skipping LINE Messaging API push.{detail}")
        return

    configuration = Configuration(access_token=token)
    with ApiClient(configuration) as api_client:
        messaging_api = MessagingApi(api_client)
        try:
            print(f"準備發送報告給用戶 {user_id}...")
            if os.getenv("LINE_USE_FLEX", "").lower() in {"1", "true", "yes"} and FlexMessage:
                contents = build_flex_contents(message)
                container = FlexContainer.from_json(contents)
                flex_message = FlexMessage(alt_text="股票分析報告已送達", contents=container)
                payload = [flex_message]
            else:
                payload = [TextMessage(text=message)]

            messaging_api.push_message(PushMessageRequest(to=user_id, messages=payload))
            print("✅ 訊息發送成功！")
        except Exception as exc:
            print(f"❌ 訊息發送失敗，錯誤原因: {exc}")
            raise RuntimeError(f"LINE Messaging API failed: {exc}") from exc


def strip_tw_symbol(symbol: str) -> str:
    return symbol.split(".")[0]


def fetch_finmind_institutional(
    symbol: str,
    report_date: datetime.date,
    token: str,
) -> Optional[InstitutionalSnapshot]:
    if not token:
        return None

    start_date = (report_date - timedelta(days=14)).isoformat()
    end_date = report_date.isoformat()
    params = {
        "dataset": "TaiwanStockInstitutionalInvestorsBuySell",
        "data_id": strip_tw_symbol(symbol),
        "start_date": start_date,
        "end_date": end_date,
        "token": token,
    }
    response = requests.get("https://api.finmindtrade.com/api/v4/data", params=params, timeout=30)
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data", []) if isinstance(payload, dict) else []
    if not data:
        return None

    latest = max(data, key=lambda item: item.get("date", ""))
    date_str = str(latest.get("date", ""))

    grouped: Dict[str, float] = {}
    for item in data:
        if item.get("date") != date_str:
            continue
        name = str(item.get("name", "")).strip() or "Unknown"
        buy = item.get("buy")
        sell = item.get("sell")
        if buy is None:
            buy = item.get("buy_volume")
        if sell is None:
            sell = item.get("sell_volume")
        if buy is None or sell is None:
            continue
        try:
            net = float(buy) - float(sell)
        except (TypeError, ValueError):
            continue
        grouped[name] = grouped.get(name, 0.0) + net

    total_net = sum(grouped.values())
    return InstitutionalSnapshot(symbol=symbol, date=date_str, total_net=total_net, net_by_name=grouped)


def collect_finmind_data(symbols: List[str], report_date: datetime.date) -> List[InstitutionalSnapshot]:
    token = os.getenv("FINMIND_API_KEY", "")
    snapshots = []
    for symbol in symbols:
        item = fetch_finmind_institutional(symbol, report_date, token)
        if item:
            snapshots.append(item)
    return snapshots


def get_db_path() -> str:
    path = os.getenv("REPORT_DB_PATH", "")
    if path:
        return path
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    return os.path.join(root, "data", "reports.db")


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
    target_date = (report_date - timedelta(days=7)).isoformat()
    compare_date = report_date.isoformat()
    notes = []

    for snapshot in snapshots:
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


def run(market: str, subscription_path: str) -> None:
    load_dotenv()
    subscriptions = load_subscriptions(subscription_path)
    watchlist = subscriptions.get(market, [])
    if not watchlist:
        raise ValueError(f"No subscriptions for market '{market}'")

    timezone = get_market_timezone(market)
    now = datetime.now(timezone)
    report_date = now.date()
    report_date_str = report_date.isoformat()
    print(f"Run start market={market} date={report_date_str} watchlist={len(watchlist)}")

    if market == "tw":
        index_symbols = ["^TWII"]
    else:
        index_symbols = ["^GSPC", "^IXIC", "^DJI"]

    snapshots = collect_market_data(watchlist, report_date)
    indices = collect_market_data(index_symbols, report_date)
    print(f"Fetched snapshots={len(snapshots)} indices={len(indices)}")
    institutional = collect_finmind_data(watchlist, report_date) if market == "tw" else []
    if market == "tw":
        print(
            "FinMind enabled="
            f"{bool(os.getenv('FINMIND_API_KEY'))} items={len(institutional)}"
        )

    print("Calling Gemini...")
    prompt = build_prompt(market, snapshots, indices, institutional, now.isoformat())
    ai_raw = call_gemini(prompt)
    print(f"Gemini response length={len(ai_raw)}")
    parsed = parse_ai_response(ai_raw, [s.symbol for s in snapshots])
    ai_summary = parsed["summary"]
    if "GEMINI_QUOTA_EXCEEDED" in ai_summary:
        print("Gemini quota exceeded; trying OpenRouter fallback.")
        ai_summary = call_openrouter(prompt)
        if "OPENROUTER_API_KEY not set" in ai_summary or "OPENROUTER_FAILED" in ai_summary:
            print("OpenRouter not available; sending AI unavailable message.")
            ai_summary = "AI 無法回復，請稍後再試。"
    elif len(ai_summary) < 400:
        print("Gemini summary too short; retrying with stricter instruction.")
        retry_prompt = (
            "請用中文輸出，總字數 400~600 字，必須達到 400 字以上。"
            "務必包含三段內容：大盤、重要個股、風險。"
            "不要使用 Markdown 或 JSON，只輸出純文字。資料如下："
            + json.dumps(
                {
                    "market": market,
                    "watchlist": [snapshot_to_dict(s) for s in snapshots],
                    "indices": [snapshot_to_dict(s) for s in indices],
                    "institutional": [
                        {
                            "symbol": item.symbol,
                            "date": item.date,
                            "total_net": item.total_net,
                            "net_by_name": item.net_by_name,
                        }
                        for item in institutional
                    ],
                },
                ensure_ascii=False,
            )
        )
        ai_raw = call_gemini(retry_prompt)
        parsed = parse_ai_response(ai_raw, [s.symbol for s in snapshots])
        ai_summary = parsed["summary"]
    if len(ai_summary) < 400:
        print("Gemini summary still short; using fallback summary.")
        ai_summary = build_fallback_summary(market, snapshots, indices, institutional)

    predictions = parsed["predictions"]

    earnings_today = [s.symbol for s in snapshots if s.earnings_today]
    earnings_reminder = ", ".join(earnings_today)

    db_path = get_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        init_db(conn)
        print(f"DB save reports={len(snapshots)} path={db_path}")
        save_reports(conn, market, report_date_str, snapshots, ai_summary, predictions)
        accuracy_notes = compare_predictions(conn, market, report_date, snapshots, predictions)
        print(f"Accuracy checks={len(accuracy_notes)}")
    finally:
        conn.close()

    message = build_message(
        market,
        snapshots,
        indices,
        institutional,
        ai_summary,
        predictions,
        earnings_reminder,
        accuracy_notes,
    )

    print(f"AI summary length={len(ai_summary)}")
    print(f"LINE message length={len(message)}")
    print(message)
    send_line_message(message)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Daily stock summary sender.")
    parser.add_argument("--market", required=True, choices=["tw", "us"], help="Market key")
    parser.add_argument(
        "--config",
        default=os.path.join(os.path.dirname(__file__), "..", "config", "subscriptions.json"),
        help="Path to subscriptions JSON",
    )

    args = parser.parse_args()
    run(args.market, os.path.abspath(args.config))
