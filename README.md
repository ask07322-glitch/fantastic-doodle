# 코인 자동매매 봇

ccxt 기반(업비트·빗썸·바이낸스 등). **기본은 모의매매**이며, `--live`를 줘야 실거래합니다.

전략: 이동평균 골든크로스 매수(RSI<70 필터) / 데드크로스 매도 + 손절 -3%, 익절 +6%, 일일 손실 -5% 시 매수 중단.

```bash
pip install -r requirements.txt
python -m bot.main --backtest --symbol BTC/KRW --timeframe 1h   # 백테스트
python -m bot.main                                              # 모의매매
cp .env.example .env && export $(cat .env | xargs)
python -m bot.main --live                                       # 실거래 (주의)
pytest                                                          # 테스트
```

## 주의
- 수익을 보장하지 않습니다. 반드시 백테스트 → 모의매매 → 소액 실거래 순으로 진행하세요.
- API 키는 출금 권한 OFF, IP 제한을 권장합니다. `.env`는 커밋 금지.
- 파라미터(`bot/risk.py`, `--fast/--slow`)는 직접 검증 후 조정하세요.
