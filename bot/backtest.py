"""과거 데이터 백테스트 (전략을 실거래 전에 검증)."""
from __future__ import annotations
import pandas as pd
from .broker import PaperBroker
from .risk import Risk
from .strategy import signal


def run(df: pd.DataFrame, risk: Risk | None = None, fast=10, slow=30,
        cash: float = 1_000_000.0) -> dict:
    risk = risk or Risk()
    b = PaperBroker(cash=cash)
    curve = []
    for i in range(slow + 4, len(df) + 1):
        window = df.iloc[:i]
        price = float(window["close"].iloc[-1])
        if b.qty > 0:
            why = risk.exit_reason(b.entry, price)
            if why or signal(window, fast, slow) == "sell":
                b.sell_all(price)
        elif signal(window, fast, slow) == "buy":
            b.buy(price, risk.buy_budget(b.cash))
        curve.append(b.equity(price))
    last = float(df["close"].iloc[-1])
    eq = pd.Series(curve)
    mdd = float(((eq / eq.cummax()) - 1).min()) if len(eq) else 0.0
    return {
        "final_equity": b.equity(last),
        "return_pct": (b.equity(last) / cash - 1) * 100,
        "buy_hold_pct": (last / float(df["close"].iloc[0]) - 1) * 100,
        "max_drawdown_pct": mdd * 100,
        "trades": sum(1 for t in b.log if t[0] == "sell"),
    }
