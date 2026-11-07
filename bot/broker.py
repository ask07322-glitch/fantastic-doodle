"""브로커: 모의(PaperBroker) / 실거래(LiveBroker). 같은 인터페이스."""
from __future__ import annotations
import os
from dataclasses import dataclass, field

FEE = 0.0005  # 0.05% 수수료 가정 (업비트 KRW 마켓)


@dataclass
class PaperBroker:
    cash: float = 1_000_000.0
    qty: float = 0.0
    entry: float = 0.0
    fee: float = FEE
    log: list = field(default_factory=list)

    def balance(self, price: float) -> tuple[float, float]:
        return self.cash, self.qty

    def equity(self, price: float) -> float:
        return self.cash + self.qty * price

    def buy(self, price: float, budget: float) -> bool:
        if budget <= 0 or budget > self.cash or self.qty > 0:
            return False
        q = budget * (1 - self.fee) / price
        self.cash -= budget
        self.qty, self.entry = q, price
        self.log.append(("buy", price, q))
        return True

    def sell_all(self, price: float) -> bool:
        if self.qty <= 0:
            return False
        self.cash += self.qty * price * (1 - self.fee)
        self.log.append(("sell", price, self.qty))
        self.qty, self.entry = 0.0, 0.0
        return True


class LiveBroker:
    """ccxt 기반 실거래. 시장가 주문. (업비트 시장가 매수는 금액 기준)"""

    def __init__(self, exchange_id: str, symbol: str):
        import ccxt
        self.symbol = symbol
        self.ex = getattr(ccxt, exchange_id)({
            "apiKey": os.environ["API_KEY"],
            "secret": os.environ["API_SECRET"],
            "enableRateLimit": True,
        })
        self.base, self.quote = symbol.split("/")
        self.entry = 0.0

    def _free(self, cur: str) -> float:
        return float(self.ex.fetch_balance().get(cur, {}).get("free", 0) or 0)

    @property
    def cash(self) -> float:
        return self._free(self.quote)

    @property
    def qty(self) -> float:
        return self._free(self.base)

    def equity(self, price: float) -> float:
        return self.cash + self.qty * price

    def buy(self, price: float, budget: float) -> bool:
        if budget <= 0 or self.qty * price > 1000:
            return False
        amount = budget / price
        # 업비트: 시장가 매수는 price=총금액 필요
        params = {"createMarketBuyOrderRequiresPrice": False}
        self.ex.create_order(self.symbol, "market", "buy",
                             budget if self.ex.id == "upbit" else amount,
                             None, params)
        self.entry = price
        return True

    def sell_all(self, price: float) -> bool:
        q = self.qty
        if q * price < 1000:
            return False
        self.ex.create_order(self.symbol, "market", "sell", q)
        self.entry = 0.0
        return True
