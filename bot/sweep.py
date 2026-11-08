"""손절/추적손절/평균선 길이 등을 바꿔 보며 '앞 60%로 고르고 뒤 40%로 확인'하는 과적합 점검 연구."""
from __future__ import annotations
import itertools
import pandas as pd
from .backtest import run
from .compare import COINS
from .risk import Risk
from .stats import trade_stats
from .strategy import Strategy

TRENDS = (50, 100, 150, 200)
BANDS = (0.0, 0.02, 0.04)
STOPS = (0.0, 0.12)       # 0 = 손절 없음
TRAILS = (0.0, 0.20)      # 0 = 추적손절 없음 (최고가 대비 -20%면 매도)
WARM = 205                # 모든 조합이 같은 날부터 시작


def make(trend, band, stop, trail):
    st = Strategy(kind="trendhold", trend=trend, band=band, cooldown=5 if (stop or trail) else 0)
    risk = Risk(position_pct=1.0, stop_loss=stop, take_profit=0.0,
                trailing_start=0.05 if trail else 0.0, trailing_gap=trail)
    return st, risk


def _score(r) -> float:
    """수익 ÷ 최대낙폭: 위험 대비 얼마나 벌었나."""
    dd = abs(r["max_drawdown_pct"])
    return r["return_pct"] / dd if dd > 1e-9 else r["return_pct"]


def _label(p):
    t, b, s, tr = p
    return f"평균{t}일 ±{b*100:.0f}% 손절{'없음' if not s else f'-{s*100:.0f}%'} 추적{'없음' if not tr else f'-{tr*100:.0f}%'}"


def sweep(fetch, ex, candles: int = 2000, coins=COINS, slippage: float = 0.001,
          split: float = 0.6, top: int = 5, progress=print) -> pd.DataFrame | None:
    data = {}
    for sym in coins:
        try:
            df = fetch(ex, sym, "1d", candles).reset_index(drop=True)
            if len(df) >= WARM * 3:
                data[sym] = df
        except Exception as e:
            print(f"{sym}: 건너뜀 ({type(e).__name__})")
    if not data:
        print("사용할 데이터가 없습니다.")
        return None
    n_days = min(len(d) for d in data.values())
    print(f"코인 {len(data)}개, 일봉 약 {n_days}일. 앞 {split*100:.0f}%로 고르고 뒤 {100-split*100:.0f}%로 확인합니다. "
          f"(슬리피지 {slippage*100:.2f}% 반영)")
    rows = []
    combos = list(itertools.product(TRENDS, BANDS, STOPS, TRAILS))
    hold = {}
    for i, p in enumerate(combos, 1):
        st, risk = make(*p)
        tr_s, te_s, te_r, te_dd, pnls = [], [], [], [], []
        for sym, df in data.items():
            k = int(len(df) * split)
            train = df.iloc[:k].reset_index(drop=True)
            test = df.iloc[k - WARM:].reset_index(drop=True)
            r1 = run(train, st, risk, warmup=WARM, slippage=slippage)
            r2 = run(test, st, risk, warmup=WARM, slippage=slippage)
            tr_s.append(_score(r1)); te_s.append(_score(r2))
            te_r.append(r2["return_pct"]); te_dd.append(r2["max_drawdown_pct"])
            pnls += [x["pnl_pct"] for x in r2["trade_list"] if x["side"] == "sell"]
            hold[sym] = (r2["buy_hold_pct"], r2["buy_hold_mdd_pct"])
        s = trade_stats(pnls)
        rows.append(dict(params=p, train=sum(tr_s) / len(tr_s), test_score=sum(te_s) / len(te_s),
                         test_ret=sum(te_r) / len(te_r), test_dd=sum(te_dd) / len(te_dd), **s))
        if i % 8 == 0:
            progress(f"  진행 {i}/{len(combos)}")
    df = pd.DataFrame(rows).sort_values("train", ascending=False).reset_index(drop=True)
    h_ret = sum(v[0] for v in hold.values()) / len(hold)
    h_dd = sum(v[1] for v in hold.values()) / len(hold)

    def line(r, tag=""):
        return (f"{tag:<4}{_label(r['params']):<32}{r['train']:>6.2f}{r['test_ret']:>9.1f}%{r['test_dd']:>8.1f}%"
                f"{int(r['n']):>6}{r['win_rate']:>7.0f}%{r['payoff']:>7.1f}{r['expectancy']:>+8.1f}%")

    head = f"{'':<4}{'설정':<32}{'학습점수':>6}{'시험수익':>10}{'시험낙폭':>9}{'거래':>6}{'승률':>8}{'손익비':>7}{'기대값':>9}"
    print("\n=== 학습 구간 점수 상위 (그 뒤 시험 구간 성과) ===")
    print(head)
    for i in range(min(top, len(df))):
        print(line(df.loc[i], f"{i+1}위"))
    base = df[df["params"].apply(lambda p: p == (200, 0.02, 0.0, 0.0))]
    if len(base):
        print(line(base.iloc[0], "기본"))
    print(f"{'':<4}{'그냥 보유(시험 구간 평균)':<32}{'':>6}{h_ret:>9.1f}%{h_dd:>8.1f}%")

    corr = df["train"].rank().corr(df["test_score"].rank())
    top10 = df.head(10)
    pos = int((top10["test_ret"] > 0).sum())
    print("\n=== 과적합 점검 ===")
    print(f"학습 순위와 시험 순위의 상관(순위상관): {corr:+.2f}   (1에 가까울수록 '과거에서 고른 것이 미래에도 좋다')")
    print(f"학습 상위 10개 중 시험에서도 수익 플러스: {pos}/10")
    if corr < 0.3:
        print("→ 판단: 학습에서 좋았던 설정이 시험에서도 좋다는 근거가 약합니다. '최적값'을 믿지 마세요.")
    else:
        print("→ 판단: 어느 정도 일관성이 있습니다. 그래도 거래 수가 적어 확정은 아닙니다.")
    print("※ 거래가 적으면 통계가 흔들립니다. 승률보다 '기대값(1회 평균 손익)'과 '손익비'를 보세요.")
    return df
