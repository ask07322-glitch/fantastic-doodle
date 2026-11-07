"""여러 코인/시간봉에서 base vs improved 비교표 출력."""
from __future__ import annotations
from .backtest import run
from .presets import PRESETS

COINS = ["BTC/KRW", "ETH/KRW", "XRP/KRW", "SOL/KRW"]
FRAMES = ["1h", "4h"]


def compare(fetch, ex, candles: int = 2000, coins=COINS, frames=FRAMES) -> None:
    print(f"{'코인':<9}{'봉':<4}{'기준(그냥보유)':>14}{'base':>9}{'improved':>10}{'거래b/i':>9}{'최대하락b/i':>14}")
    wins = n = 0
    sum_b = sum_i = 0.0
    for sym in coins:
        for tf in frames:
            try:
                df = fetch(ex, sym, tf, candles)
            except Exception as e:  # 상장 안 된 코인 등
                print(f"{sym:<9}{tf:<4} 건너뜀 ({type(e).__name__})")
                continue
            r = {k: run(df, *PRESETS[k]) for k in PRESETS}
            b, i = r["base"], r["improved"]
            n += 1
            wins += i["return_pct"] > b["return_pct"]
            sum_b += b["return_pct"]; sum_i += i["return_pct"]
            print(f"{sym:<9}{tf:<4}{b['buy_hold_pct']:>13.1f}%{b['return_pct']:>8.1f}%{i['return_pct']:>9.1f}%"
                  f"{b['trades']:>5}/{i['trades']:<3}{b['max_drawdown_pct']:>8.1f}/{i['max_drawdown_pct']:.1f}")
    if n:
        print(f"\n비교 {n}건 중 improved가 더 나은 경우: {wins}건")
        print(f"평균 수익률  base {sum_b/n:+.2f}%  |  improved {sum_i/n:+.2f}%")
        print("※ 과거 결과일 뿐 미래 수익을 보장하지 않습니다. improved가 이기는 경우가 절반 미만이면 실거래하지 마세요.")
