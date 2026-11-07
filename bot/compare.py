"""여러 코인/시간봉에서 모든 전략(PRESETS)을 한 표로 비교."""
from __future__ import annotations
from .backtest import run
from .presets import PRESETS, TREND_PRESETS

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


def compare_trend(fetch, ex, candles: int = 2000, coins=COINS, slippage: float = 0.0) -> None:
    """일봉에서 trend-hold 전략 vs 그냥 보유 (수익률 + 최대 낙폭)."""
    names = list(TREND_PRESETS)
    warm = max(s.trend for s, _ in TREND_PRESETS.values()) + 5   # 모든 전략이 같은 날부터 시작
    print(f"가정: 일봉, 수수료 0.05% + 슬리피지 {slippage*100:.2f}%, 전액 보유/현금 전환")
    print(f"{'코인':<9}{'':<12}{'수익률':>9}{'최대낙폭':>9}{'거래':>6}")
    agg = {k: dict(ret=[], mdd=[], tr=[], ret_win=0, mdd_win=0, mdd_both=0, calmar_win=0) for k in names}
    hold_ret, hold_mdd, n = [], [], 0
    for sym in coins:
        try:
            df = fetch(ex, sym, "1d", candles).reset_index(drop=True)
        except Exception as e:
            print(f"{sym:<9} 건너뜀 ({type(e).__name__})")
            continue
        if len(df) < warm + 100:
            print(f"{sym:<9} 데이터 부족({len(df)}일) — 건너뜀")
            continue
        n += 1
        h = len(df) // 2
        halves = (df.iloc[:h].reset_index(drop=True), df.iloc[h:].reset_index(drop=True))
        res = {k: run(df, *TREND_PRESETS[k], warmup=warm, slippage=slippage) for k in names}
        b = res[names[0]]
        hold_ret.append(b["buy_hold_pct"]); hold_mdd.append(b["buy_hold_mdd_pct"])
        print(f"{sym:<9}{'그냥 보유':<12}{b['buy_hold_pct']:>8.1f}%{b['buy_hold_mdd_pct']:>8.1f}%{'-':>6}")
        for k in names:
            r, s = res[k], agg[k]
            s["ret"].append(r["return_pct"]); s["mdd"].append(r["max_drawdown_pct"]); s["tr"].append(r["trades"])
            s["ret_win"] += r["return_pct"] > b["buy_hold_pct"]
            s["mdd_win"] += r["max_drawdown_pct"] > b["buy_hold_mdd_pct"]
            s["calmar_win"] += (r["return_pct"] / abs(r["max_drawdown_pct"] or 1e-9)
                                > b["buy_hold_pct"] / abs(b["buy_hold_mdd_pct"] or 1e-9))
            hw = [run(x, *TREND_PRESETS[k], warmup=warm // 2, slippage=slippage) for x in halves]
            s["mdd_both"] += all(w["max_drawdown_pct"] > w["buy_hold_mdd_pct"] for w in hw)
            print(f"{'':<9}{k:<12}{r['return_pct']:>8.1f}%{r['max_drawdown_pct']:>8.1f}%{r['trades']:>5}번")
    if not n:
        return
    print(f"\n=== 요약 ({n}개 코인) ===  그냥 보유: 평균수익 {sum(hold_ret)/n:+.1f}%, 평균최대낙폭 {sum(hold_mdd)/n:.1f}%")
    print(f"{'전략':<10}{'평균수익':>9}{'평균낙폭':>9}{'평균거래':>9}{'수익>보유':>10}{'낙폭<보유':>10}{'전후반낙폭↓':>12}{'수익/낙폭↑':>11}")
    for k in names:
        s = agg[k]
        print(f"{k:<10}{sum(s['ret'])/n:>8.1f}%{sum(s['mdd'])/n:>8.1f}%{sum(s['tr'])/n:>9.1f}"
              f"{s['ret_win']:>8}/{n}{s['mdd_win']:>8}/{n}{s['mdd_both']:>10}/{n}{s['calmar_win']:>9}/{n}")
    print("\n※ 목표는 보유보다 더 버는 것이 아니라 '큰 하락을 피해 위험 대비 수익(수익/낙폭)을 높이는 것'입니다."
          " 과거 결과일 뿐 미래를 보장하지 않습니다.")
