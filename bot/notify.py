"""텔레그램 알림. 토큰/채팅ID는 .env 또는 환경변수에서 읽는다 (코드에 적지 않는다)."""
from __future__ import annotations
import os
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
            r = requests.post(API.format(token=self.token, method="sendMessage"),
                              json={"chat_id": self.chat, "text": text}, timeout=10)
            if r.status_code != 200:
                print(f"[텔레그램] 전송 실패 (HTTP {r.status_code})")
                return False
            return True
        except Exception as e:  # URL에 토큰이 들어 있어 메시지 대신 종류만 출력
            print(f"[텔레그램] 전송 실패 ({type(e).__name__})")
            return False


def find_chat_ids(token: str) -> list[tuple[int, str]]:
    """봇에게 먼저 보낸 메시지에서 채팅 ID를 찾는다."""
    r = requests.get(API.format(token=token, method="getUpdates"), timeout=10)
    r.raise_for_status()
    found = {}
    for u in r.json().get("result", []):
        chat = (u.get("message") or u.get("channel_post") or {}).get("chat")
        if chat:
            found[chat["id"]] = chat.get("first_name") or chat.get("title") or chat.get("username") or ""
    return list(found.items())
