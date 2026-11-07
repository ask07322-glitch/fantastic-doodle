"""API 키 점검(잔고만 읽기)과 소액 시험 주문."""
from __future__ import annotations
import os
import ccxt


def explain_api_error(e: Exception) -> str:
    s = str(e).lower()
    if "no_authorization_ip" in s or "verified ip" in s or "unauthorized ip" in s:
        return ("업비트에 등록되지 않은 IP입니다. 업비트 Open API 관리에서 '허용 IP'에 "
                "이 컴퓨터의 현재 공인 IP(검색창에 '내 IP')를 등록하세요.")
    if "out_of_scope" in s:
        return "API 키 권한이 부족합니다. 자산조회·주문조회·주문하기 권한이 체크되어 있어야 합니다."
    if "invalid_access_key" in s or "jwt" in s or isinstance(e, ccxt.AuthenticationError):
        return "API 키(Access/Secret)가 올바르지 않습니다. .env의 API_KEY, API_SECRET을 확인하세요(띄어쓰기·따옴표 없이)."
    if isinstance(e, (ccxt.NetworkError, ccxt.RequestTimeout)):
        return "업비트 서버에 연결하지 못했습니다. 인터넷 연결을 확인하고 잠시 후 다시 시도하세요."
    return f"알 수 없는 오류 ({type(e).__name__})."


def _exchange(exchange_id: str):
    if not (os.environ.get("API_KEY") and os.environ.get("API_SECRET")):
        raise SystemExit(".env에 API_KEY와 API_SECRET을 넣어 주세요.")
    return getattr(ccxt, exchange_id)({"apiKey": os.environ["API_KEY"],
                                       "secret": os.environ["API_SECRET"], "enableRateLimit": True})


def api_check(exchange_id: str, symbols) -> bool:
    """잔고만 읽는다 (주문 없음). 성공하면 True."""
    ex = _exchange(exchange_id)
    try:
        free = {k: float(v) for k, v in ex.fetch_balance().get("free", {}).items() if v}
    except Exception as e:
        print("API 점검 실패:", explain_api_error(e))
        return False
    print(f"API 연결 성공 (읽기 전용 확인)\n원화(KRW) 주문 가능 금액: {free.get('KRW', 0):,.0f}원")
    for sym in symbols:
        base = sym.split("/")[0]
        q = free.get(base, 0.0)
        if q:
            try:
                val = q * float(ex.fetch_ticker(sym)["last"])
                print(f"  {base} 보유: {q:g}개 (약 {val:,.0f}원)")
            except Exception:
                print(f"  {base} 보유: {q:g}개")
    print("※ 출금 권한이 꺼져 있는지는 업비트 Open API 관리 화면에서 직접 확인하세요.")
    return True


def test_order(exchange_id: str, symbol: str, krw: float = 10_000.0) -> None:
    """실제 시장가로 krw원어치를 사고 바로 전부 판다. 비용은 수수료+호가 차이(보통 수십 원)."""
    from .broker import LiveBroker
    b = LiveBroker(exchange_id, symbol, state_path="test_state.json")
    price = float(b.ex.fetch_ticker(symbol)["last"])
    before = b.cash
    if before < krw * 1.01:
        raise SystemExit(f"원화 잔고가 부족합니다 (필요 {krw:,.0f}원 이상, 현재 {before:,.0f}원).")
    print(f"1) 시장가 매수: {symbol} {krw:,.0f}원어치 (현재가 {price:,.0f}원)")
    if not b.buy(price, krw):
        raise SystemExit("매수 주문이 실행되지 않았습니다.")
    print(f"   봇이 산 수량: {b.qty:g}")
    print("2) 바로 전부 시장가 매도")
    if not b.sell_all(price):
        raise SystemExit("매도가 실행되지 않았습니다. 업비트 앱에서 직접 확인하고 정리하세요.")
    after = b.cash
    print(f"완료. 원화 {before:,.0f} → {after:,.0f}원 (시험 비용 약 {before - after:,.0f}원)")
    print("업비트 앱의 거래 내역에서 매수·매도 2건이 보이는지 확인하세요.")
