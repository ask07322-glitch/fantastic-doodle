import numpy as np, pandas as pd
from bot.strategy import signal
from bot.risk import Risk
from bot.broker import PaperBroker
from bot.backtest import run
from bot.presets import PRESETS


def series(n=300, seed=1):
    rng = np.random.default_rng(seed)
    price = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, n)))
    return pd.DataFrame({"close": price})


def test_signal_buy_on_golden_cross():
    # 하락 후 급반등 → 골든크로스
    close = list(np.linspace(100, 80, 40)) + list(np.linspace(80, 110, 25))
    seen = {signal(pd.DataFrame({"close": close[:i]}), 5, 20) for i in range(25, len(close) + 1)}
    assert "buy" in seen


def test_signal_hold_when_short():
    assert signal(pd.DataFrame({"close": [1, 2, 3]})) == "hold"


def test_risk_exit():
    r = Risk()
    assert r.exit_reason(100, 96) == "stop_loss"
    assert r.exit_reason(100, 107) == "take_profit"
    assert r.exit_reason(100, 101) is None
    assert r.buy_budget(10_000) == 0.0


def test_paper_roundtrip_applies_fees():
    b = PaperBroker(cash=100_000)
    assert b.buy(100, 50_000)
    assert not b.buy(100, 10_000)  # 이미 보유
    b.sell_all(100)
    assert b.cash < 100_000  # 수수료만큼 손실


def test_backtest_runs():
    res = run(series())
    assert {"return_pct", "max_drawdown_pct", "trades"} <= res.keys()


def test_trailing_stop_and_no_take_profit():
    r = Risk(stop_loss=0.03, take_profit=0.0, trailing_start=0.03, trailing_gap=0.02)
    assert r.exit_reason(100, 110, 110) is None          # 익절 없이 계속 보유
    assert r.exit_reason(100, 107.7, 110) == "trailing"  # 최고점 110에서 2%+ 하락
    assert r.exit_reason(100, 102, 102) is None          # 아직 추적 시작 전


def test_trend_filter_blocks_buy_in_downtrend():
    # 긴 하락 후 짧은 반등: 골든크로스가 나도 큰 추세 필터가 매수를 막아야 함
    close = list(np.linspace(200, 100, 200)) + list(np.linspace(100, 108, 20))
    base = {signal(pd.DataFrame({"close": close[:i]}), 5, 20) for i in range(150, len(close) + 1)}
    filt = {signal(pd.DataFrame({"close": close[:i]}), 5, 20, trend=100) for i in range(150, len(close) + 1)}
    assert "buy" in base and "buy" not in filt


def test_both_presets_run_and_improved_trades_less():
    df = series(n=800, seed=7)
    b, i = run(df, *PRESETS["base"]), run(df, *PRESETS["improved"])
    assert i["trades"] <= b["trades"]
    assert i["max_drawdown_pct"] > -50
