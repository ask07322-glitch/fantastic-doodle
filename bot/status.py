"""지금 각 코인이 평균선 위(보유)인지 아래(현금)인지 한눈에 보여주기."""
from __future__ import annotations
import pandas as pd
from .compare import COINS
from .presets import TREND_PRESETS
from .strategy import trendhold_signal

LABEL = {"buy": "보유(평균선 위)", "sell": "현금(평균선 아래)", "hold": "중립(직전 상태 유지)"}


def status(fetch, ex, coins=COINS, presets=TREND_PRESETS) -> None:
    need = max(s.trend for s, _ in presets.values()) + 30
    print("큰 흐름 따라 보유(일봉) — 어제 확정 종가 기준 현재 상태")
    for sym in coins:
        try:
            df = fetch(ex, sym, "1d", need)
        except Exception as e:
            print(f"\n{sym}: 건너뜀 ({type(e).__name__})")
            continue
        conf = df["close"].iloc[:-1]
        day = (pd.to_datetime(df["ts"].iloc[-2], unit="ms") + pd.Timedelta(hours=9)).date()
        print(f"\n{sym}  현재가 {df['close'].iloc[-1]:,.0f}원  (확정 종가 기준일 {day})")
        for name, (st, _) in presets.items():
            ma = float(conf.rolling(st.trend).mean().iloc[-1])
            p = float(conf.iloc[-1])
            sig = trendhold_signal(df, st.trend, st.band)
            print(f"  {name:<9}{LABEL[sig]:<16} 종가 {p:,.0f} / {st.trend}일 평균 {ma:,.0f} "
                  f"({(p / ma - 1) * 100:+.1f}%)  매수선 {ma * (1 + st.band):,.0f} · 매도선 {ma * (1 - st.band):,.0f}")
    print("\n※ 보유=봇이 샀을 상태, 현금=팔았을 상태, 중립=평균선 ±2% 안이라 직전 상태 유지. 투자 권유가 아닙니다.")
