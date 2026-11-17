"""운영자 로그인: 채팅창에 `su -` 를 치고 비밀번호를 넣으면 관리자 모드가 된다.

예전엔 제보함 주소 끝에 `?token=...` 을 붙여 들어갔다. 그러면 비밀값이 브라우저 방문 기록,
서버 접속 기록에 그대로 남는다. 이제는 비밀번호를 한 번만 보내고, 맞으면 서명한 쿠키를 준다.

- 비밀번호: ADMIN_PASSWORD (없으면 ADMIN_TOKEN). 둘 다 없으면 로그인을 받지 않는다.
- 쿠키: "만료시각.서명". 서명 열쇠는 비밀번호에서 만들므로 비밀번호를 바꾸면 모든 로그인이 풀린다.
  HttpOnly(페이지 스크립트가 못 읽음) + SameSite=Strict(다른 사이트에서 보낸 요청엔 안 붙음).
- 무차별 대입 방지: 같은 IP 에서 15분에 5번 틀리면 잠시 막는다.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import threading
import time
from collections import defaultdict

COOKIE = "kwak_admin"
TTL = 12 * 3600                 # 로그인 유지 시간
FAIL_WINDOW = 15 * 60
FAIL_LIMIT = 5

_lock = threading.Lock()
_fails: dict[str, list[float]] = defaultdict(list)


class TooManyTries(Exception):
    pass


def password() -> str:
    return (os.getenv("ADMIN_PASSWORD") or os.getenv("ADMIN_TOKEN") or "").strip()


def enabled() -> bool:
    return bool(password())


def _key() -> bytes:
    return hashlib.sha256(("kwakbot-admin-cookie|" + password()).encode()).digest()


def _sign(exp: int) -> str:
    return hmac.new(_key(), str(exp).encode(), hashlib.sha256).hexdigest()


def issue() -> str:
    exp = int(time.time()) + TTL
    return f"{exp}.{_sign(exp)}"


def valid(cookie: str | None) -> bool:
    if not cookie or not enabled():
        return False
    exp, _, sig = cookie.partition(".")
    if not exp.isdigit() or int(exp) < time.time():
        return False
    return hmac.compare_digest(sig, _sign(int(exp)))


def login(given: str, ip: str) -> bool:
    """비밀번호가 맞으면 True. 너무 많이 틀렸으면 TooManyTries."""
    now = time.time()
    with _lock:
        recent = [t for t in _fails[ip] if now - t < FAIL_WINDOW]
        _fails[ip] = recent
        if len(recent) >= FAIL_LIMIT:
            raise TooManyTries
    ok = enabled() and hmac.compare_digest(given.encode(), password().encode())
    if not ok:
        with _lock:
            _fails[ip].append(now)
    else:
        with _lock:
            _fails.pop(ip, None)
    return ok
