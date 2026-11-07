"""전략: 이동평균 골든/데드크로스 + RSI 과열 필터 + (선택) 큰 추세 필터."""
from __future__ import annotations
from dataclasses import dataclass
import pandas as pd


@dataclass(frozen=True)
class Strategy:
    fast: int = 10
    slow: int = 30
    rsi_max: float = 70.0
    trend: int = 0       # 0이면 끔. N>0: 가격이 N봉 평균 위 + 그 평균이 오르는 중일 때만 매수
    cooldown: int = 0    # 매도 후 N봉 동안 재매수 금지 (잦은 매매/수수료 줄이기)


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, float("nan"))
    return (100 - 100 / (1 + rs)).fillna(50.0)


def signal(df: pd.DataFrame, fast: int = 10, slow: int = 30,
           rsi_max: float = 70.0, trend: int = 0) -> str:
    """마지막 *확정된* 캔들 기준 신호: 'buy' | 'sell' | 'hold'.

    df: 'close' 컬럼을 가진 캔들 DataFrame (마지막 행은 진행 중 캔들이라 제외).
    """
    if len(df) < max(slow, trend + 6) + 3:
        return "hold"
    c = df["close"].iloc[:-1]
    f = c.rolling(fast).mean()
    s = c.rolling(slow).mean()
    crossed_up = f.iloc[-2] <= s.iloc[-2] and f.iloc[-1] > s.iloc[-1]
    crossed_dn = f.iloc[-2] >= s.iloc[-2] and f.iloc[-1] < s.iloc[-1]
    if crossed_up and rsi(c).iloc[-1] < rsi_max:
        if trend:
            t = c.rolling(trend).mean()
            if not (c.iloc[-1] > t.iloc[-1] and t.iloc[-1] > t.iloc[-6]):
                return "hold"  # 큰 흐름이 하락/횡보면 쉰다
        return "buy"
    if crossed_dn:
        return "sell"
    return "hold"


def signal_for(df: pd.DataFrame, s: Strategy) -> str:
    return signal(df, s.fast, s.slow, s.rsi_max, s.trend)
