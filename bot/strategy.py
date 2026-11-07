"""전략: 이동평균 골든/데드크로스 + RSI 과열 필터."""
from __future__ import annotations
import pandas as pd


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, float("nan"))
    out = 100 - 100 / (1 + rs)
    return out.fillna(50.0)


def signal(df: pd.DataFrame, fast: int = 10, slow: int = 30,
           rsi_max: float = 70.0) -> str:
    """마지막 *확정된* 캔들 기준 신호: 'buy' | 'sell' | 'hold'.

    df: 'close' 컬럼을 가진 캔들 DataFrame (마지막 행은 진행 중 캔들일 수 있어 제외).
    """
    if len(df) < slow + 3:
        return "hold"
    c = df["close"].iloc[:-1]  # 진행 중 캔들 제외
    f = c.rolling(fast).mean()
    s = c.rolling(slow).mean()
    crossed_up = f.iloc[-2] <= s.iloc[-2] and f.iloc[-1] > s.iloc[-1]
    crossed_dn = f.iloc[-2] >= s.iloc[-2] and f.iloc[-1] < s.iloc[-1]
    if crossed_up and rsi(c).iloc[-1] < rsi_max:
        return "buy"
    if crossed_dn:
        return "sell"
    return "hold"
