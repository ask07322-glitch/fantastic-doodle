"""브로커: 모의(PaperBroker) / 실거래(LiveBroker). 같은 인터페이스."""
from __future__ import annotations
import json
import os
import time
from dataclasses import dataclass, field

FEE = 0.0005  # 0.05% 수수료 가정 (업비트 KRW 마켓)


@dataclass
class PaperBroker:
    cash: float = 1_000_000.0
    qty: float = 0.0
    entry: float = 0.0
    fee: float = FEE
    slippage: float = 0.0   # 체결가가 불리하게 밀리는 비율 (0.001 = 0.1%)
    log: list = field(default_factory=list)

    def balance(self, price: float) -> tuple[float, float]:
        return self.cash, self.qty

    def equity(self, price: float) -> float:
        return self.cash + self.qty * price

    def buy(self, price: float, budget: float) -> bool:
        if budget <= 0 or budget > self.cash or self.qty > 0:
            return False
        fill = price * (1 + self.slippage)   # 살 때는 조금 비싸게
        q = budget * (1 - self.fee) / fill
        self.cash -= budget
        self.qty, self.entry = q, fill
        self.log.append(("buy", fill, q))
        return True

    def sell_all(self, price: float) -> bool:
        if self.qty <= 0:
            return False
        fill = price * (1 - self.slippage)   # 팔 때는 조금 싸게
        self.cash += self.qty * fill * (1 - self.fee)
        self.log.append(("sell", fill, self.qty))
        self.qty, self.entry = 0.0, 0.0
        return True


class LiveBroker:
    """ccxt 기반 실거래. 시장가 주문. (업비트 시장가 매수는 금액 기준)

    안전장치: 봇이 직접 산 수량만 기억(state.json)해서 그만큼만 판다.
    계좌에 원래 있던 코인은 건드리지 않는다.
    """

    def __init__(self, exchange_id: str, symbol: str, state_path: str = "state.json"):
        import ccxt
        self.symbol = symbol
        self.ex = getattr(ccxt, exchange_id)({
            "apiKey": os.environ["API_KEY"],
            "secret": os.environ["API_SECRET"],
            "enableRateLimit": True,
        })
        self.base, self.quote = symbol.split("/")
        self.state_path = state_path
        self._bot_qty, self.entry = self._load()

    # ---- 봇의 포지션 기억 ----
    def _load(self):
        try:
            with open(self.state_path) as f:
                s = json.load(f).get(self.symbol, {})
            return float(s.get("qty", 0.0)), float(s.get("entry", 0.0))
        except (OSError, ValueError):
            return 0.0, 0.0

    def _save(self):
        try:
            with open(self.state_path) as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {}
        data[self.symbol] = {"qty": self._bot_qty, "entry": self.entry}
        with open(self.state_path, "w") as f:
            json.dump(data, f)

    def _free(self, cur: str) -> float:
        return float(self.ex.fetch_balance().get(cur, {}).get("free", 0) or 0)

    @property
    def cash(self) -> float:
        return self._free(self.quote)

    @property
    def qty(self) -> float:
        """봇이 보유 중인 수량 (실제 잔고보다 클 수 없음)."""
        if self._bot_qty <= 0:
            return 0.0
        return min(self._bot_qty, self._free(self.base))

    def equity(self, price: float) -> float:
        return self.cash + self.qty * price

    def buy(self, price: float, budget: float) -> bool:
        if budget <= 0 or self._bot_qty * price > 1000:
            return False
        before = self._free(self.base)
        # 업비트: 시장가 매수는 총금액(KRW)을 넘긴다
        params = {"createMarketBuyOrderRequiresPrice": False}
        self.ex.create_order(self.symbol, "market", "buy",
                             budget if self.ex.id == "upbit" else budget / price, None, params)
        bought = 0.0
        for _ in range(6):  # 체결 반영까지 잠깐 기다림
            time.sleep(0.5)
            bought = self._free(self.base) - before
            if bought > 0:
                break
        if bought <= 0:
            bought = budget * (1 - FEE) / price  # 잔고 반영이 늦으면 추정치 사용
        self._bot_qty, self.entry = bought, price
        self._save()
        return True

    def sell_all(self, price: float) -> bool:
        q = min(self._bot_qty, self._free(self.base))
        if q * price < 1000:
            self._bot_qty, self.entry = 0.0, 0.0  # 이미 없는 포지션 정리
            self._save()
            return False
        self.ex.create_order(self.symbol, "market", "sell", q)
        self._bot_qty, self.entry = 0.0, 0.0
        self._save()
        return True
