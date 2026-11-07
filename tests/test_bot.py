import numpy as np, pandas as pd
from bot.strategy import signal, vbreak_signal, trendhold_signal, Strategy, DAY_MS
from bot.risk import Risk
from bot.broker import PaperBroker
from bot.backtest import run
from bot.presets import PRESETS, TREND_PRESETS


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


def _vb_df():
    # 0일차: 100→110 (변동폭 10). 1일차 시가 105 → 매수선 105+0.5*10 = 110
    c0 = np.linspace(100, 110, 24)
    day0 = pd.DataFrame({"open": c0, "high": c0, "low": c0, "close": c0})
    day1 = pd.DataFrame({"open": 105.0, "high": 105.0, "low": 105.0, "close": 105.0}, index=range(24))
    day1.loc[1, "close"] = 109.0   # 매수선 아래
    day1.loc[2, "close"] = 111.0   # 매수선 돌파
    df = pd.concat([day0, day1], ignore_index=True)
    df["ts"] = np.arange(len(df)) * (DAY_MS // 24)
    return df


def test_vbreak_signals():
    df = _vb_df()
    assert vbreak_signal(df.iloc[:25]) == "sell"   # 새 날의 첫 봉 → 정리
    assert vbreak_signal(df.iloc[:26]) == "hold"   # 109 < 110
    assert vbreak_signal(df.iloc[:27]) == "buy"    # 111 > 110
    assert vbreak_signal(df.iloc[:27], day_ma=5) == "hold"  # 5일 평균 만들 데이터 부족


def test_vbreak_backtest_one_buy_per_day():
    rng = np.random.default_rng(5)
    n = 24 * 40
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    df = pd.DataFrame({"ts": np.arange(n) * (DAY_MS // 24), "open": np.r_[c[0], c[:-1]],
                       "high": c * 1.003, "low": c * 0.997, "close": c})
    for name in ("vbreak", "vbreak_f"):
        res = run(df, *PRESETS[name])
        buys = [df["ts"][t["i"]] // DAY_MS for t in res["trade_list"] if t["side"] == "buy"]
        assert len(buys) == len(set(buys))


def test_fetch_retries_on_rate_limit(monkeypatch):
    import ccxt
    from bot import main as m
    monkeypatch.setattr(m.time, "sleep", lambda s: None)

    class Ex:
        calls = 0
        def fetch_ohlcv(self, sym, tf, **kw):
            Ex.calls += 1
            if Ex.calls <= 2:
                raise ccxt.RateLimitExceeded("429")
            return [[1, 1, 1, 1, 1, 1]]

    df = m.fetch(Ex(), "BTC/KRW", "1h", 100)
    assert len(df) == 1 and Ex.calls == 3


def test_slippage_makes_results_worse():
    a, b = PaperBroker(cash=100_000), PaperBroker(cash=100_000, slippage=0.001)
    for x in (a, b):
        x.buy(100, 50_000); x.sell_all(100)
    assert b.cash < a.cash
    df = series(n=800, seed=7)
    assert run(df, *PRESETS["base"], slippage=0.002)["return_pct"] < run(df, *PRESETS["base"])["return_pct"]


def test_trendhold_signal():
    up = pd.DataFrame({"close": np.linspace(100, 200, 150)})
    dn = pd.DataFrame({"close": np.linspace(200, 100, 150)})
    assert trendhold_signal(up, 100, 0.02) == "buy"
    assert trendhold_signal(dn, 100, 0.02) == "sell"
    assert trendhold_signal(up.iloc[:50], 100) == "hold"   # 데이터 부족
    flat = pd.DataFrame({"close": [100.0] * 150})
    assert trendhold_signal(flat, 100, 0.02) == "hold"      # 평균선 근처에서는 상태 유지


def test_stop_loss_zero_disables_stop():
    assert Risk(stop_loss=0.0, take_profit=0.0).exit_reason(100, 1) is None


def test_trendhold_avoids_crash_with_few_trades():
    rng = np.random.default_rng(11)
    n_up, n_dn = 400, 250
    drift = np.r_[np.full(n_up, 0.003), np.full(n_dn, -0.004)]
    c = 100 * np.exp(np.cumsum(drift + rng.normal(0, 0.01, n_up + n_dn)))
    df = pd.DataFrame({"ts": np.arange(len(c)) * DAY_MS, "close": c})
    res = run(df, *TREND_PRESETS["trend100"], warmup=105, slippage=0.001)
    assert res["trades"] <= 6
    assert res["max_drawdown_pct"] > res["buy_hold_mdd_pct"]   # 보유보다 낙폭이 작아야 함
    assert res["return_pct"] > res["buy_hold_pct"]             # 급락 전에 빠져나와 이득
