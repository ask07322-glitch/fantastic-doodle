"""전략 묶음. base = 처음 버전, improved = 개선 버전."""
from .risk import Risk
from .strategy import Strategy

PRESETS = {
    # 처음 버전
    "base": (Strategy(), Risk()),
    # 개선: 큰 하락장 매수 회피 + 느린 선으로 가짜 신호 감소 + 재매수 대기
    #       + 수익은 길게(추적손절), 손실은 짧게(손절 -3%)
    "improved": (
        Strategy(fast=12, slow=36, trend=120, cooldown=6),
        Risk(stop_loss=0.03, take_profit=0.0, trailing_start=0.03, trailing_gap=0.02),
    ),
}
