"""서울과기대 홈페이지에서 공지사항·학사일정을 긁어 data/auto_*.md 로 저장한다.

수동 실행: python -m app.scraper
서버는 시작 시 + 주기적으로 refresh_all() 을 호출한다.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

log = logging.getLogger("kwakbot.scraper")

BASE = "https://www.seoultech.ac.kr"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
HEADERS = {"User-Agent": "Mozilla/5.0 (kwakbot; +https://github.com/sanzmann/gwakbot)"}
TIMEOUT = 15

BOARDS = {
    "공지사항": f"{BASE}/service/info/notice/",
    "학사공지": f"{BASE}/service/info/matters/",
    "장학공지": f"{BASE}/service/info/janghak/",
    "취업공지": f"{BASE}/service/info/job/",
}
NOTICES_PER_BOARD = 15


def _get(url: str) -> BeautifulSoup:
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return BeautifulSoup(r.text, "lxml")


# ------------------------------------------------------------- 게시판

def _short_url(url: str) -> str:
    """검색·페이지 파라미터를 떼고 글 식별에 필요한 bnum/bidx 만 남긴다 (토큰 절약)."""
    u = urlparse(url)
    q = parse_qs(u.query)
    keep = {k: q[k][0] for k in ("do", "bnum", "bidx") if k in q}
    return f"{u.scheme}://{u.netloc}{u.path}?{urlencode(keep)}" if keep else url


def fetch_board(url: str, limit: int = NOTICES_PER_BOARD) -> list[dict]:
    """게시판 목록 첫 페이지. 표 열: [번호/공지, 제목, 첨부, 부서, 날짜, 조회]"""
    soup = _get(url)
    items = []
    for tr in soup.select("table tbody tr"):
        tds = tr.find_all("td")
        if len(tds) < 5:
            continue
        a = tds[1].find("a", href=True)  # 제목 칸의 링크만 (상단 미리보기 행의 '더보기' 제외)
        title = a.get_text(" ", strip=True) if a else ""
        if not title:
            continue
        items.append({
            "title": title,
            "dept": tds[3].get_text(strip=True),
            "date": tds[4].get_text(strip=True),
            "url": _short_url(urljoin(url, a["href"])),
            "pinned": not tds[0].get_text(strip=True).isdigit(),
        })
    return items[:limit]


def fetch_all_boards() -> dict[str, list[dict]]:
    result = {}
    for name, url in BOARDS.items():
        try:
            result[name] = fetch_board(url)
        except Exception as e:  # 한 게시판이 죽어도 나머지는 살린다
            log.warning("%s 수집 실패: %s", name, e)
            result[name] = []
    return result


def render_notices(boards: dict[str, list[dict]], fetched_at: datetime) -> str:
    lines = [
        "# 최근 공지사항 (학교 홈페이지 자동 수집)",
        f"- 수집 시각: {fetched_at:%Y-%m-%d %H:%M}",
        "- 각 게시판의 최신 글 제목만 담겨 있음. 자세한 내용은 링크로 안내할 것.",
        "",
    ]
    for name, items in boards.items():
        lines.append(f"## {name} ({BOARDS[name]})")
        if not items:
            lines.append("- (수집 실패)")
        for it in items:
            mark = "[고정] " if it["pinned"] else ""
            lines.append(f"- {it['date']} | {it['dept']} | {mark}{it['title']} | {it['url']}")
        lines.append("")
    return "\n".join(lines)


# ------------------------------------------------------------- 학사일정

def fetch_calendar(year: int, month: int) -> dict[str, list[tuple[str, str]]]:
    """typ=2: 1학기 전체, typ=3: 2학기 전체. (날짜, 내용) 목록."""
    out = {}
    for label, typ in (("1학기", 2), ("2학기", 3)):
        soup = _get(f"{BASE}/life/sch/common/?year={year}&mon={month}&typ={typ}")
        rows = []
        for tr in soup.select("table.schedule tbody tr"):
            tds = tr.find_all("td")
            if len(tds) >= 2:
                rows.append((tds[0].get_text(strip=True), tds[1].get_text(" ", strip=True)))
        out[label] = rows
    return out


def render_calendar(cal: dict[str, list[tuple[str, str]]], year: int, fetched_at: datetime) -> str:
    lines = [
        f"# {year}학년도 학부 학사일정 (학교 홈페이지 자동 수집)",
        f"- 수집 시각: {fetched_at:%Y-%m-%d %H:%M}",
        f"- 출처: {BASE}/life/sch/common/",
        "",
    ]
    for label, rows in cal.items():
        lines.append(f"## {label}")
        for date, text in rows:
            lines.append(f"- {date}: {text}")
        lines.append("")
    return "\n".join(lines)


# ------------------------------------------------------------- 진입점

def refresh_all() -> dict:
    """모든 자동 수집 자료를 갱신하고 결과 요약을 돌려준다."""
    now = datetime.now()
    boards = fetch_all_boards()
    (DATA_DIR / "auto_notices.md").write_text(render_notices(boards, now), encoding="utf-8", newline="
")

    cal_ok = True
    try:
        cal = fetch_calendar(now.year, now.month)
        (DATA_DIR / "auto_calendar.md").write_text(render_calendar(cal, now.year, now), encoding="utf-8", newline="
")
    except Exception as e:
        log.warning("학사일정 수집 실패: %s", e)
        cal_ok = False

    summary = {
        "fetched_at": now.isoformat(timespec="minutes"),
        "notices": {k: len(v) for k, v in boards.items()},
        "calendar": cal_ok,
    }
    log.info("자동 수집 완료: %s", summary)
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    print(refresh_all())
