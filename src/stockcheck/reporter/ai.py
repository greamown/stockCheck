import json
import os
import time
from typing import Any, Dict, List, Optional

import requests

try:
    from google import genai
except Exception:  # pragma: no cover - optional dependency at runtime
    genai = None

from .models import InstitutionalSnapshot, TickerSnapshot


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
    pipeline_context: Dict[str, Any],
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
        "pipeline": pipeline_context,
    }
    schema = {
        "summary": "string (Chinese, 400-600 chars, 3 paragraphs: 大盤/重要個股/風險)",
        "predictions": "object mapping symbol -> up|down|neutral",
    }
    return (
        "請用中文輸出 JSON，且只輸出 JSON。"
        "summary 需 400-600 字，分成三段：大盤、重要個股、風險。"
        "predictions 要針對 watchlist symbol，輸出 up/down/neutral。"
        "JSON schema: "
        + json.dumps(schema, ensure_ascii=False)
        + "資料如下："
        + json.dumps(data, ensure_ascii=False)
    )


def build_fallback_summary(
    market: str,
    snapshots: List[TickerSnapshot],
    indices: List[TickerSnapshot],
    institutional: List[InstitutionalSnapshot],
    pipeline_context: Dict[str, Any],
) -> str:
    index_lines = []
    for item in indices:
        index_lines.append(
            f"{item.symbol} {item.price:.2f}（{item.change:+.2f}，{item.change_pct:+.2f}%）"
        )
    index_text = "，".join(index_lines) if index_lines else "指數資料不足"

    watchlist_lines = []
    for item in snapshots[:4]:
        if item.ma50 <= 0 or item.ma200 <= 0:
            trend = "資料不足"
        else:
            trend = "強勢" if item.price >= item.ma50 >= item.ma200 else "偏弱"
        news_note = ""
        context = pipeline_context.get(item.symbol, {})
        news_items = context.get("news") or []
        if news_items:
            news_note = f"，焦點：{news_items[0].get('title', '')[:20]}"
        watchlist_lines.append(
            f"{item.symbol} 收於 {item.price:.2f}（{item.change_pct:+.2f}%），"
            f"50/200 日均線 {item.ma50:.2f}/{item.ma200:.2f}，走勢{trend}{news_note}"
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
    max_tokens = int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "800") or 800)
    max_retries = int(os.getenv("AI_MAX_RETRIES", "2") or 2)
    backoff_sec = float(os.getenv("AI_BACKOFF_SEC", "1.5") or 1.5)
    for attempt in range(1, max_retries + 1):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config={
                    "temperature": 0.3,
                    "max_output_tokens": max_tokens,
                    "response_mime_type": "application/json",
                },
            )
            text = getattr(response, "text", "") or ""
            return text.strip() or "Gemini response was empty."
        except Exception as exc:
            message = str(exc)
            if "RESOURCE_EXHAUSTED" in message or "quota" in message.lower():
                print("Gemini quota exhausted; skipping AI summary for now.")
                return "GEMINI_QUOTA_EXCEEDED"
            if attempt == max_retries:
                print(f"Gemini request failed after retries: {exc}")
                return "GEMINI_FAILED"
            time.sleep(backoff_sec * (2 ** (attempt - 1)))


def call_openrouter(prompt: str) -> str:
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        return "OPENROUTER_API_KEY not set; skipped."

    model_name = os.getenv("OPENROUTER_MODEL", "google/gemma-2-9b-it:free")
    max_retries = int(os.getenv("AI_MAX_RETRIES", "2") or 2)
    backoff_sec = float(os.getenv("AI_BACKOFF_SEC", "1.5") or 1.5)
    timeout_sec = float(os.getenv("OPENROUTER_TIMEOUT_SEC", "60") or 60)
    for attempt in range(1, max_retries + 1):
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
                    "max_tokens": int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "800") or 800),
                },
                timeout=timeout_sec,
            )
            response.raise_for_status()
            payload = response.json()
            choice = (payload.get("choices") or [{}])[0]
            content = choice.get("message", {}).get("content", "")
            return content.strip() or "OpenRouter response was empty."
        except requests.RequestException as exc:
            detail = ""
            try:
                detail = response.text
            except Exception:
                detail = ""
            if attempt == max_retries:
                print(f"OpenRouter request failed after retries: {exc} {detail}")
                return "OPENROUTER_FAILED"
            time.sleep(backoff_sec * (2 ** (attempt - 1)))


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    text = text.strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        return None
    return None


def parse_ai_response(response_text: str, symbols: List[str]) -> Dict[str, Any]:
    parsed = _extract_json(response_text)
    summary = response_text.strip()
    predictions = {symbol: "unknown" for symbol in symbols}
    valid_json = False

    if parsed:
        valid_json = True
        summary = str(parsed.get("summary", "")).strip() or summary
        parsed_predictions = parsed.get("predictions", {}) or {}
        if isinstance(parsed_predictions, dict):
            for symbol in symbols:
                value = str(parsed_predictions.get(symbol, "unknown")).lower()
                if value in {"up", "down", "neutral"}:
                    predictions[symbol] = value

    return {"summary": summary, "predictions": predictions, "valid_json": valid_json}
