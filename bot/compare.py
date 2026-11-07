"""여러 코인/시간봉에서 모든 전략(PRESETS)을 한 표로 비교."""
from __future__ import annotations
from .backtest import run
from .presets import PRESETS

COINS = ["BTC/KRW", "ETH/KRW", "XRP/KRW", "SOL/KRW"]
FRAMES = ["1h", "4h"]
WARMUP = 200  # 모든 전략이 같은 시점부터 시작하도록


def compare(fetch, ex, candles: int = 2000, coins=COINS, frames=FRAMES, slippage: float = 0.0) -> None:
    print(f"가정: 수수료 0.05% + 슬리피지 {slippage*100:.2f}% (사고팔 때마다 불리하게 체결)")
    names = list(PRESETS)
    st = {k: dict(ret=[], mdd=[], tr=[], beat=0, pos=0, both=0) for k in names}
    print(f"{'코인':<9}{'봉':<4}{'그냥보유':>9}" + "".join(f"{k:>10}" for k in names) + "   (수익률 %)")
    n = 0
    for sym in coins:
        for tf in frames:
            try:
                df = fetch(ex, sym, tf, candles).reset_index(drop=True)
            except Exception as e:
                print(f"{sym:<9}{tf:<4} 건너뜀 ({type(e).__name__})")
                continue
            h = len(df) // 2
            halves = (df.iloc[:h].reset_index(drop=True), df.iloc[h:].reset_index(drop=True))
            res = {k: run(df, *PRESETS[k], warmup=WARMUP, slippage=slippage) for k in names}
            n += 1
            bh = res[names[0]]["buy_hold_pct"]
            print(f"{sym:<9}{tf:<4}{bh:>8.1f}%" + "".join(f"{res[k]['return_pct']:>9.1f}%" for k in names))
            for k in names:
                r, s = res[k], st[k]
                s["ret"].append(r["return_pct"]); s["mdd"].append(r["max_drawdown_pct"]); s["tr"].append(r["trades"])
                s["beat"] += r["return_pct"] > bh
                s["pos"] += r["return_pct"] > 0
                s["both"] += all(run(x, *PRESETS[k], warmup=WARMUP // 2, slippage=slippage)["return_pct"] > 0 for x in halves)
    if not n:
        return
    print(f"\n=== 요약 ({n}건) ===")
    print(f"{'전략':<10}{'평균수익':>9}{'평균최대하락':>13}{'평균거래수':>10}{'플러스':>7}{'보유보다나음':>12}{'전후반모두플러스':>14}")
    for k in names:
        s = st[k]
        print(f"{k:<10}{sum(s['ret'])/n:>8.2f}%{sum(s['mdd'])/n:>12.1f}%{sum(s['tr'])/n:>10.1f}"
              f"{s['pos']:>6}/{n}{s['beat']:>11}/{n}{s['both']:>13}/{n}")
    print("\n※ 과거 결과일 뿐 미래를 보장하지 않습니다. 수익이 나려면 '플러스'와 '전후반모두플러스'가 "
          "모두 높아야 하고(절반 이상), 한두 건에만 의존하면 우연일 수 있습니다.")
