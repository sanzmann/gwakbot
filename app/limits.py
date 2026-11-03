"""공개 운영용 사용량 제한.

누구나 쓸 수 있게 열면 한 사람이 계속 질문을 던져 무료 티어 한도를 태워버릴 수 있다.
그래서 IP 하나당, 그리고 전체적으로 하루에 받을 질문 수를 제한한다.

- 저장은 메모리에만 한다 (서버가 재시작되면 초기화). 개인정보(IP)를 파일에 남기지 않기 위해서다.
- 수치는 .env 로 조절한다.
"""
from __future__ import annotations

import os
import threading
from collections import defaultdict
from datetime import date, datetime, timedelta

from . import clock  # 한국 시간 기준 (서버는 UTC 로 돈다)


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


PER_IP_DAILY = _int_env("CHAT_LIMIT_PER_IP", 40)     # 한 사람이 하루에 보낼 수 있는 질문 수
TOTAL_DAILY = _int_env("CHAT_LIMIT_TOTAL", 1500)     # 전체 하루 질문 수
PER_IP_MINUTE = _int_env("CHAT_LIMIT_PER_MIN", 8)    # 연타 방지

_lock = threading.Lock()
_day = clock.today()
_per_ip: dict[str, int] = defaultdict(int)
_total = 0
_recent: dict[str, list[datetime]] = defaultdict(list)


class LimitExceeded(Exception):
    """사용자에게 그대로 보여줄 한국어 안내를 담는다."""


def _roll_over() -> None:
    global _day, _total
    today = clock.today()
    if today != _day:
        _day = today
        _per_ip.clear()
        _recent.clear()
        _total = 0


def check(ip: str) -> None:
    """질문 한 건을 기록한다. 한도를 넘으면 LimitExceeded."""
    global _total
    with _lock:
        _roll_over()
        now = clock.now()

        recent = [t for t in _recent[ip] if now - t < timedelta(minutes=1)]
        if len(recent) >= PER_IP_MINUTE:
            raise LimitExceeded("조금 빠르네요! 잠시 쉬었다가 다시 물어봐 주세요.")
        recent.append(now)
        _recent[ip] = recent

        if _per_ip[ip] >= PER_IP_DAILY:
            raise LimitExceeded(
                f"오늘은 질문을 {PER_IP_DAILY}번까지 받을 수 있어요. 내일 다시 찾아와 주세요!")
        if _total >= TOTAL_DAILY:
            raise LimitExceeded(
                "오늘 곽봇이 받을 수 있는 질문을 다 채웠어요. 내일 다시 이용해 주세요 😴")

        _per_ip[ip] += 1
        _total += 1


def status() -> dict:
    with _lock:
        _roll_over()
        return {"date": _day.isoformat(), "total_today": _total,
                "limits": {"per_ip": PER_IP_DAILY, "total": TOTAL_DAILY, "per_min": PER_IP_MINUTE}}
