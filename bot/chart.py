"""백테스트 결과를 그림(PNG)으로 저장."""
from __future__ import annotations
import os, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from matplotlib import font_manager as _fm
_have = {f.name for f in _fm.fontManager.ttflist}
for _f in ("Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans CJK KR"):
    if _f in _have:  # 설치된 한글 폰트를 사용 (윈도우: 맑은 고딕)
        matplotlib.rcParams["font.family"] = _f
        break
matplotlib.rcParams["axes.unicode_minus"] = False

REASON = {"stop_loss": "손절", "take_profit": "익절", "signal": "신호"}


def save(df: pd.DataFrame, res: dict, fast: int, slow: int,
         title: str, path: str = "backtest.png") -> str:
    x = pd.to_datetime(df["ts"], unit="ms") if "ts" in df else df.index
    c = df["close"]
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(13, 8), sharex=True,
                                 gridspec_kw={"height_ratios": [3, 2]})
    a1.plot(x, c, color="#555", lw=1, label="가격")
    a1.plot(x, c.rolling(fast).mean(), color="#f5a623", lw=1, label=f"단기선({fast})")
    a1.plot(x, c.rolling(slow).mean(), color="#7b4bd0", lw=1, label=f"장기선({slow})")

    for t in res["trade_list"]:
        xi, p = x[t["i"]], t["price"]
        if t["side"] == "buy":
            a1.scatter(xi, p, marker="^", s=140, color="#e53935", zorder=5)
            a1.annotate("매수", (xi, p), textcoords="offset points",
                        xytext=(0, -20), ha="center", color="#e53935", fontsize=9)
        else:
            a1.scatter(xi, p, marker="v", s=140, color="#1e63d6", zorder=5)
            a1.annotate(f"매도\n{REASON.get(t['reason'], t['reason'])} {t['pnl_pct']:+.1f}%",
                        (xi, p), textcoords="offset points", xytext=(0, 14),
                        ha="center", color="#1e63d6", fontsize=9)
    a1.scatter([], [], marker="^", color="#e53935", label="매수")
    a1.scatter([], [], marker="v", color="#1e63d6", label="매도")
    a1.set_title(f"{title}\n봇 수익 {res['return_pct']:+.2f}%  |  그냥 들고 있었다면 "
                 f"{res['buy_hold_pct']:+.2f}%  |  거래 {res['trades']}번", fontsize=12)
    a1.set_ylabel("가격"); a1.legend(loc="upper left", ncol=5); a1.grid(alpha=.3)

    eq = pd.Series(res["equity_curve"], index=[x[i] for i in res["equity_index"]])
    a2.plot(eq.index, eq / res["start_cash"] * 100 - 100, color="#e53935", lw=1.5, label="봇")
    bh = c.loc[res["equity_index"][0]:] / c.iloc[res["equity_index"][0]] * 100 - 100
    a2.plot(x[res["equity_index"][0]:], bh, color="#888", lw=1, label="그냥 들고 있기")
    a2.axhline(0, color="k", lw=.5)
    a2.set_ylabel("수익률 (%)"); a2.set_xlabel("시간")
    a2.legend(loc="upper left"); a2.grid(alpha=.3)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return os.path.abspath(path)


def open_file(path: str) -> None:
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            os.system(f'open "{path}"')
    except Exception:
        pass
