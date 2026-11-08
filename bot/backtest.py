"""과거 데이터 백테스트 (전략을 실거래 전에 검증)."""
from __future__ import annotations
import pandas as pd
from .broker import PaperBroker
from .risk import Risk
from .stats import trade_stats
from .strategy import Strategy, day_of, signal_for


def run(df: pd.DataFrame, strategy: Strategy | None = None, risk: Risk | None = None,
        cash: float = 1_000_000.0, warmup: int = 0, slippage: float = 0.0) -> dict:
    st, risk = strategy or Strategy(), risk or Risk()
    b = PaperBroker(cash=cash, slippage=slippage)
    curve, idx, trades = [], [], []
    peak, last_exit, buy_day = 0.0, -10**9, None
    for i in range(max(st.slow + 4, warmup), len(df) + 1):
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
                               "pnl_pct": (price * (1 - slippage) / entry - 1) * 100})
        elif (i - last_exit > st.cooldown
              and (not st.one_per_day or day_of(df["ts"].iat[i - 1]) != buy_day)
              and signal_for(window, st) == "buy"):
            if b.buy(price, risk.buy_budget(b.cash)):
                peak = price
                buy_day = day_of(df["ts"].iat[i - 1]) if st.one_per_day else None
                trades.append({"i": i - 1, "side": "buy", "price": price})
        curve.append(b.equity(price))
        idx.append(i - 1)
    last = float(df["close"].iloc[idx[0] if idx else 0])
    end = float(df["close"].iloc[-1])
    hold = df["close"].iloc[idx[0]:] if idx else df["close"]
    hold_mdd = float((hold / hold.cummax() - 1).min()) * 100
    eq = pd.Series(curve)
    mdd = float(((eq / eq.cummax()) - 1).min()) if len(eq) else 0.0
    return {
        "final_equity": b.equity(end),
        "return_pct": (b.equity(end) / cash - 1) * 100,
        "buy_hold_pct": (end / last - 1) * 100,   # 같은 시작 시점부터 그냥 들고 있기
        "max_drawdown_pct": mdd * 100,
        "buy_hold_mdd_pct": hold_mdd,
        "trades": sum(1 for t in b.log if t[0] == "sell"),
        "trade_list": trades,
        "stats": trade_stats([x["pnl_pct"] for x in trades if x["side"] == "sell"]),
        "equity_curve": curve,
        "equity_index": idx,
        "start_cash": cash,
    }
