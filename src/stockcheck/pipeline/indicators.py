from typing import Dict, List, Optional

import pandas as pd
import pandas_ta as ta

from .models import PriceRow


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

    sma20 = ta.sma(df["close"], length=20)
    sma50 = ta.sma(df["close"], length=50)
    ema12 = ta.ema(df["close"], length=12)
    ema26 = ta.ema(df["close"], length=26)
    rsi14 = ta.rsi(df["close"], length=14)
    macd = ta.macd(df["close"], fast=12, slow=26, signal=9)
    bbands = ta.bbands(df["close"], length=20, std=2.0)

    def as_optional(value):
        if pd.isna(value):
            return None
        return float(value)

    indicators = []
    for idx, row in df.iterrows():
        macd_row = macd.iloc[idx] if macd is not None else None
        bb_row = bbands.iloc[idx] if bbands is not None else None
        indicators.append(
            {
                "date": str(row["date"]),
                "sma20": as_optional(sma20.iloc[idx]) if sma20 is not None else None,
                "sma50": as_optional(sma50.iloc[idx]) if sma50 is not None else None,
                "ema12": as_optional(ema12.iloc[idx]) if ema12 is not None else None,
                "ema26": as_optional(ema26.iloc[idx]) if ema26 is not None else None,
                "rsi14": as_optional(rsi14.iloc[idx]) if rsi14 is not None else None,
                "macd": as_optional(macd_row.get("MACD_12_26_9")) if macd_row is not None else None,
                "macd_signal": as_optional(macd_row.get("MACDs_12_26_9")) if macd_row is not None else None,
                "macd_hist": as_optional(macd_row.get("MACDh_12_26_9")) if macd_row is not None else None,
                "bb_mid": as_optional(bb_row.get("BBM_20_2.0")) if bb_row is not None else None,
                "bb_upper": as_optional(bb_row.get("BBU_20_2.0")) if bb_row is not None else None,
                "bb_lower": as_optional(bb_row.get("BBL_20_2.0")) if bb_row is not None else None,
            }
        )
    return indicators
