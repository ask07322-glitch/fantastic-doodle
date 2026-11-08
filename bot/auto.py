"""하루 한 번 실행되는 자동매매: 큰 흐름 신호가 '바뀐 코인'만 주문한다.

- 기본은 모의(주문 없이 알림만). 실제 주문은 live=True 일 때만.
- 한도: 1회 매수 금액(budget), 봇이 들고 있는 총액 상한(max_total).
- 주문이 실패하면 상태를 바꾸지 않아 다음 실행 때 다시 시도한다.
- 첫 실행은 기준만 저장하고 주문하지 않는다(이미 오른 코인을 뒤늦게 쫓아 사지 않기 위해).
"""
from __future__ import annotations
import csv
import json
import os
import pandas as pd
from .broker import FEE
from .presets import TREND_PRESETS
from .strategy import trendhold_signal

IN, OUT = "in", "out"
MIN_ORDER = 5_000.0     # 업비트 최소 주문금액(원)
WARN = "※ 투자 권유가 아닙니다. 손실은 본인 책임입니다."


def _load(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _log_paper(path, row):
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date", "symbol", "preset", "entry_date", "entry", "exit", "pnl_pct", "hold_days"])
        w.writerow(row)


def run_auto(fetch, ex, send, make_broker, coins, preset: str, budget: float, max_total: float,
             live: bool, state_path: str = "auto_state.json", slippage: float = 0.001,
             log_path: str = "paper_trades.csv") -> list[str]:
    st, _ = TREND_PRESETS[preset]
    mode = "🟢실거래" if live else "모의"
    prev_all = _load(state_path)
    new_all = dict(prev_all)
    data = {}
    for sym in coins:
        try:
            data[sym] = fetch(ex, sym, "1d", st.trend + 30)
        except Exception as e:
            print(f"{sym}: 건너뜀 ({type(e).__name__})")
    brokers = {}

    def broker(sym):
        if sym not in brokers:
            brokers[sym] = make_broker(sym)
        return brokers[sym]

    invested = sum(broker(s).qty * float(df["close"].iloc[-1]) for s, df in data.items()) if live else 0.0
    msgs, lines = [], []
    for sym, df in data.items():
        conf = df["close"].iloc[:-1]
        price = float(df["close"].iloc[-1])
        day = str((pd.to_datetime(df["ts"].iloc[-2], unit="ms") + pd.Timedelta(hours=9)).date())
        sig = trendhold_signal(df, st.trend, st.band)
        prev = prev_all.get(sym, {}).get("state")
        cur = IN if sig == "buy" else OUT if sig == "sell" else (prev or OUT)
        ma, p = float(conf.rolling(st.trend).mean().iloc[-1]), float(conf.iloc[-1])
        info = f"종가 {p:,.0f} / {st.trend}일 평균 {ma:,.0f} ({(p / ma - 1) * 100:+.1f}%)"
        lines.append(f"{sym}: {'보유' if cur == IN else '현금'}  {info}")
        keep = {k: prev_all.get(sym, {}).get(k) for k in ("entry", "entry_date")}
        if prev is None or prev == cur:
            new_all[sym] = {"state": cur, "date": day, **keep}
            continue
        head = f"[{mode}] {'📈 매수' if cur == IN else '📉 매도'} 신호 | {sym} {preset}\n{info}"
        try:
            if not live:
                note = "(모의 모드라서 실제 주문은 하지 않았습니다)"
                if cur == IN:
                    keep = {"entry": price, "entry_date": day}
                    note += f"\n가상 매수 기록: {price:,.0f}원"
                elif keep.get("entry"):
                    e = float(keep["entry"])   # 수수료·슬리피지 반영한 가상 손익
                    pnl = ((1 - FEE) ** 2 * price * (1 - slippage) / (e * (1 + slippage)) - 1) * 100
                    days = (pd.Timestamp(day) - pd.Timestamp(keep["entry_date"])).days
                    _log_paper(log_path, [day, sym, preset, keep["entry_date"], e, price, round(pnl, 2), days])
                    note += f"\n가상 손익: {pnl:+.1f}% ({days}일 보유) → paper_trades.csv에 기록"
                    keep = {"entry": None, "entry_date": None}
                msgs.append(head + "\n" + note)
            elif cur == IN:
                b = broker(sym)
                amt = min(budget, max_total - invested, b.cash * 0.995)
                if amt < MIN_ORDER:
                    msgs.append(head + f"\n주문하지 않음: 한도/잔고 부족 (가능 금액 {max(amt, 0):,.0f}원 < 최소 {MIN_ORDER:,.0f}원)")
                elif b.buy(price, amt):
                    invested += amt
                    msgs.append(head + f"\n✅ 시장가 매수 주문: {amt:,.0f}원어치 (봇 보유 {b.qty:g}개)")
                else:
                    msgs.append(head + "\n주문하지 않음: 이미 봇이 보유 중")
            else:
                b = broker(sym)
                q = b.qty
                if b.sell_all(price):
                    msgs.append(head + f"\n✅ 시장가 매도 주문: 봇 보유분 {q:g}개 전부")
                else:
                    msgs.append(head + "\n주문하지 않음: 봇이 보유한 수량이 없습니다")
            new_all[sym] = {"state": cur, "date": day, **keep}
        except Exception as e:  # 실패하면 상태를 그대로 둬서 다음 실행 때 재시도
            msgs.append(head + f"\n⚠️ 주문 실패 ({type(e).__name__}) — 업비트 앱에서 확인하세요. 다음 실행 때 다시 시도합니다.")
    with open(state_path, "w") as f:
        json.dump(new_all, f)
    for line in lines:
        print(line)
    if msgs:
        send("\n\n".join(msgs) + "\n\n" + WARN)
    elif not prev_all:
        send(f"✅ 자동매매 감시 시작 [{mode}] (1회 {budget:,.0f}원, 총 {max_total:,.0f}원 한도)\n\n" + "\n".join(lines) + "\n\n" + WARN)
    else:
        print("신호 변경 없음")
    return msgs
