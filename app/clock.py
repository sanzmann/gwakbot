"""한국 시간 기준 날짜·시각.

배포 서버(Render)는 UTC 로 돈다. `datetime.now()` 를 그대로 쓰면 한국시간 00~09시
사이에 서버는 아직 어제라고 생각해서, 아침에 '오늘 식단'을 물으면 어제 식단이 나오고
학사일정 D-day 도 하루씩 밀린다. 하필 아침 식단을 확인하는 시간대라 매일 터진다.

그래서 학생에게 보이는 날짜·시각은 전부 여기를 거친다.
서버가 어느 지역에서 돌든 결과가 같다.
"""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def now() -> datetime:
    """한국 시간 (timezone 정보는 떼고 돌려준다 — 기존 코드와 섞어 쓰기 위해)."""
    return datetime.now(KST).replace(tzinfo=None)


def today() -> date:
    return now().date()
