"""과거 데이터 백테스트 (전략을 실거래 전에 검증)."""
from __future__ import annotations
import pandas as pd
from .broker import PaperBroker
from .risk import Risk
from .strategy import Strategy, signal_for


def run(df: pd.DataFrame, strategy: Strategy | None = None, risk: Risk | None = None,
        cash: float = 1_000_000.0) -> dict:
    st, risk = strategy or Strategy(), risk or Risk()
    b = PaperBroker(cash=cash)
    curve, idx, trades = [], [], []
    peak, last_exit = 0.0, -10**9
    for i in range(st.slow + 4, len(df) + 1):
        window = df.iloc[:i]
        price = float(window["close"].iloc[-1])
        if b.qty > 0:
            peak = max(peak, price)
            why = risk.exit_reason(b.entry, price, peak)
            if why or signal_for(window, st) == "sell":
                entry = b.entry
                b.sell_all(price)
                last_exit = i
                trades.append({"i": i - 1, "side": "sell", "price": price,
                               "reason": why or "signal",
                               "pnl_pct": (price / entry - 1) * 100})
        elif i - last_exit > st.cooldown and signal_for(window, st) == "buy":
            if b.buy(price, risk.buy_budget(b.cash)):
                peak = price
                trades.append({"i": i - 1, "side": "buy", "price": price})
        curve.append(b.equity(price))
        idx.append(i - 1)
    last = float(df["close"].iloc[0 if not len(idx) else idx[0]])
    end = float(df["close"].iloc[-1])
    eq = pd.Series(curve)
    mdd = float(((eq / eq.cummax()) - 1).min()) if len(eq) else 0.0
    return {
        "final_equity": b.equity(end),
        "return_pct": (b.equity(end) / cash - 1) * 100,
        "buy_hold_pct": (end / last - 1) * 100,   # 같은 시작 시점부터 그냥 들고 있기
        "max_drawdown_pct": mdd * 100,
        "trades": sum(1 for t in b.log if t[0] == "sell"),
        "trade_list": trades,
        "equity_curve": curve,
        "equity_index": idx,
        "start_cash": cash,
    }
