from typing import Dict, List

from .models import InstitutionalSnapshot, TickerSnapshot


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
