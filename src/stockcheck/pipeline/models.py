from dataclasses import dataclass


@dataclass
class PriceRow:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str
