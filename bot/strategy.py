"""전략: 이동평균 골든/데드크로스 + RSI 과열 필터 + (선택) 큰 추세 필터."""
from __future__ import annotations
from dataclasses import dataclass
import pandas as pd


DAY_MS = 86_400_000  # 업비트 일봉 기준(09:00 KST = 00:00 UTC)


@dataclass(frozen=True)
class Strategy:
    kind: str = "ma"     # "ma" 이동평균 | "vbreak" 변동성 돌파
    k: float = 0.5       # vbreak: 어제 변동폭의 k배를 오늘 시가에 더한 가격이 매수선
    day_ma: int = 0      # vbreak: N일 평균 위일 때만 매수 (0이면 끔)
    fast: int = 10
    slow: int = 30
    rsi_max: float = 70.0
    trend: int = 0       # 0이면 끔. N>0: 가격이 N봉 평균 위 + 그 평균이 오르는 중일 때만 매수
    cooldown: int = 0    # 매도 후 N봉 동안 재매수 금지 (잦은 매매/수수료 줄이기)


    @property
    def one_per_day(self) -> bool:
        return self.kind == "vbreak"

    def history_bars(self, bars_per_day: float) -> int:
        """실시간 실행 때 필요한 최소 캔들 수."""
        if self.kind == "vbreak":
            return int((self.day_ma + 3) * bars_per_day) + 5
        return max(self.slow, self.trend + 6) + 10


def day_of(ts) -> int:
    return int(ts // DAY_MS)


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


def vbreak_signal(df: pd.DataFrame, k: float = 0.5, day_ma: int = 0) -> str:
    """변동성 돌파. 마지막 행(현재 봉)의 종가를 현재가로 본다.

    - 새 날의 첫 봉이면 'sell' (보유 중이면 전날 포지션 정리)
    - 현재가 > 오늘 시가 + k * 어제 (고가-저가) 이면 'buy'
    df에는 ts(ms), open, high, low, close 컬럼이 필요하다. 1일봉 미만 시간봉에서만 의미가 있다.
    """
    if len(df) < 3:
        return "hold"
    days = df["ts"].to_numpy() // DAY_MS
    today = days[-1]
    keep = days >= today - (day_ma + 2)
    df, days = df[keep], days[keep]
    if len(days) < 2:
        return "hold"
    if days[-2] != today:
        return "sell"
    prev = df[days == today - 1]
    if prev.empty:
        return "hold"
    target = float(df.loc[days == today, "open"].iloc[0]) + k * float(prev["high"].max() - prev["low"].min())
    price = float(df["close"].iloc[-1])
    if price <= target:
        return "hold"
    if day_ma:
        closes = df.groupby(days)["close"].last().iloc[:-1].tail(day_ma)
        if len(closes) < day_ma or price <= float(closes.mean()):
            return "hold"
    return "buy"


def signal_for(df: pd.DataFrame, s: Strategy) -> str:
    if s.kind == "vbreak":
        return vbreak_signal(df, s.k, s.day_ma)
    return signal(df, s.fast, s.slow, s.rsi_max, s.trend)
