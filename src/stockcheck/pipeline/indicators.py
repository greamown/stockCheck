from typing import Dict, List, Optional

import pandas as pd

from .models import PriceRow


def _sma(series: pd.Series, length: int) -> pd.Series:
    return series.rolling(window=length, min_periods=length).mean()


def _ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False, min_periods=length).mean()


def _rsi(series: pd.Series, length: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    avg_loss = loss.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _macd(series: pd.Series, fast: int, slow: int, signal: int) -> pd.DataFrame:
    macd_line = _ema(series, fast) - _ema(series, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    hist = macd_line - signal_line
    return pd.DataFrame({"macd": macd_line, "signal": signal_line, "hist": hist})


def _bbands(series: pd.Series, length: int, std: float) -> pd.DataFrame:
    mid = series.rolling(window=length, min_periods=length).mean()
    deviation = series.rolling(window=length, min_periods=length).std()
    upper = mid + std * deviation
    lower = mid - std * deviation
    return pd.DataFrame({"mid": mid, "upper": upper, "lower": lower})


def compute_indicators(rows: List[PriceRow]) -> List[Dict[str, Optional[float]]]:
    if not rows:
        return []

    df = pd.DataFrame(
        [
            {
                "date": row.date,
                "open": row.open,
                "high": row.high,
                "low": row.low,
                "close": row.close,
                "volume": row.volume,
            }
            for row in rows
        ]
    )

    sma20 = _sma(df["close"], 20)
    sma50 = _sma(df["close"], 50)
    ema12 = _ema(df["close"], 12)
    ema26 = _ema(df["close"], 26)
    rsi14 = _rsi(df["close"], 14)
    macd = _macd(df["close"], fast=12, slow=26, signal=9)
    bbands = _bbands(df["close"], length=20, std=2.0)

    def as_optional(value):
        if pd.isna(value):
            return None
        return float(value)

    indicators = []
    for idx, row in df.iterrows():
        macd_row = macd.iloc[idx]
        bb_row = bbands.iloc[idx]
        indicators.append(
            {
                "date": str(row["date"]),
                "sma20": as_optional(sma20.iloc[idx]),
                "sma50": as_optional(sma50.iloc[idx]),
                "ema12": as_optional(ema12.iloc[idx]),
                "ema26": as_optional(ema26.iloc[idx]),
                "rsi14": as_optional(rsi14.iloc[idx]),
                "macd": as_optional(macd_row["macd"]),
                "macd_signal": as_optional(macd_row["signal"]),
                "macd_hist": as_optional(macd_row["hist"]),
                "bb_mid": as_optional(bb_row["mid"]),
                "bb_upper": as_optional(bb_row["upper"]),
                "bb_lower": as_optional(bb_row["lower"]),
            }
        )
    return indicators
