from __future__ import annotations

from typing import Dict, List, Any

from .models import InstitutionalSnapshot, TickerSnapshot


def _market_name(market: str) -> str:
    return "台股" if market == "tw" else "美股"


def _prediction_to_zh(value: str) -> str:
    value = (value or "").lower().strip()
    if value == "up":
        return "偏多"
    if value == "down":
        return "偏空"
    if value == "neutral":
        return "中性"
    return "未知"


def _normalize_news(items: Any) -> List[Dict[str, str]]:
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
        normalized.append({"title": title, "url": url, "published_at": published_at, "source": source})
    return normalized


def _short_domain(url: str) -> str:
    try:
        from urllib.parse import urlparse

        host = urlparse(url).netloc
        return host.replace("www.", "") if host else ""
    except Exception:
        return ""


def format_snapshot_line(snapshot: TickerSnapshot, prediction: str) -> str:
    return (
        f"- {snapshot.symbol} {snapshot.price:.2f}（{snapshot.change_pct:+.2f}%）"
        f"｜MA50/200 {snapshot.ma50:.2f}/{snapshot.ma200:.2f}"
        f"｜明日：{_prediction_to_zh(prediction)}"
    )


def format_index_line(snapshot: TickerSnapshot) -> str:
    return f"- {snapshot.symbol} {snapshot.price:.2f}（{snapshot.change_pct:+.2f}%）"


def format_institutional(item: InstitutionalSnapshot) -> str:
    details = ", ".join(f"{name} {value:+,.0f}" for name, value in item.net_by_name.items())
    detail_text = f"（{details}）" if details else ""
    return f"- {item.symbol} {item.date} 三大法人淨額 {item.total_net:+,.0f} {detail_text}".strip()


def build_message(
    market: str,
    snapshots: List[TickerSnapshot],
    indices: List[TickerSnapshot],
    institutional: List[InstitutionalSnapshot],
    ai_summary: str,
    predictions: Dict[str, str],
    earnings_reminder: str,
    accuracy_notes: List[str],
    pipeline_context: Dict[str, Any] | None = None,
) -> str:
    """Build a clean, consistent plain-text message for messaging apps.

    If pipeline_context is provided, prefer its news for each symbol.
    """

    lines: List[str] = []
    lines.append(f"【每日盤勢】{_market_name(market)}")

    if earnings_reminder:
        lines.append(f"【財報提醒】今日可能公布：{earnings_reminder}")

    if indices:
        lines.append("【指數】")
        lines.extend(format_index_line(s) for s in indices)

    if snapshots:
        lines.append("【重點個股】")
        for s in snapshots:
            pred = (predictions or {}).get(s.symbol, "unknown")
            lines.append(format_snapshot_line(s, pred))

            # News: prefer pipeline/google RSS if available
            ctx = (pipeline_context or {}).get(s.symbol, {}) if isinstance(pipeline_context, dict) else {}
            ctx_news = _normalize_news(ctx.get("news"))
            use_news = ctx_news or _normalize_news(s.news)
            use_news = use_news[:3]
            if use_news:
                lines.append("  新聞：")
                for item in use_news:
                    title = item.get("title", "").strip()
                    source = item.get("source", "unknown").strip()
                    url = item.get("url", "").strip()
                    domain = _short_domain(url) if url else ""
                    meta = " / ".join([p for p in [domain, source] if p])
                    meta = f"（{meta}）" if meta else ""
                    if url:
                        lines.append(f"  - {title}{meta}\n    {url}")
                    else:
                        lines.append(f"  - {title}{meta}")

    if institutional:
        lines.append("【三大法人（FinMind）】")
        lines.extend(format_institutional(item) for item in institutional)

    lines.append("【AI 摘要】")
    lines.append((ai_summary or "N/A").strip())

    if accuracy_notes:
        lines.append("【近 7 次預測回測】")
        lines.extend(f"- {note}" for note in accuracy_notes)

    return "\n".join(lines).strip() + "\n"
