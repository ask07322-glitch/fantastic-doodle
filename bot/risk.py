"""포지션 크기/손절/익절/추적손절 규칙."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class Risk:
    position_pct: float = 0.30      # 1회 매수에 쓸 현금 비중
    stop_loss: float = 0.03         # -3% 손절 (0이면 끔)
    take_profit: float = 0.06       # +6% 익절 (0이면 끔)
    trailing_start: float = 0.0     # 이만큼 오르면 추적손절 시작 (0이면 끔)
    trailing_gap: float = 0.0       # 최고가 대비 이만큼 내려오면 매도
    max_daily_loss: float = 0.05    # 하루 -5% 넘으면 당일 거래 중단
    min_order_value: float = 5000.0 # 거래소 최소 주문금액(업비트 KRW 5,000)

    def buy_budget(self, cash: float) -> float:
        v = cash * self.position_pct
        return v if v >= self.min_order_value else 0.0

    def exit_reason(self, entry: float, price: float, peak: float | None = None) -> str | None:
        if self.stop_loss and price <= entry * (1 - self.stop_loss):
            return "stop_loss"
        if self.take_profit and price >= entry * (1 + self.take_profit):
            return "take_profit"
        if (self.trailing_gap and peak and peak >= entry * (1 + self.trailing_start)
                and price <= peak * (1 - self.trailing_gap)):
            return "trailing"
        return None
