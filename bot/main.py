"""실행: python -m bot.main [--live] [--backtest]"""
from __future__ import annotations
import argparse, csv, time, datetime as dt
import ccxt
import pandas as pd
from .backtest import run as backtest
from .broker import PaperBroker, LiveBroker
from .risk import Risk
from .strategy import signal


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
    ap.add_argument("--timeframe", default="15m")
    ap.add_argument("--fast", type=int, default=10)
    ap.add_argument("--slow", type=int, default=30)
    ap.add_argument("--interval", type=int, default=30, help="폴링 간격(초)")
    ap.add_argument("--backtest", action="store_true", help="백테스트만 실행 (그림 저장)")
    ap.add_argument("--candles", type=int, default=500, help="백테스트에 쓸 캔들 개수")
    ap.add_argument("--live", action="store_true", help="실거래 (기본은 모의매매)")
    a = ap.parse_args()

    pub = getattr(ccxt, a.exchange)({"enableRateLimit": True})
    risk = Risk()

    if a.backtest:
        from . import chart
        df = fetch(pub, a.symbol, a.timeframe, a.candles)
        res = backtest(df, risk, a.fast, a.slow)
        print(f"데이터 {len(df)}개 | 봇 {res['return_pct']:+.2f}% | 그냥 들고 있기 "
              f"{res['buy_hold_pct']:+.2f}% | 최대 하락 {res['max_drawdown_pct']:.2f}% | 거래 {res['trades']}번")
        path = chart.save(df, res, a.fast, a.slow,
                          f"{a.symbol} {a.timeframe} 백테스트", "backtest.png")
        print("그림 저장:", path)
        chart.open_file(path)
        return

    if a.live:
        if input("실거래 모드입니다. 실제 돈이 거래됩니다. 'YES' 입력: ") != "YES":
            return
        broker = LiveBroker(a.exchange, a.symbol)
    else:
        broker = PaperBroker()
    print(f"[start] {a.exchange} {a.symbol} {a.timeframe} mode={'LIVE' if a.live else 'PAPER'}")

    day, day_start_eq, halted = dt.date.today(), None, False
    last_candle = None
    while True:
        try:
            df = fetch(pub, a.symbol, a.timeframe)
            price = float(df["close"].iloc[-1])
            eq = broker.equity(price)
            if dt.date.today() != day or day_start_eq is None:
                day, day_start_eq, halted = dt.date.today(), eq, False
            if not halted and eq < day_start_eq * (1 - risk.max_daily_loss):
                halted = True
                print("[halt] 일일 최대 손실 도달 — 오늘 신규 매수 중단")

            if broker.qty * price > 1000:  # 보유 중: 손절/익절은 매 폴링 확인
                why = risk.exit_reason(broker.entry, price)
                new_candle = df["ts"].iloc[-2] != last_candle
                if why or (new_candle and signal(df, a.fast, a.slow) == "sell"):
                    broker.sell_all(price)
                    print(f"[sell] {price:,.0f} {why or 'signal'} equity={broker.equity(price):,.0f}")
                    _log("sell", price)
            elif not halted and df["ts"].iloc[-2] != last_candle:
                if signal(df, a.fast, a.slow) == "buy":
                    if broker.buy(price, risk.buy_budget(broker.cash)):
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
