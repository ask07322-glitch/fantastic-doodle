# 코인 자동매매 봇

ccxt 기반(업비트·빗썸·바이낸스 등). **기본은 모의매매**이며, `--live`를 줘야 실거래합니다.

전략: 이동평균 골든크로스 매수(RSI<70 필터) / 데드크로스 매도 + 손절 -3%, 익절 +6%, 일일 손실 -5% 시 매수 중단.

```bash
pip install -r requirements.txt
python -m bot.main --backtest --symbol BTC/KRW --timeframe 1h   # 백테스트
python -m bot.main                                              # 모의매매
cp .env.example .env   # 윈도우: copy .env.example .env  (봇이 .env를 자동으로 읽습니다)
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

## 텔레그램 알림
`.env`에 `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`를 넣은 뒤:
```bash
python -m bot.main --telegram-test       # 테스트 메시지
python -m bot.main --check-signals       # 하루 1번: 신호가 바뀌면 알림 (첫 실행은 기준만 저장)
python -m bot.main --check-signals --summary   # 변경 없어도 현재 상태 전송
```
윈도우 작업 스케줄러에 `--check-signals`를 매일 09:10(업비트 일봉 마감 직후)에 걸어 두면 창을 켜 둘 필요가 없습니다.

## 자동 주문 (소액, 단계별)
```bash
python -m bot.main --api-check                 # 1) 키 점검: 잔고만 읽음(주문 없음)
python -m bot.main --test-order                # 2) 1만원 시험: 사고 바로 팖(ENABLE_LIVE=YES 필요)
python -m bot.main --auto-trade                # 3) 모의: 신호가 바뀌면 '했을 것'만 알림
python -m bot.main --auto-trade --live --budget 30000 --max-total 100000   # 4) 실제 주문
```
- 하루 1번(스케줄러 09:10) 실행. 신호가 **바뀐 코인만** 주문하고, 첫 실행은 기준만 저장합니다.
- 실제 주문은 `--live` **그리고** `.env`의 `ENABLE_LIVE=YES` 둘 다 있어야 합니다.
- 봇이 직접 산 수량만 팝니다. 주문이 실패하면 상태를 바꾸지 않아 다음 실행 때 재시도합니다.
