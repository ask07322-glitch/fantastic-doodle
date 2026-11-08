"""모의매매 기록 통계."""
from __future__ import annotations
import os
import pandas as pd
from .stats import suggest_position, trade_stats


def _fmt(s: dict) -> str:
    pf = "∞" if s["profit_factor"] == float("inf") else f"{s['profit_factor']:.2f}"
    po = "∞" if s["payoff"] == float("inf") else f"{s['payoff']:.2f}"
    return (f"거래 {s['n']}번 | 승률 {s['win_rate']:.0f}% | 평균이익 {s['avg_win']:+.1f}% / 평균손실 -{s['avg_loss']:.1f}% "
            f"| 손익비 {po} | 기대값 {s['expectancy']:+.2f}%/회 | 이익계수 {pf}")


def paper_report(path: str = "paper_trades.csv") -> None:
    if not os.path.exists(path):
        print("아직 모의매매 기록이 없습니다. `--auto-trade`(모의)를 매일 실행하면 신호가 바뀔 때 가상 거래가 기록됩니다.")
        return
    df = pd.read_csv(path)
    if df.empty:
        print("기록이 비어 있습니다.")
        return
    allp = trade_stats(df["pnl_pct"].tolist())
    print("=== 모의매매 전체 ===")
    print(_fmt(allp))
    for sym, g in df.groupby("symbol"):
        print(f"  {sym}: {_fmt(trade_stats(g['pnl_pct'].tolist()))}")
    print(f"평균 보유 기간: {df['hold_days'].mean():.0f}일")
    f, note = suggest_position(allp)
    print(f"\n[베팅 크기 참고] {note}")
    print("※ 승률이 높다고 좋은 게 아니라 '기대값'이 플러스인지가 핵심입니다. 표본이 30번 미만이면 우연일 수 있습니다.")
