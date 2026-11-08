"""실행: python -m bot.main [--live] [--backtest] [--compare]"""
from __future__ import annotations
import argparse, csv, os, time, dataclasses, datetime as dt
import ccxt
import pandas as pd
from .backtest import run as backtest
from .broker import PaperBroker, LiveBroker
from .notify import Telegram, explain, find_chat_ids, load_env
from .presets import ALL_PRESETS, TREND_PRESETS
from .strategy import day_of, signal_for


def _page(ex, symbol, tf, **kw):
    """요청 한도·일시적 네트워크 오류(절전 복귀 직후 등)는 기다렸다가 다시 시도."""
    waits = (5, 10, 20, 30, 30)
    for i in range(len(waits) + 1):
        try:
            return ex.fetch_ohlcv(symbol, tf, **kw)
        except ccxt.NetworkError:  # RateLimitExceeded, RequestTimeout, ExchangeNotAvailable 포함
            if i == len(waits):
                raise
            time.sleep(waits[i])


def fetch(ex, symbol, tf, limit=200) -> pd.DataFrame:
    """limit개 캔들. 200개 넘으면 여러 번 나눠서 가져옵니다."""
    if limit <= 200:
        rows = _page(ex, symbol, tf, limit=limit)
    else:
        step = ex.parse_timeframe(tf) * 1000
        since = ex.milliseconds() - limit * step
        rows = []
        while len(rows) < limit:
            part = _page(ex, symbol, tf, since=since, limit=200)
            time.sleep(0.15)  # 업비트는 초당 약 10회 제한이라 천천히 요청
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
    ap.add_argument("--timeframe", default=None, help="기본: trend 전략은 1d, 그 외 1h")
    ap.add_argument("--strategy", default="improved", choices=list(ALL_PRESETS),
                    help="base/improved/vbreak/vbreak_f(분·시간봉용), trend100/trend200(일봉용 큰 흐름 보유)")
    ap.add_argument("--interval", type=int, default=30, help="폴링 간격(초)")
    ap.add_argument("--backtest", action="store_true", help="백테스트만 실행 (그림 저장)")
    ap.add_argument("--compare", action="store_true", help="여러 코인에서 시간봉 전략들 비교")
    ap.add_argument("--compare-trend", action="store_true", help="일봉 trend-hold vs 그냥 보유 비교(수익+최대낙폭)")
    ap.add_argument("--candles", type=int, default=1000, help="백테스트에 쓸 캔들 개수")
    ap.add_argument("--slippage", type=float, default=0.001,
                    help="체결가가 불리하게 밀리는 비율 (기본 0.001 = 0.1%%). 백테스트/비교/모의매매에 적용")
    ap.add_argument("--status", action="store_true", help="지금 각 코인이 평균선 위(보유)/아래(현금)인지 보기")
    ap.add_argument("--position", type=float, default=None,
                    help="매수 때 현금의 몇 %%를 쓸지 (0~1, 예: 0.1=10%%). 기본: 전략별 설정. 백테스트/모의/실거래에 적용")
    ap.add_argument("--check-signals", action="store_true",
                    help="하루 1번 실행: 큰 흐름 신호가 바뀌었는지 확인해서 텔레그램으로 알림")
    ap.add_argument("--summary", action="store_true", help="--check-signals와 함께: 변경이 없어도 현재 상태 전송")
    ap.add_argument("--telegram-test", action="store_true", help="텔레그램 테스트 메시지 보내기")
    ap.add_argument("--telegram-chat-id", action="store_true", help="텔레그램 채팅 ID 찾기 (봇에게 먼저 메시지를 보낸 뒤)")
    ap.add_argument("--api-check", action="store_true", help="API 키 점검: 잔고만 읽습니다(주문 없음)")
    ap.add_argument("--test-order", action="store_true", help="소액(1만원) 시험 주문: 사고 바로 팔아 주문 경로 확인")
    ap.add_argument("--auto-trade", action="store_true",
                    help="하루 1번 실행: 신호가 바뀐 코인만 주문(기본 모의, --live면 실제)")
    ap.add_argument("--budget", type=float, default=30_000, help="--auto-trade: 1회 매수 금액(원)")
    ap.add_argument("--max-total", type=float, default=100_000, help="--auto-trade: 봇이 보유할 총액 상한(원)")
    ap.add_argument("--live", action="store_true", help="실거래 (기본은 모의매매)")
    a = ap.parse_args()
    load_env()  # .env의 API 키/텔레그램 설정 읽기
    tg = Telegram()

    if a.telegram_chat_id:
        if not tg.token:
            raise SystemExit(".env에 TELEGRAM_BOT_TOKEN을 먼저 넣어 주세요.")
        try:
            ids = find_chat_ids(tg.token)
        except Exception as e:
            raise SystemExit(f"조회 실패: {explain(e)}")
        if not ids:
            raise SystemExit("메시지가 없습니다. 텔레그램에서 만든 봇에게 아무 말이나 보낸 뒤 다시 실행하세요.")
        for cid, name in ids:
            print(f"채팅 ID: {cid}  ({name})")
        return

    if a.telegram_test:
        if not tg.enabled:
            raise SystemExit(".env에 TELEGRAM_BOT_TOKEN과 TELEGRAM_CHAT_ID를 넣어 주세요.")
        print("전송 성공" if tg.send("✅ 코인 봇 텔레그램 연결 테스트입니다.") else "전송 실패 (토큰/채팅ID 확인)")
        return

    pub = getattr(ccxt, a.exchange)({"enableRateLimit": True})
    pub.rateLimit = max(pub.rateLimit, 150)  # 요청 간격을 넉넉히 (업비트 한도 보호)
    st, risk = ALL_PRESETS[a.strategy]
    if a.position is not None:
        if not 0 < a.position <= 1:
            raise SystemExit("--position은 0보다 크고 1 이하여야 합니다 (예: 0.1 = 현금의 10%)")
        risk = dataclasses.replace(risk, position_pct=a.position)
    tf = a.timeframe or ("1d" if st.kind == "trendhold" else "1h")

    if a.compare:
        from .compare import compare
        compare(fetch, pub, max(a.candles, 2000), slippage=a.slippage)
        return

    def need_live_switch():
        if os.environ.get("ENABLE_LIVE", "").strip().upper() != "YES":
            raise SystemExit("실거래 스위치가 꺼져 있습니다. .env에 ENABLE_LIVE=YES 를 넣어야 실제 주문이 나갑니다.")

    if a.api_check:
        from .apicheck import api_check
        from .compare import COINS
        raise SystemExit(0 if api_check(a.exchange, COINS) else 1)

    if a.test_order:
        from .apicheck import explain_api_error, test_order
        need_live_switch()
        print(f"시험 주문: {a.exchange} {a.symbol} 1만원어치를 실제로 사고 바로 전부 팝니다 (비용 보통 수십 원).")
        if input("진행하려면 'YES' 입력: ") != "YES":
            return
        try:
            test_order(a.exchange, a.symbol)
        except SystemExit:
            raise
        except Exception as e:
            raise SystemExit(f"시험 주문 실패: {explain_api_error(e)}\n업비트 앱의 거래 내역/보유 코인을 꼭 확인하세요.")
        return

    if a.auto_trade:
        from .auto import run_auto
        from .compare import COINS
        preset = a.strategy if a.strategy in TREND_PRESETS else "trend200"
        if a.live:
            need_live_switch()
            from .apicheck import api_check
            if not api_check(a.exchange, COINS):
                tg.send("⚠️ 자동매매 중단: API 점검 실패 (IP/키/권한 확인)")
                raise SystemExit(1)
        make = (lambda sym: LiveBroker(a.exchange, sym)) if a.live else None
        run_auto(fetch, pub, tg.send, make, COINS, preset, a.budget, a.max_total, a.live)
        return

    if a.check_signals:
        from .signals import check_signals
        if not tg.enabled:
            print("[안내] 텔레그램 설정이 없어 화면에만 표시합니다 (.env 확인).")
        check_signals(fetch, pub, tg.send, summary=a.summary)
        return

    if a.status:
        from .status import status
        status(fetch, pub)
        return

    if a.compare_trend:
        from .compare import compare_trend
        compare_trend(fetch, pub, max(a.candles, 2000), slippage=a.slippage)
        return

    if a.backtest:
        from . import chart
        df = fetch(pub, a.symbol, tf, a.candles)
        res = backtest(df, st, risk, slippage=a.slippage)
        print(f"[{a.strategy}] 데이터 {len(df)}개 | 봇 {res['return_pct']:+.2f}% | 그냥 들고 있기 "
              f"{res['buy_hold_pct']:+.2f}% | 최대 하락 {res['max_drawdown_pct']:.2f}% | 거래 {res['trades']}번")
        ma = st.kind == "ma"
        path = chart.save(df, res, st.fast if ma else 0, st.slow if ma else 0,
                          f"{a.symbol} {tf} 백테스트 ({a.strategy})",
                          "backtest.png", st.trend)
        print("그림 저장:", path)
        chart.open_file(path)
        return

    if a.live:
        print(f"[실거래] {a.exchange} {a.symbol} | 전략 {a.strategy} | 매수 때 현금의 {risk.position_pct*100:.0f}% 사용")
        print("봇이 직접 산 수량만 팝니다(state.json에 기록). 계좌에 원래 있던 코인은 건드리지 않습니다.")
        if input("실거래 모드입니다. 실제 돈이 거래됩니다. 'YES' 입력: ") != "YES":
            return
        broker = LiveBroker(a.exchange, a.symbol)
    else:
        broker = PaperBroker(slippage=a.slippage)
    print(f"[start] {a.exchange} {a.symbol} {tf} strategy={a.strategy} "
          f"mode={'LIVE' if a.live else 'PAPER'}")
    mode_tag = "실거래" if a.live else "모의"
    tg.send(f"[{mode_tag}] 봇 시작: {a.symbol} {tf} {a.strategy}")

    bpd = 86400 / pub.parse_timeframe(tf)
    if st.kind == "vbreak" and bpd < 2:
        raise SystemExit("변동성 돌파는 1일봉 미만 시간봉(예: 1h, 4h)에서만 쓸 수 있습니다.")
    need = st.history_bars(bpd)
    day, day_start_eq, halted = dt.date.today(), None, False
    last_candle, peak, bars_since_exit, buy_day = None, 0.0, 10**6, None
    while True:
        try:
            df = fetch(pub, a.symbol, tf, max(200, need))
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
                    tg.send(f"[{mode_tag}] 📉 매도 {a.symbol} {price:,.0f}원 ({why or '신호'})")
                    _log("sell", price)
            elif (not halted and (new_candle or st.one_per_day) and bars_since_exit > st.cooldown
                  and (not st.one_per_day or day_of(df["ts"].iloc[-1]) != buy_day)):
                # 변동성 돌파는 봉 중간에 돌파할 수 있어 매 폴링마다 확인
                if signal_for(df, st) == "buy":
                    if broker.buy(price, risk.buy_budget(broker.cash)):
                        peak = price
                        buy_day = day_of(df["ts"].iloc[-1])
                        print(f"[buy] {price:,.0f}")
                        tg.send(f"[{mode_tag}] 📈 매수 {a.symbol} {price:,.0f}원")
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
