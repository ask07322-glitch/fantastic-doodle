"""텔레그램 알림. 토큰/채팅ID는 .env 또는 환경변수에서 읽는다 (코드에 적지 않는다)."""
from __future__ import annotations
import os
import time
import requests

API = "https://api.telegram.org/bot{token}/{method}"


def load_env(path: str = ".env") -> None:
    """.env 파일의 KEY=VALUE를 환경변수로 읽는다 (이미 있는 값은 덮어쓰지 않음)."""
    try:
        with open(path, encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except OSError:
        pass


def _call(fn, url, tries: int = 3, **kw):
    """느린 응답/일시적 연결 오류는 몇 번 다시 시도한다 (총 최대 3번, 각 20초)."""
    for i in range(tries):
        try:
            return fn(url, timeout=20, **kw)
        except (requests.Timeout, requests.ConnectionError):
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


def explain(e: Exception) -> str:
    """에러를 초보자도 알 수 있는 말로 (URL에 토큰이 있어 원문은 출력하지 않는다)."""
    if isinstance(e, requests.HTTPError) and e.response is not None:
        if e.response.status_code in (401, 404):
            return "토큰이 올바르지 않습니다. .env의 TELEGRAM_BOT_TOKEN을 다시 확인하세요(띄어쓰기/따옴표 없이)."
        return f"텔레그램 서버 오류 (HTTP {e.response.status_code})."
    if isinstance(e, (requests.Timeout, requests.ConnectionError)):
        return ("텔레그램 서버에 연결하지 못했습니다. 인터넷 연결, VPN/방화벽/회사·학교 네트워크, "
                "잠시 후 재시도를 확인하세요. (토큰 문제가 아닙니다)")
    return f"알 수 없는 오류 ({type(e).__name__})."


class Telegram:
    def __init__(self) -> None:
        self.token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        self.chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat)

    def send(self, text: str) -> bool:
        """성공하면 True. 실패해도 봇이 멈추지 않도록 예외는 삼키고, 토큰이 노출되지 않게 에러 종류만 출력."""
        if not self.enabled:
            return False
        try:
            r = _call(requests.post, API.format(token=self.token, method="sendMessage"),
                      json={"chat_id": self.chat, "text": text})
            if r.status_code != 200:
                print(f"[텔레그램] 전송 실패 (HTTP {r.status_code}) — 토큰/채팅ID를 확인하세요")
                return False
            return True
        except Exception as e:  # URL에 토큰이 들어 있어 원문 대신 설명만 출력
            print(f"[텔레그램] 전송 실패: {explain(e)}")
            return False


def find_chat_ids(token: str) -> list[tuple[int, str]]:
    """봇에게 먼저 보낸 메시지에서 채팅 ID를 찾는다."""
    r = _call(requests.get, API.format(token=token, method="getUpdates"))
    r.raise_for_status()
    found = {}
    for u in r.json().get("result", []):
        chat = (u.get("message") or u.get("channel_post") or {}).get("chat")
        if chat:
            found[chat["id"]] = chat.get("first_name") or chat.get("title") or chat.get("username") or ""
    return list(found.items())
