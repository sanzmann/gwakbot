"""학교 홈페이지 캠퍼스지도(/intro/map)의 건물·시설·호실 정보를 data/14_campus_map.md 로 저장.

지도 페이지는 AJAX 로 채워지므로 같은 엔드포인트를 직접 호출한다.
  map_ajax.jsp           탭(건물별/대학/대학원/복지시설/행정지원)별 건물 마커
  building_info.jsp      건물 페이지: 층 목록 + '공통' 항목
  building_info_ajax.jsp 층별 호실 목록
실행: python -m app.campus_map
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE = "https://www.seoultech.ac.kr"
AJAX = f"{BASE}/site/www/intro/map/"
MAP_URL = f"{BASE}/intro/map/"
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUT = DATA_DIR / "14_campus_map.md"
# 채팅 화면이 지도를 그릴 때 쓰는 좌표 파일. 지도 이미지는 학교 서버 것을 그대로 링크한다
# (CORS 허용됨 — 복사본을 저장소에 두지 않아 항상 최신이고 재배포 문제도 없음)
MARKERS_OUT = ROOT / "static" / "campus_buildings.json"
MAP_IMAGE = f"{BASE}/common/images/campusmap/map_summer.jpg"
MAP_W, MAP_H = 900, 582  # 마커 좌표가 이 크기 기준
HEADERS = {"User-Agent": "Mozilla/5.0 (kwakbot; +https://github.com/sanzmann/gwakbot)", "Referer": MAP_URL}

TABS = ["대학", "대학원", "복지시설", "행정지원"]

# 학생이 찾을 만한 공간만 남긴다 (교수연구실·강의실·화장실 등 3천 개 중 대부분은 제외)
KEEP_ROOM = re.compile(
    r"사무실|행정실|센터|식당|매점|카페|편의점|열람실|자료실|은행|우체국|보건|상담|휴게|세미나|강당|회의실|"
    r"서점|문구|복사|학생회|동아리|라운지|프린트|증명|헬스|휘트니스|당구|탁구|안경|화방|미용|"
    r"학과|학부|전공|대학원|사감|경비|택배|무인|스터디|취업|창업|국제|교류|입학|교무|학생처|총장|"
    r"사무국|기획|홍보|발전기금|평생교육|어학|어린이집|도서관|전산|처$|과$|팀$|실장실|원장실|단$|본부"
)
DROP_ROOM = re.compile(r"교수연구실|미화원|사생실|공실|창고|기계실|전기실|준비실|입주기업")


def _get_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


_POS_RE = re.compile(r"left:\s*(\d+)px;\s*top:\s*(\d+)px")


def fetch_tab(s: requests.Session, name: str) -> list[tuple[str, str, str]]:
    """탭의 마커 목록 → [(건물id, 번호, 라벨)]"""
    return [(bid, num, label) for bid, num, label, _, _ in fetch_tab_full(s, name)]


def fetch_tab_full(s: requests.Session, name: str) -> list[tuple[str, str, str, int, int]]:
    """탭의 마커 목록 → [(건물id, 번호, 라벨, x, y)]. 좌표는 지도 이미지(900x582) 기준 핀 중심."""
    soup = BeautifulSoup(s.post(AJAX + "map_ajax.jsp", data={"building": name}, timeout=15).text, "lxml")
    out = []
    for a in soup.select("a.popup"):
        m = re.search(r"id=(\d+)", a.get("href", ""))
        img, badge = a.find("img"), a.find("span")
        if not (m and img):
            continue
        pos = _POS_RE.search((badge or img).get("style", ""))
        x, y = (int(pos.group(1)) + 10, int(pos.group(2)) + 10) if pos else (0, 0)
        out.append((m.group(1), badge.get_text(strip=True) if badge else "", img["alt"].strip(), x, y))
    return out


def fetch_building(s: requests.Session, bid: str) -> tuple[list[str], list[tuple[str, str]]]:
    """건물 페이지 → ('공통' 항목들, [(호실, 공간명)])"""
    html = s.get(AJAX + f"building_info.jsp?id={bid}", timeout=15).text
    soup = BeautifulSoup(html, "lxml")
    floors = [d.get_text(strip=True) for d in soup.select(".list1 div")]
    floors = [f for f in dict.fromkeys(floors) if f and f != "공통"]
    common = re.findall(r"<td style='text-align: center;'>-</td><td style='text-align: center;'>(.*?)</td>", html)

    rooms: list[tuple[str, str]] = []
    for floor in floors:
        r = s.post(AJAX + "building_info_ajax.jsp", data={"building": bid, "floor": floor}, timeout=15).text
        for tr in BeautifulSoup(r, "lxml").find_all("tr"):
            tds = [td.get_text(strip=True) for td in tr.find_all("td")]
            if len(tds) == 2 and (tds[0], tds[1]) not in rooms:
                rooms.append((tds[0], tds[1]))
    return common, rooms


def refresh_campus_map() -> dict:
    s = _get_session()
    buildings: dict[str, tuple[str, str]] = {}  # id -> (번호, 이름)
    markers: list[dict] = []
    for bid, num, name, x, y in fetch_tab_full(s, "건물별"):
        if bid in buildings:
            continue
        buildings[bid] = (num, name)
        markers.append({"num": num, "name": name, "x": x, "y": y})

    # 시설/부서 → 건물 (탭 정보)
    facilities: list[tuple[str, str, str]] = []  # (탭, 시설명, 건물표기)
    for tab in TABS:
        for bid, _, label in fetch_tab(s, tab):
            if bid in buildings:
                num, name = buildings[bid]
                facilities.append((tab, label, f"{name}({num}번)"))

    lines = [
        "# 캠퍼스 지도 (건물·시설 위치 안내)",
        f"- 출처: {MAP_URL}",
        f"- 수집일: {date.today().isoformat()}",
        f"- 캠퍼스 지도 보기: {MAP_URL} (건물 번호를 누르면 층별 호실 확인 가능)",
        "- 위치 질문에는 건물 이름과 번호를 함께 알려주고, 위 캠퍼스 지도 링크를 안내할 것",
        "",
        "## 건물 목록 (번호 - 이름 - 주요 입주 기관)",
    ]
    details: list[str] = []
    kept_rooms = 0
    for bid, (num, name) in sorted(buildings.items(), key=lambda kv: int(kv[1][0] or 0)):
        common, rooms = fetch_building(s, bid)
        lines.append(f"- {num}번 {name}" + (f": {', '.join(common)}" if common else ""))
        picked = [(rn, sp) for rn, sp in rooms if KEEP_ROOM.search(sp) and not DROP_ROOM.search(sp)]
        if picked:
            details.append(f"\n## {name} ({num}번) 주요 호실")
            details.extend(f"- {rn} {sp}" for rn, sp in picked)
            kept_rooms += len(picked)

    lines.append("\n## 시설·부서가 있는 건물")
    for tab, label, where in facilities:
        lines.append(f"- {label} ({tab}): {where}")

    OUT.write_text("\n".join(lines + details) + "\n", encoding="utf-8", newline="\n")

    # 시설명으로도 건물을 찾을 수 있게 별칭 추가 (예: "도서관" -> 34번)
    aliases: dict[str, str] = {}
    for _, label, where in facilities:
        m = re.search(r"\((\d+)번\)$", where)
        if m:
            aliases.setdefault(label, m.group(1))
    MARKERS_OUT.write_text(json.dumps({
        "image": MAP_IMAGE, "width": MAP_W, "height": MAP_H, "page": MAP_URL,
        "buildings": markers, "aliases": aliases,
    }, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")

    return {"buildings": len(buildings), "facilities": len(facilities), "rooms": kept_rooms,
            "markers": len(markers), "aliases": len(aliases)}


if __name__ == "__main__":
    print(refresh_campus_map())
