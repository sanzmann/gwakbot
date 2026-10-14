"""홈 화면에 보여줄 요약 정보를 data/auto_*.md 에서 뽑아 JSON 으로 만든다.

수집기(scraper, menu)가 만든 마크다운을 그대로 재활용한다 — 별도 저장소를 두지 않기 위해서다.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
WEEKDAYS = "월화수목금토일"

# "- 2026년 10월 2주 14일 수 점심: 나가사끼짬뽕, ..."
MENU_LINE = re.compile(r"^-\s+\S+년\s+\d+월\s+\d+주\s+(\d+)일\s+(\S)\s+(아침|점심|저녁):\s*(.+)$")
MENU_HEAD = re.compile(r"^##\s+(.+?)\s+식단\s*\((.+?)\)")
# "- 2026-10-14 | 학사지원과 | [고정] 제목 | https://..."
NOTICE_LINE = re.compile(r"^-\s+(\d{4}-\d{2}-\d{2})\s*\|\s*([^|]*)\|\s*([^|]+)\|\s*(https?://\S+)$")
# "- [학부] 2026.10.16 ~ 10.16: 제1차 졸업종합시험 시행(대학)"
CAL_LINE = re.compile(r"^-\s+\[(학부|대학원)\]\s+(\d{4})\.(\d{2})\.(\d{2})\s*~\s*([\d.]+):\s*(.+)$")

SHORTCUTS = [
    {"label": "수강신청", "url": "https://for-s.seoultech.ac.kr", "icon": "📝"},
    {"label": "학생포탈", "url": "https://stportal.seoultech.ac.kr", "icon": "🎓"},
    {"label": "통합정보시스템", "url": "https://suis.seoultech.ac.kr", "icon": "📋"},
    {"label": "학사일정", "url": "https://www.seoultech.ac.kr/life/sch/common/", "icon": "📅"},
    {"label": "공지사항", "url": "https://www.seoultech.ac.kr/service/info/notice/", "icon": "📢"},
    {"label": "도서관", "url": "https://library.seoultech.ac.kr", "icon": "📚"},
    {"label": "캠퍼스 지도", "url": "https://www.seoultech.ac.kr/intro/map/", "icon": "🗺"},
    {"label": "생활관", "url": "https://housing.seoultech.ac.kr", "icon": "🏠"},
]


def _read(name: str) -> list[str]:
    path = DATA_DIR / name
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def today_menu(today: date | None = None) -> list[dict]:
    """오늘 날짜에 해당하는 생활관 식당 식단 → [{식당, 대상, meals: {끼니: 내용}}]"""
    today = today or date.today()
    out: list[dict] = []
    current: dict | None = None
    for line in _read("auto_menu.md"):
        head = MENU_HEAD.match(line)
        if head:
            current = {"name": head.group(1), "who": head.group(2), "meals": {}}
            out.append(current)
            continue
        m = MENU_LINE.match(line)
        if m and current is not None and int(m.group(1)) == today.day:
            current["meals"][m.group(3)] = m.group(4).strip()
    return [c for c in out if c["meals"]]


def recent_notices(limit: int = 6) -> list[dict]:
    """게시판별 최신 글을 날짜순으로 합쳐서 반환."""
    board = ""
    items: list[dict] = []
    for line in _read("auto_notices.md"):
        if line.startswith("## "):
            board = line[3:].split(" (")[0].strip()
            continue
        m = NOTICE_LINE.match(line)
        if m:
            title = m.group(3).strip()
            items.append({
                "board": board,
                "date": m.group(1),
                "dept": m.group(2).strip(),
                "title": title.replace("[고정] ", ""),
                "pinned": title.startswith("[고정]"),
                "url": m.group(4),
            })
    items.sort(key=lambda it: it["date"], reverse=True)
    return items[:limit]


def upcoming_schedule(limit: int = 6, today: date | None = None) -> list[dict]:
    """오늘 이후로 가장 가까운 학부 학사일정."""
    today = today or date.today()
    items = []
    for line in _read("auto_calendar.md"):
        m = CAL_LINE.match(line)
        if not m or m.group(1) != "학부":
            continue
        try:
            start = date(int(m.group(2)), int(m.group(3)), int(m.group(4)))
        except ValueError:
            continue
        if start < today:
            continue
        items.append({
            "date": start.isoformat(),
            "month": start.month,
            "day": start.day,
            "weekday": WEEKDAYS[start.weekday()],
            "dday": (start - today).days,
            "title": m.group(6).strip(),
        })
    items.sort(key=lambda it: it["date"])
    # 같은 날 같은 제목이 1·2학기 양쪽에 있을 수 있으므로 중복 제거
    seen, unique = set(), []
    for it in items:
        key = (it["date"], it["title"])
        if key not in seen:
            seen.add(key)
            unique.append(it)
    return unique[:limit]


def collected_at() -> str:
    for line in _read("auto_notices.md"):
        if line.startswith("- 수집 시각:"):
            return line.split(":", 1)[1].strip()
    return ""


def home_summary() -> dict:
    today = date.today()
    return {
        "today": today.isoformat(),
        "weekday": WEEKDAYS[today.weekday()],
        "collected_at": collected_at(),
        "menu": today_menu(today),
        "notices": recent_notices(),
        "schedule": upcoming_schedule(today=today),
        "shortcuts": SHORTCUTS,
    }


if __name__ == "__main__":
    import json

    print(json.dumps(home_summary(), ensure_ascii=False, indent=1)[:2000])
