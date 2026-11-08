"""거래 통계: 승률만이 아니라 '기대값'(평균적으로 한 번 거래에 얼마를 버는가)으로 판단한다."""
from __future__ import annotations
import math


def trade_stats(pnls: list[float]) -> dict:
    """pnls: 거래별 손익률(%) 리스트."""
    n = len(pnls)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    wr = len(wins) / n if n else 0.0
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = -sum(losses) / len(losses) if losses else 0.0      # 양수(손실 크기)
    payoff = avg_win / avg_loss if avg_loss else (math.inf if avg_win else 0.0)
    gl = -sum(losses)
    pf = sum(wins) / gl if gl else (math.inf if wins else 0.0)
    return {
        "n": n,
        "win_rate": wr * 100,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "payoff": payoff,                                  # 평균이익 ÷ 평균손실
        "expectancy": wr * avg_win - (1 - wr) * avg_loss,  # 1회 거래 평균 손익(%)
        "profit_factor": pf,                               # 총이익 ÷ 총손실
    }


def kelly_fraction(win_rate_pct: float, payoff: float) -> float:
    """켈리 비율 f = p - (1-p)/b. 기대값이 마이너스면 0."""
    if payoff <= 0 or math.isinf(payoff):
        return 0.0
    p = win_rate_pct / 100
    return max(p - (1 - p) / payoff, 0.0)


def suggest_position(stats: dict, cap: float = 0.3, min_trades: int = 30) -> tuple[float, str]:
    """보수적 제안: 절반 켈리, 상한 cap. 거래 수가 적으면 믿지 말라고 알린다."""
    if stats["n"] < min_trades:
        return 0.0, f"거래가 {stats['n']}번뿐이라 아직 크기를 정하기엔 표본이 부족합니다 (최소 {min_trades}번 이상 필요)."
    f = kelly_fraction(stats["win_rate"], stats["payoff"]) / 2
    f = min(f, cap)
    if f <= 0:
        return 0.0, "기대값이 플러스라는 근거가 없어 베팅하지 않는 쪽을 권합니다."
    return f, f"절반 켈리 {f*100:.0f}% (상한 {cap*100:.0f}%). 승률·손익비 추정은 오차가 커서 이 이하로 쓰세요."
