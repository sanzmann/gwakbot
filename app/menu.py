"""식단 수집: 생활관(기숙사) 주간 식단표 + 교내 식당 판매 메뉴.

- 생활관: housing.seoultech.ac.kr/livng/dining (KB/성림/수림학사, 이번 주 날짜별 조·중·석식)
- 교내 식당: 학교가 Notion 으로 운영하는 ST:Table / ST:Dining 메뉴판 (브랜드·메뉴·가격)

주 단위로 바뀌므로 결과는 data/auto_menu.md (깃에 올리지 않음). 실행: python -m app.menu
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

log = logging.getLogger("kwakbot.menu")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUT = DATA_DIR / "auto_menu.md"
HEADERS = {"User-Agent": "Mozilla/5.0 (kwakbot; +https://github.com/sanzmann/gwakbot)"}
TIMEOUT = 20

DORM_URL = "https://housing.seoultech.ac.kr/livng/dining"
DORMS = [("kb", "KB학사 식당", "불암학사·KB학사·창명학사 사생"),
         ("sunglim", "성림학사 식당", "성림학사·누리학사 사생"),
         ("surim", "수림학사 식당", "수림학사 사생")]

# 학교 홈페이지 '식단' 페이지가 안내하는 Notion 메뉴판
NOTION_PAGE = "https://fern-magic-bde.notion.site/21e45244ac0a80fdb02ad064ce75d674"
NOTION_SPACE = "5a939ea0-b332-4365-96e0-413703544878"
NOTION_DBS = [("ST:Table (제1학생회관)", "22345244-ac0a-8062-86bd-000b564de5f4", "22345244-ac0a-807c-ad39-000c423759b5"),
              ("ST:Dining (제2학생회관)", "22345244-ac0a-801b-8ee1-000b50d50c14", "22345244-ac0a-8001-8c7e-000c2da02c00")]

_WEEK_RE = re.compile(r"\d{4}년\s*\d{1,2}월\s*\d{1,2}주")
_MEAL_RE = re.compile(r"(아침|점심|저녁)\s*:")


def _split_meals(text: str) -> list[tuple[str, str]]:
    """'아침 : ... 점심 : ... 저녁 : ...' 한 덩어리를 끼니별로 쪼갠다."""
    parts = _MEAL_RE.split(text)
    meals = []
    for name, body in zip(parts[1::2], parts[2::2]):
        body = re.sub(r"\s+", " ", body).strip(" ,")
        if body:
            meals.append((name, body))
    return meals


def fetch_dorm(foodtype: str) -> tuple[str, list[tuple[str, list[tuple[str, str]]]]]:
    """생활관 식당 한 곳의 이번 주 식단 → (주차 표기, [(날짜, [(끼니, 내용)])])"""
    r = requests.get(f"{DORM_URL}/?foodtype={foodtype}", headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")
    week_text = soup.find(string=_WEEK_RE)
    week = _WEEK_RE.search(week_text).group(0) if week_text else ""

    days = []
    table = soup.select_one("table.chang")
    for tr in (table.select("tr") if table else []):
        cells = tr.find_all(["th", "td"])
        if len(cells) < 3:
            continue
        day = " ".join(c.get_text(" ", strip=True) for c in cells[:2])
        meals = _split_meals(cells[2].get_text(" ", strip=True))
        if meals:
            days.append((day, meals))
    return week, days


def fetch_dorm_hours() -> list[str]:
    """식당 이용시간 표를 '- 구분 | 값 | ...' 줄로."""
    r = requests.get(DORM_URL, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")
    lines = []
    for label, table in zip(("학기 중", "방학 중"), soup.select("table.t-table")[:2]):
        lines.append(f"- [생활관(기숙사) 식당 {label}] 입장/퇴장 시간 (조식=아침, 중식=점심, 석식=저녁)")
        for tr in table.select("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
            cells = [c for c in cells if c]
            if len(cells) > 1:  # '학기' 같은 제목 한 칸짜리 행은 건너뜀
                lines.append("  - " + " | ".join(cells))
    return lines


def fetch_notion_menu(cid: str, vid: str) -> list[tuple[str, str, str]]:
    """Notion 메뉴판 DB → [(브랜드, 메뉴, 가격)]"""
    body = {
        "source": {"type": "collection", "id": cid, "spaceId": NOTION_SPACE},
        "collectionView": {"id": vid, "spaceId": NOTION_SPACE},
        "loader": {"reducers": {"collection_group_results": {"type": "results", "limit": 200}},
                   "searchQuery": "", "userTimeZone": "Asia/Seoul", "type": "reducer"},
    }
    r = requests.post("https://www.notion.so/api/v3/queryCollection", json=body,
                      headers={**HEADERS, "Content-Type": "application/json"}, timeout=TIMEOUT)
    r.raise_for_status()
    record_map = r.json()["recordMap"]
    collection = list(record_map["collection"].values())[0]["value"]["value"]
    schema = {k: v["name"] for k, v in collection["schema"].items()}

    rows = []
    for wrapper in record_map.get("block", {}).values():
        value = wrapper["value"]
        value = value["value"] if "value" in value else value
        props = value.get("properties") or {}
        if not props:
            continue
        row = {schema.get(k, k): " ".join(str(seg[0]) for seg in v).strip() for k, v in props.items()}
        name = row.get("이름") or row.get("메뉴") or ""
        price = re.sub(r"[^\d,]", "", row.get("가격", ""))
        brand = row.get("브랜드", "")
        if name and price and brand:  # 메뉴 항목이 아닌 페이지 블록 제외
            rows.append((brand, name, price))
    return rows


def refresh_menu() -> dict:
    now = datetime.now()
    lines = [
        "# 식단 (생활관 식당 주간 식단표 + 교내 식당 메뉴)",
        f"- 수집 시각: {now:%Y-%m-%d %H:%M}",
        "- 생활관 식단 출처: https://housing.seoultech.ac.kr/livng/dining (이번 주치만 제공됨)",
        f"- 교내 식당 메뉴판 출처: {NOTION_PAGE}",
        "- 생활관 식당은 해당 학사 사생만 이용 가능하며, 식자재 사정으로 식단이 바뀔 수 있음",
        "",
        "## 생활관(기숙사) 식당 이용시간 (조식/중식/석식)",
    ]
    summary = {"dorms": 0, "days": 0, "menus": 0}
    try:
        lines += fetch_dorm_hours()
    except Exception as e:
        log.warning("식당 이용시간 수집 실패: %s", e)
        lines.append("- (수집 실패)")

    for foodtype, title, who in DORMS:
        lines.append("")
        try:
            week, days = fetch_dorm(foodtype)
        except Exception as e:
            log.warning("%s 식단 수집 실패: %s", title, e)
            lines += [f"## {title} 식단", "- (수집 실패)"]
            continue
        lines.append(f"## {title} 식단 ({who}) — {week}")
        if not days:
            lines.append("- 이번 주 식단이 게시되지 않았습니다.")
        for day, meals in days:
            for meal, body in meals:
                lines.append(f"- {week} {day} {meal}: {body}")
            summary["days"] += 1
        summary["dorms"] += 1

    for title, cid, vid in NOTION_DBS:
        lines.append("")
        try:
            rows = fetch_notion_menu(cid, vid)
        except Exception as e:
            log.warning("%s 메뉴 수집 실패: %s", title, e)
            lines += [f"## {title} 판매 메뉴", "- (수집 실패)"]
            continue
        lines.append(f"## {title} 판매 메뉴 (브랜드 | 메뉴 | 가격)")
        for brand, name, price in rows:
            lines.append(f"- {title} {brand} | {name} | {price}원")
        summary["menus"] += len(rows)

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    log.info("식단 수집 완료: %s", summary)
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    print(refresh_menu())
