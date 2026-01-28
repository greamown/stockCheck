import json
import os
import sqlite3
from datetime import datetime
from typing import Dict, List
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from . import ai, institutional, market_data, message, storage


def load_subscriptions(path: str) -> Dict[str, List[str]]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def get_market_timezone(market: str) -> ZoneInfo:
    if market == "tw":
        return ZoneInfo("Asia/Taipei")
    return ZoneInfo("America/New_York")


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

    snapshots = market_data.collect_market_data(watchlist, report_date)
    indices = market_data.collect_market_data(index_symbols, report_date)
    print(f"Fetched snapshots={len(snapshots)} indices={len(indices)}")
    if not snapshots:
        raise RuntimeError("No snapshots collected; aborting report run.")

    finmind_token = os.getenv("FINMIND_API_KEY", "")
    institutional_data = (
        institutional.collect_finmind_data(watchlist, report_date, finmind_token)
        if market == "tw"
        else []
    )
    if market == "tw":
        print(f"FinMind enabled={bool(finmind_token)} items={len(institutional_data)}")

    pipeline_context = storage.load_pipeline_context(market, watchlist)
    if pipeline_context:
        print(f"Pipeline context loaded symbols={len(pipeline_context)}")

    print("Calling Gemini...")
    allow_retry = True
    prompt = ai.build_prompt(
        market,
        snapshots,
        indices,
        institutional_data,
        pipeline_context,
        now.isoformat(),
    )
    try:
        ai_raw = ai.call_gemini(prompt)
    except Exception as exc:
        print(f"Gemini request raised an exception: {exc}")
        ai_raw = "GEMINI_FAILED"
    print(f"Gemini response length={len(ai_raw)}")
    parsed = ai.parse_ai_response(ai_raw, [s.symbol for s in snapshots])
    ai_summary = parsed["summary"]

    if "GEMINI_QUOTA_EXCEEDED" in ai_summary or "GEMINI_FAILED" in ai_summary:
        print("Gemini unavailable; trying OpenRouter fallback.")
        try:
            ai_raw = ai.call_openrouter(prompt)
        except Exception as exc:
            print(f"OpenRouter request raised an exception: {exc}")
            ai_raw = "OPENROUTER_FAILED"
        if "OPENROUTER_API_KEY not set" in ai_raw or "OPENROUTER_FAILED" in ai_raw:
            print("OpenRouter not available; using fallback summary.")
            ai_summary = ai.build_fallback_summary(
                market,
                snapshots,
                indices,
                institutional_data,
                pipeline_context,
            )
            parsed = {"predictions": {s.symbol: "unknown" for s in snapshots}, "valid_json": False}
            allow_retry = False
        else:
            parsed = ai.parse_ai_response(ai_raw, [s.symbol for s in snapshots])
            ai_summary = parsed["summary"]
    elif "skipped AI summary" in ai_summary:
        ai_summary = ai.build_fallback_summary(
            market,
            snapshots,
            indices,
            institutional_data,
            pipeline_context,
        )
        parsed = {"predictions": {s.symbol: "unknown" for s in snapshots}, "valid_json": False}
        allow_retry = False

    if allow_retry and (not parsed.get("valid_json") or len(ai_summary) < 400):
        print("Gemini summary invalid/short; retrying with stricter instruction.")
        retry_prompt = (
            "請用中文輸出 JSON，且只輸出 JSON。summary 需 400-600 字，"
            "分成三段：大盤、重要個股、風險。predictions 必須回傳 up/down/neutral。資料如下："
            + json.dumps(
                {
                    "market": market,
                    "watchlist": [ai.snapshot_to_dict(s) for s in snapshots],
                    "indices": [ai.snapshot_to_dict(s) for s in indices],
                    "institutional": [
                        {
                            "symbol": item.symbol,
                            "date": item.date,
                            "total_net": item.total_net,
                            "net_by_name": item.net_by_name,
                        }
                        for item in institutional_data
                    ],
                    "pipeline": pipeline_context,
                },
                ensure_ascii=False,
            )
        )
        ai_raw = ai.call_gemini(retry_prompt)
        parsed = ai.parse_ai_response(ai_raw, [s.symbol for s in snapshots])
        ai_summary = parsed["summary"]

    if len(ai_summary) < 400:
        print("Gemini summary still short; using fallback summary.")
        ai_summary = ai.build_fallback_summary(
            market,
            snapshots,
            indices,
            institutional_data,
            pipeline_context,
        )

    predictions = parsed.get("predictions", {s.symbol: "unknown" for s in snapshots})

    earnings_today = [s.symbol for s in snapshots if s.earnings_today]
    earnings_reminder = ", ".join(earnings_today)

    db_path = storage.get_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        storage.init_db(conn)
        print(f"DB save reports={len(snapshots)} path={db_path}")
        storage.save_reports(conn, market, report_date_str, snapshots, ai_summary, predictions)
        accuracy_notes = storage.compare_predictions(conn, market, report_date, snapshots, predictions)
        print(f"Accuracy checks={len(accuracy_notes)}")
    finally:
        conn.close()

    final_message = message.build_message(
        market,
        snapshots,
        indices,
        institutional_data,
        ai_summary,
        predictions,
        earnings_reminder,
        accuracy_notes,
    )

    print(f"AI summary length={len(ai_summary)}")
    print(f"LINE message length={len(final_message)}")
    print(final_message)
    from .line_messaging import send_line_message

    send_line_message(final_message)
