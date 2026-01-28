from datetime import datetime, timedelta
from typing import Dict, List, Optional

import requests

from .models import InstitutionalSnapshot


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


def collect_finmind_data(symbols: List[str], report_date: datetime.date, token: str) -> List[InstitutionalSnapshot]:
    snapshots = []
    for symbol in symbols:
        item = fetch_finmind_institutional(symbol, report_date, token)
        if item:
            snapshots.append(item)
    return snapshots
