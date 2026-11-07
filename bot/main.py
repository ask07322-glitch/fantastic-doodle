"""실행: python -m bot.main [--live] [--backtest] [--compare]"""
from __future__ import annotations
import argparse, csv, time, datetime as dt
import ccxt
import pandas as pd
from .backtest import run as backtest
from .broker import PaperBroker, LiveBroker
from .presets import PRESETS
from .strategy import day_of, signal_for


def fetch(ex, symbol, tf, limit=200) -> pd.DataFrame:
    """limit개 캔들. 200개 넘으면 여러 번 나눠서 가져옵니다."""
    if limit <= 200:
        rows = ex.fetch_ohlcv(symbol, tf, limit=limit)
    else:
        step = ex.parse_timeframe(tf) * 1000
        since = ex.milliseconds() - limit * step
        rows = []
        while len(rows) < limit:
            part = ex.fetch_ohlcv(symbol, tf, since=since, limit=200)
            if not part:
                break
            rows += [r for r in part if not rows or r[0] > rows[-1][0]]
            since = part[-1][0] + step
            if part[-1][0] >= ex.milliseconds() - step:
                break
    return pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exchange", default="upbit")
    ap.add_argument("--symbol", default="BTC/KRW")
    ap.add_argument("--timeframe", default="1h")
    ap.add_argument("--strategy", default="improved", choices=list(PRESETS),
                    help="base=처음 버전, improved=개선 버전")
    ap.add_argument("--interval", type=int, default=30, help="폴링 간격(초)")
    ap.add_argument("--backtest", action="store_true", help="백테스트만 실행 (그림 저장)")
    ap.add_argument("--compare", action="store_true", help="여러 코인에서 base vs improved 비교")
    ap.add_argument("--candles", type=int, default=1000, help="백테스트에 쓸 캔들 개수")
    ap.add_argument("--live", action="store_true", help="실거래 (기본은 모의매매)")
    a = ap.parse_args()

    pub = getattr(ccxt, a.exchange)({"enableRateLimit": True})
    st, risk = PRESETS[a.strategy]

    if a.compare:
        from .compare import compare
        compare(fetch, pub, max(a.candles, 2000))
        return

    if a.backtest:
        from . import chart
        df = fetch(pub, a.symbol, a.timeframe, a.candles)
        res = backtest(df, st, risk)
        print(f"[{a.strategy}] 데이터 {len(df)}개 | 봇 {res['return_pct']:+.2f}% | 그냥 들고 있기 "
              f"{res['buy_hold_pct']:+.2f}% | 최대 하락 {res['max_drawdown_pct']:.2f}% | 거래 {res['trades']}번")
        ma = st.kind == "ma"
        path = chart.save(df, res, st.fast if ma else 0, st.slow if ma else 0,
                          f"{a.symbol} {a.timeframe} 백테스트 ({a.strategy})",
                          "backtest.png", st.trend)
        print("그림 저장:", path)
        chart.open_file(path)
        return

    if a.live:
        if input("실거래 모드입니다. 실제 돈이 거래됩니다. 'YES' 입력: ") != "YES":
            return
        broker = LiveBroker(a.exchange, a.symbol)
    else:
        broker = PaperBroker()
    print(f"[start] {a.exchange} {a.symbol} {a.timeframe} strategy={a.strategy} "
          f"mode={'LIVE' if a.live else 'PAPER'}")

    bpd = 86400 / pub.parse_timeframe(a.timeframe)
    if st.kind == "vbreak" and bpd < 2:
        raise SystemExit("변동성 돌파는 1일봉 미만 시간봉(예: 1h, 4h)에서만 쓸 수 있습니다.")
    need = st.history_bars(bpd)
    day, day_start_eq, halted = dt.date.today(), None, False
    last_candle, peak, bars_since_exit, buy_day = None, 0.0, 10**6, None
    while True:
        try:
            df = fetch(pub, a.symbol, a.timeframe, max(200, need))
            price = float(df["close"].iloc[-1])
            eq = broker.equity(price)
            if dt.date.today() != day or day_start_eq is None:
                day, day_start_eq, halted = dt.date.today(), eq, False
            if not halted and eq < day_start_eq * (1 - risk.max_daily_loss):
                halted = True
                print("[halt] 일일 최대 손실 도달 — 오늘 신규 매수 중단")

            new_candle = df["ts"].iloc[-2] != last_candle
            if new_candle:
                bars_since_exit += 1
            if broker.qty * price > 1000:  # 보유 중: 손절/추적손절은 매 폴링 확인
                peak = max(peak, price)
                why = risk.exit_reason(broker.entry, price, peak)
                if why or (new_candle and signal_for(df, st) == "sell"):
                    broker.sell_all(price)
                    bars_since_exit = 0
                    print(f"[sell] {price:,.0f} {why or 'signal'} equity={broker.equity(price):,.0f}")
                    _log("sell", price)
            elif (not halted and (new_candle or st.one_per_day) and bars_since_exit > st.cooldown
                  and (not st.one_per_day or day_of(df["ts"].iloc[-1]) != buy_day)):
                # 변동성 돌파는 봉 중간에 돌파할 수 있어 매 폴링마다 확인
                if signal_for(df, st) == "buy":
                    if broker.buy(price, risk.buy_budget(broker.cash)):
                        peak = price
                        buy_day = day_of(df["ts"].iloc[-1])
                        print(f"[buy] {price:,.0f}")
                        _log("buy", price)
            last_candle = df["ts"].iloc[-2]
        except (ccxt.NetworkError, ccxt.ExchangeNotAvailable) as e:
            print("[warn] 네트워크 오류, 재시도:", e)
        time.sleep(a.interval)


def _log(side, price):
    with open("trades.csv", "a", newline="") as f:
        csv.writer(f).writerow([dt.datetime.now().isoformat(), side, price])


if __name__ == "__main__":
    main()
