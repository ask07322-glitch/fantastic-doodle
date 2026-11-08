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


class FakeEx:
    id = "upbit"
    bal = {}
    def __init__(self, cfg): pass
    def fetch_balance(self): return {k: {"free": v} for k, v in FakeEx.bal.items()}
    def create_order(self, sym, typ, side, amount, price=None, params=None):
        if side == "buy":   # 업비트식: amount=KRW 금액, 가격 100원, 수수료 무시
            FakeEx.bal["KRW"] -= amount
            FakeEx.bal["BTC"] += amount / 100
        else:
            FakeEx.bal["BTC"] -= amount
            FakeEx.bal["KRW"] += amount * 100


def test_live_broker_sells_only_what_bot_bought(monkeypatch, tmp_path):
    import ccxt
    from bot import broker as bm
    monkeypatch.setattr(ccxt, "fakeex", FakeEx, raising=False)
    monkeypatch.setattr(bm.time, "sleep", lambda s: None)
    monkeypatch.setenv("API_KEY", "x"); monkeypatch.setenv("API_SECRET", "y")
    FakeEx.bal = {"KRW": 100_000.0, "BTC": 5.0}   # 원래 BTC 5개 보유 중
    b = bm.LiveBroker("fakeex", "BTC/KRW", str(tmp_path / "state.json"))
    assert b.qty == 0                      # 원래 보유분은 봇의 포지션이 아님
    assert b.buy(100, 10_000) and abs(b.qty - 100) < 1e-6   # 10,000원어치=100개
    b2 = bm.LiveBroker("fakeex", "BTC/KRW", str(tmp_path / "state.json"))  # 재시작해도 기억
    assert abs(b2.qty - 100) < 1e-6
    assert b2.sell_all(100)
    assert abs(FakeEx.bal["BTC"] - 5.0) < 1e-6   # 원래 보유분은 그대로
    assert b2.qty == 0


def test_status_runs(capsys):
    from bot.status import status
    c = np.r_[np.linspace(100, 200, 200), np.linspace(200, 120, 60)]
    df = pd.DataFrame({"ts": np.arange(len(c)) * DAY_MS, "close": c})
    status(lambda ex, s, tf, n: df, None, coins=["BTC/KRW"])
    out = capsys.readouterr().out
    assert "trend100" in out and "trend200" in out and "BTC/KRW" in out


def test_telegram_send_and_no_token_leak(monkeypatch, capsys):
    from bot import notify
    sent = {}
    class R:
        status_code = 200
    monkeypatch.setattr(notify.requests, "post", lambda url, json, timeout: sent.update(url=url, **json) or R())
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "SECRET123"); monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    assert notify.Telegram().send("hi") and sent["chat_id"] == "42" and sent["text"] == "hi"

    monkeypatch.setattr(notify.time, "sleep", lambda s: None)
    def boom(url, json, timeout): raise RuntimeError("failed for " + url)
    monkeypatch.setattr(notify.requests, "post", boom)
    assert notify.Telegram().send("hi") is False
    assert "SECRET123" not in capsys.readouterr().out      # 토큰이 화면에 나오면 안 됨


def test_telegram_disabled_without_config(monkeypatch):
    from bot import notify
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False); monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert notify.Telegram().send("x") is False


def test_load_env(tmp_path, monkeypatch):
    from bot import notify
    f = tmp_path / ".env"; f.write_text("# c\nFOO_X=bar\nBAZ_X = \"q\"\n")
    monkeypatch.delenv("FOO_X", raising=False); monkeypatch.delenv("BAZ_X", raising=False)
    notify.load_env(str(f))
    import os
    assert os.environ["FOO_X"] == "bar" and os.environ["BAZ_X"] == "q"


def test_check_signals_alerts_only_on_change(tmp_path):
    from bot.signals import check_signals
    up = np.linspace(100, 300, 320)
    down = np.r_[up, np.linspace(300, 150, 60)]
    mk = lambda c: pd.DataFrame({"ts": np.arange(len(c)) * DAY_MS, "close": c})
    msgs, state = [], str(tmp_path / "s.json")
    kw = dict(coins=["BTC/KRW"], state_path=state)
    check_signals(lambda e, s, tf, n: mk(up), None, msgs.append, **kw)
    assert len(msgs) == 1 and "시작" in msgs[0]            # 첫 실행: 기준 저장 + 시작 안내
    check_signals(lambda e, s, tf, n: mk(up), None, msgs.append, **kw)
    assert len(msgs) == 1                                   # 변경 없으면 조용
    alerts = check_signals(lambda e, s, tf, n: mk(down), None, msgs.append, **kw)
    assert alerts and "매도 신호" in msgs[-1]               # 보유→현금으로 바뀌면 알림
    check_signals(lambda e, s, tf, n: mk(down), None, msgs.append, **kw)
    assert len(msgs) == 2                                   # 같은 신호는 반복 알림 없음


def test_telegram_retries_on_timeout_and_explains(monkeypatch):
    import requests
    from bot import notify
    monkeypatch.setattr(notify.time, "sleep", lambda s: None)
    calls = {"n": 0}
    class R:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"result": [{"message": {"chat": {"id": 7, "first_name": "나"}}}]}
    def flaky(url, timeout):
        calls["n"] += 1
        if calls["n"] < 3:
            raise requests.ReadTimeout("slow")
        return R()
    monkeypatch.setattr(notify.requests, "get", flaky)
    assert notify.find_chat_ids("TOK") == [(7, "나")] and calls["n"] == 3   # 두 번 느려도 세 번째에 성공
    assert "토큰 문제가 아닙니다" in notify.explain(requests.ReadTimeout("x"))


def _auto_env(monkeypatch, tmp_path):
    import ccxt
    from bot import broker as bm
    monkeypatch.setattr(ccxt, "fakeex", FakeEx, raising=False)
    monkeypatch.setattr(bm.time, "sleep", lambda s: None)
    monkeypatch.setenv("API_KEY", "x"); monkeypatch.setenv("API_SECRET", "y")
    FakeEx.bal = {"KRW": 100_000.0, "BTC": 0.0}
    make = lambda sym: bm.LiveBroker("fakeex", sym, str(tmp_path / "state.json"))
    mk = lambda c: pd.DataFrame({"ts": np.arange(len(c)) * DAY_MS, "close": c})
    return make, mk, np.linspace(100, 300, 320), np.linspace(300, 100, 320), str(tmp_path / "auto.json")


def test_auto_dry_run_never_orders(monkeypatch, tmp_path):
    from bot.auto import run_auto
    make, mk, up, dn, sp = _auto_env(monkeypatch, tmp_path)
    msgs = []
    kw = dict(coins=["BTC/KRW"], preset="trend200", budget=30000, max_total=100000, live=False, state_path=sp)
    run_auto(lambda e, s, tf, n: mk(dn), None, msgs.append, None, **kw)   # 기준 저장
    out = run_auto(lambda e, s, tf, n: mk(up), None, msgs.append, None, **kw)
    assert out and "모의" in out[0] and FakeEx.bal["KRW"] == 100_000.0


def test_auto_live_buy_then_sell_and_caps(monkeypatch, tmp_path):
    from bot.auto import run_auto
    make, mk, up, dn, sp = _auto_env(monkeypatch, tmp_path)
    msgs = []
    kw = dict(coins=["BTC/KRW"], preset="trend200", budget=30000, max_total=20000, live=True, state_path=sp)
    run_auto(lambda e, s, tf, n: mk(dn), None, msgs.append, make, **kw)   # 첫 실행: 주문 없음
    assert FakeEx.bal["KRW"] == 100_000.0
    run_auto(lambda e, s, tf, n: mk(up), None, msgs.append, make, **kw)   # 매수 신호
    assert FakeEx.bal["KRW"] == 80_000.0          # 총액 상한 2만원이 1회 한도 3만원보다 우선
    run_auto(lambda e, s, tf, n: mk(dn), None, msgs.append, make, **kw)   # 매도 신호
    assert FakeEx.bal["KRW"] == 100_000.0 and FakeEx.bal["BTC"] < 1e-9


def test_auto_order_failure_keeps_state_for_retry(monkeypatch, tmp_path):
    import json
    from bot.auto import run_auto
    make, mk, up, dn, sp = _auto_env(monkeypatch, tmp_path)
    msgs = []
    kw = dict(coins=["BTC/KRW"], preset="trend200", budget=30000, max_total=100000, live=True, state_path=sp)
    run_auto(lambda e, s, tf, n: mk(dn), None, msgs.append, make, **kw)
    def boom(*a, **k): raise RuntimeError("down")
    monkeypatch.setattr(FakeEx, "create_order", boom)
    out = run_auto(lambda e, s, tf, n: mk(up), None, msgs.append, make, **kw)
    assert "주문 실패" in out[0]
    assert json.load(open(sp))["BTC/KRW"]["state"] == "out"   # 상태 유지 → 다음 실행 때 재시도


def test_explain_api_error():
    import ccxt
    from bot.apicheck import explain_api_error
    assert "IP" in explain_api_error(Exception('{"error":{"name":"no_authorization_ip"}}'))
    assert "권한" in explain_api_error(Exception("out_of_scope"))
    assert "올바르지" in explain_api_error(ccxt.AuthenticationError("x"))


def test_fetch_retries_on_network_error_after_wake(monkeypatch):
    import ccxt
    from bot import main as m
    monkeypatch.setattr(m.time, "sleep", lambda s: None)
    class Ex2:
        calls = 0
        def fetch_ohlcv(self, sym, tf, **kw):
            Ex2.calls += 1
            if Ex2.calls <= 3:
                raise ccxt.RequestTimeout("network not ready")   # 절전 복귀 직후 인터넷 미연결
            return [[1, 1, 1, 1, 1, 1]]
    assert len(m.fetch(Ex2(), "BTC/KRW", "1d", 100)) == 1 and Ex2.calls == 4


def test_trade_stats_and_kelly():
    from bot.stats import trade_stats, kelly_fraction, suggest_position
    s = trade_stats([10, -5, 20, -5, -5])          # 승률 40%, 평균이익 15, 평균손실 5
    assert s["n"] == 5 and abs(s["win_rate"] - 40) < 1e-9
    assert abs(s["payoff"] - 3.0) < 1e-9 and abs(s["expectancy"] - 3.0) < 1e-9   # 0.4*15 - 0.6*5
    assert abs(kelly_fraction(40, 3.0) - 0.2) < 1e-9                              # 0.4 - 0.6/3
    assert kelly_fraction(30, 1.0) == 0.0                                          # 기대값 마이너스면 0
    f, note = suggest_position(s)                                                 # 표본 부족이면 0 + 경고
    assert f == 0.0 and "표본" in note


def test_backtest_reports_stats():
    res = run(series(n=800, seed=7), *PRESETS["base"])
    assert res["stats"]["n"] == res["trades"]


def test_paper_mode_records_virtual_pnl(monkeypatch, tmp_path):
    import csv
    from bot.auto import run_auto
    make, mk, up, dn, sp = _auto_env(monkeypatch, tmp_path)
    log = str(tmp_path / "paper.csv")
    kw = dict(coins=["BTC/KRW"], preset="trend200", budget=30000, max_total=100000, live=False,
              state_path=sp, log_path=log, slippage=0.001)
    run_auto(lambda e, s, tf, n: mk(dn), None, lambda m: None, None, **kw)   # 기준
    run_auto(lambda e, s, tf, n: mk(up), None, lambda m: None, None, **kw)   # 가상 매수
    run_auto(lambda e, s, tf, n: mk(dn), None, lambda m: None, None, **kw)   # 가상 매도 → 기록
    rows = list(csv.DictReader(open(log, encoding="utf-8")))
    assert len(rows) == 1 and float(rows[0]["entry"]) > 0 and "pnl_pct" in rows[0]


def test_sweep_runs_and_reports(capsys):
    from bot.sweep import sweep
    DAY = 86400000
    def fake(ex, sym, tf, n):
        rng = np.random.default_rng(abs(hash(sym)) % 1000)
        c = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.02, 1500)))
        return pd.DataFrame({"ts": np.arange(1500) * DAY, "close": c})
    df = sweep(fake, None, 1500, coins=["A", "B"], progress=lambda s: None)
    out = capsys.readouterr().out
    assert df is not None and len(df) == 48 and "과적합 점검" in out and "순위상관" in out
