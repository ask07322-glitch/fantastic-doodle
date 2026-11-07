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
    # 변동성 돌파: 하루 최대 1번 매수, 다음 날 시작에 정리, 손절 -3%
    "vbreak": (Strategy(kind="vbreak", k=0.5), Risk(stop_loss=0.03, take_profit=0.0)),
    # 변동성 돌파 + 5일 평균 위에서만 매수 (하락장 회피)
    "vbreak_f": (Strategy(kind="vbreak", k=0.5, day_ma=5), Risk(stop_loss=0.03, take_profit=0.0)),
}


# 큰 흐름 따라 보유(일봉용): 장기 평균선 위면 전액 보유, 아래면 현금. 손절/익절 없음(평균선 이탈이 곧 매도).
_TH = dict(position_pct=1.0, stop_loss=0.0, take_profit=0.0)
TREND_PRESETS = {
    "trend100": (Strategy(kind="trendhold", trend=100, band=0.02), Risk(**_TH)),
    "trend200": (Strategy(kind="trendhold", trend=200, band=0.02), Risk(**_TH)),
}
ALL_PRESETS = {**PRESETS, **TREND_PRESETS}
