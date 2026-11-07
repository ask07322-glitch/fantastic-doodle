"""하루 한 번 실행: 큰 흐름 신호가 바뀌었는지 확인해서 바뀐 것만 알림."""
from __future__ import annotations
import json
import pandas as pd
from .compare import COINS
from .presets import TREND_PRESETS
from .strategy import trendhold_signal

IN, OUT = "in", "out"
WARN = "※ 투자 권유가 아닙니다. 최종 판단은 직접 하세요."


def _load(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def check_signals(fetch, ex, send, coins=COINS, presets=TREND_PRESETS,
                  state_path: str = "signal_state.json", summary: bool = False) -> list[str]:
    """바뀐 신호 메시지 목록을 반환하고 send()로 전송. 첫 실행은 기준만 저장(알림 없음)."""
    prev_all, new_all, alerts, lines = _load(state_path), {}, [], []
    need = max(s.trend for s, _ in presets.values()) + 30
    for sym in coins:
        try:
            df = fetch(ex, sym, "1d", need)
        except Exception as e:
            print(f"{sym}: 건너뜀 ({type(e).__name__})")
            for name in presets:  # 못 가져온 코인은 직전 상태 유지
                k = f"{sym}|{name}"
                if k in prev_all:
                    new_all[k] = prev_all[k]
            continue
        conf = df["close"].iloc[:-1]
        day = str((pd.to_datetime(df["ts"].iloc[-2], unit="ms") + pd.Timedelta(hours=9)).date())
        for name, (st, _) in presets.items():
            key = f"{sym}|{name}"
            sig = trendhold_signal(df, st.trend, st.band)
            prev = prev_all.get(key, {}).get("state")
            cur = IN if sig == "buy" else OUT if sig == "sell" else (prev or OUT)  # 중립이면 직전 상태 유지
            new_all[key] = {"state": cur, "date": day}
            ma, p = float(conf.rolling(st.trend).mean().iloc[-1]), float(conf.iloc[-1])
            info = f"종가 {p:,.0f} / {st.trend}일 평균 {ma:,.0f} ({(p / ma - 1) * 100:+.1f}%)"
            lines.append(f"{sym} {name}: {'보유' if cur == IN else '현금'}  {info}")
            if prev is not None and prev != cur:
                tag = "📈 매수 신호" if cur == IN else "📉 매도 신호"
                alerts.append(f"{tag} | {sym} {name}\n{info}\n기준일 {day}")
    with open(state_path, "w") as f:
        json.dump(new_all, f)
    first_run = not prev_all
    for line in lines:
        print(line)
    if alerts:
        send("\n\n".join(alerts) + "\n\n" + WARN)
    elif first_run:
        send("✅ 신호 감시를 시작했습니다. 신호가 바뀌면 알려 드립니다.\n\n" + "\n".join(lines) + "\n\n" + WARN)
    elif summary:
        send("오늘의 상태 (변경 없음)\n\n" + "\n".join(lines) + "\n\n" + WARN)
    else:
        print("신호 변경 없음")
    return alerts
