from dataclasses import dataclass
from typing import Dict, List


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
