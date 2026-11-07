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

## 큰 흐름 따라 보유 (trend-hold, 일봉)
```bash
python -m bot.main --compare-trend                         # 일봉 5년+: trend100/trend200 vs 그냥 보유
python -m bot.main --backtest --strategy trend200          # 그림으로 보기 (기본 1d)
```
장기 평균선 위면 전액 보유, 아래면 현금. 목표는 보유보다 더 버는 것이 아니라 큰 하락을 피하는 것(최대낙폭↓).

```bash
python -m bot.main --status                                    # 지금 평균선 위(보유)/아래(현금)?
python -m bot.main --strategy trend200 --position 0.1          # 모의매매, 현금의 10%만 사용
python -m bot.main --strategy trend200 --position 0.1 --live --interval 3600   # 실거래(소액!)
```
실거래는 봇이 직접 산 수량만 팝니다(`state.json`에 기록). 계좌에 원래 있던 코인은 건드리지 않습니다.
시작 시 이미 평균선 위라면 바로 매수합니다.
