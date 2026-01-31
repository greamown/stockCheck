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


def _normalize_news_items(items: Any) -> List[Dict[str, str]]:
    """Normalize news items into a consistent schema:
    {title, url, published_at, source}
    """
    normalized: List[Dict[str, str]] = []
    if not isinstance(items, list):
        return normalized
    for raw in items:
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("title") or "").strip()
        url = str(raw.get("url") or raw.get("link") or "").strip()
        published_at = str(raw.get("published_at") or "").strip()
        source = str(raw.get("source") or raw.get("publisher") or "").strip() or "unknown"
        if not title and not url:
            continue
        normalized.append(
            {
                "title": title,
                "url": url,
                "published_at": published_at,
                "source": source,
            }
        )
    return normalized


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
        # Keep news in normalized schema.
        "news": _normalize_news_items(snapshot.news),
    }


def build_prompt(
    market: str,
    snapshots: List[TickerSnapshot],
    indices: List[TickerSnapshot],
    institutional: List[InstitutionalSnapshot],
    pipeline_context: Dict[str, Any],
    timestamp: str,
) -> str:
    # Strengthen news usage:
    # - Prefer pipeline_context news (Google RSS) if available.
    # - Fall back to yfinance snapshot.news only when pipeline news is missing.
    watchlist_payload: List[Dict[str, Any]] = []
    for s in snapshots:
        base = snapshot_to_dict(s)
        ctx = pipeline_context.get(s.symbol, {}) if isinstance(pipeline_context, dict) else {}
        ctx_news = _normalize_news_items(ctx.get("news"))
        if ctx_news:
            base["news"] = ctx_news
            base["news_note"] = "來源：pipeline/google_news（優先）"
        else:
            base["news"] = _normalize_news_items(s.news)
            base["news_note"] = "來源：yfinance（備援，可能較少/較不完整）"
        # Include a tiny slice of pipeline indicators/sentiment metadata (if present) without duplicating raw tables.
        if isinstance(ctx, dict):
            if ctx.get("indicators"):
                base["pipeline_indicators"] = ctx.get("indicators")
            if ctx.get("sentiment"):
                base["pipeline_sentiment"] = ctx.get("sentiment")
        watchlist_payload.append(base)

    data = {
        "market": market,
        "timestamp": timestamp,
        "watchlist": watchlist_payload,
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
        # Keep pipeline context for transparency/debugging, but the model should primarily use watchlist[*].news.
        "pipeline": pipeline_context,
    }
    schema = {
        "summary": "string (Chinese, 400-600 chars, 3 paragraphs: 大盤/重要個股/風險)",
        "predictions": "object mapping symbol -> up|down|neutral",
        "citations": "array of objects {symbol, title, url} (引用到的新聞；至少 1 則，最多 3 則)",
    }
    return (
        "請用中文輸出 JSON，且只輸出 JSON。"
        "summary 需 400-600 字，分成三段：大盤、重要個股、風險。"
        "predictions 要針對 watchlist symbol，輸出 up/down/neutral。"
        "你必須閱讀 watchlist[*].news，並在輸出 JSON 裡提供 citations："
        "列出你在 summary 內引用到的新聞（至少 1 則，最多 3 則），"
        "每筆包含 symbol、title、url。"
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
    # Keep fallback readable and consistent with the main report style.
    # Use 3 clear sections: 【大盤】/【個股】/【風險】.

    index_lines = []
    for item in indices:
        index_lines.append(f"{item.symbol} {item.price:.2f}（{item.change_pct:+.2f}%）")
    index_text = "、".join(index_lines) if index_lines else "指數資料不足"

    market_name = "台股" if market == "tw" else "美股"

    inst_text = ""
    if institutional:
        inst_lines = []
        for item in institutional[:3]:
            inst_lines.append(f"{item.symbol} 法人淨額 {item.total_net:+,.0f}")
        inst_text = "；" + "、".join(inst_lines)

    stock_lines = []
    for item in snapshots[:4]:
        if item.ma50 <= 0 or item.ma200 <= 0:
            trend = "資料不足"
        else:
            trend = "偏強" if item.price >= item.ma50 >= item.ma200 else "偏弱"

        news_hint = ""
        ctx = pipeline_context.get(item.symbol, {}) if isinstance(pipeline_context, dict) else {}
        news_items = ctx.get("news") or []
        if isinstance(news_items, list) and news_items:
            title = str((news_items[0] or {}).get("title", "")).strip()
            if title:
                news_hint = f"｜新聞：{title[:28]}"

        stock_lines.append(
            f"- {item.symbol} {item.price:.2f}（{item.change_pct:+.2f}%）"
            f"｜MA50/200 {item.ma50:.2f}/{item.ma200:.2f}｜趨勢：{trend}{news_hint}"
        )

    if not stock_lines:
        stock_lines = ["- 個股資料不足"]

    risk_text = "留意財報/法說、匯率與國際盤波動；若量能不足，短線震盪可能放大。"

    return (
        f"【大盤】{market_name} 指數 {index_text}，偏區間震盪，留意量能與法人動向{inst_text}\n"
        f"【個股】\n" + "\n".join(stock_lines) + "\n"
        f"【風險】{risk_text}"
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
    citations: List[Dict[str, str]] = []
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

        parsed_citations = parsed.get("citations", []) or []
        if isinstance(parsed_citations, list):
            for item in parsed_citations[:3]:
                if not isinstance(item, dict):
                    continue
                sym = str(item.get("symbol", "")).strip()
                title = str(item.get("title", "")).strip()
                url = str(item.get("url", "")).strip()
                if sym and title:
                    citations.append({"symbol": sym, "title": title, "url": url})

    return {
        "summary": summary,
        "predictions": predictions,
        "citations": citations,
        "valid_json": valid_json,
    }
