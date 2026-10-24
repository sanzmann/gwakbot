"""OpenStreetMap 자료로 캠퍼스 벡터 지도를 만든다 → static/campus_vector.json

학교가 제공하는 일러스트 지도는 그림이라 확대해도 더 자세해지지 않고, 편의점·흡연구역 같은
생활 정보도 없다. OSM 에는 건물 윤곽·길·운동장·편의시설이 좌표로 들어 있어서,
그걸 받아 화면에 직접 그릴 수 있는 형태(SVG 좌표)로 변환해 둔다.

실행: python -m app.osm_map
"""
from __future__ import annotations

import json
import math
import re
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "static" / "campus_vector.json"
BUILDINGS_JSON = ROOT / "static" / "campus_buildings.json"

# 공개 서버는 자주 붐벼서 여러 곳을 차례로 시도한다
OVERPASS_SERVERS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.osm.jp/api/interpreter",
]
HEADERS = {"User-Agent": "kwakbot/0.1 (+https://github.com/sanzmann/gwakbot)"}
BBOX = (37.6285, 127.0745, 37.6368, 127.0840)  # 남, 서, 북, 동 (캠퍼스 전체가 들어가도록 넉넉하게)
WIDTH = 1000  # 출력 SVG 가로 크기 (세로는 비율대로)

# 학교 지도의 건물 이름과 OSM 이름이 달라서 맞춰 주는 표
NAME_ALIASES = {
    "도서관/정보전산원": "중앙도서관",
    "도서관 별관": "중앙도서관 별관",
    "테크노큐브": "Techno Cube",
    "제1창업보육센터": "창업보육센터",
    "제1파워플랜트": "파워플랜트",
    "서울과학기술대 어린이집": "SeoulTech어린이집",
    "제1학생회관": "학생회관",
}

# 지도에 그릴 편의시설 (OSM 태그 → 표시 이름·아이콘)
POI_KINDS = {
    "convenience": ("편의점", "🏪"),
    "cafe": ("카페", "☕"),
    "restaurant": ("식당", "🍚"),
    "fast_food": ("패스트푸드", "🍔"),
    "bank": ("은행", "🏦"),
    "atm": ("ATM", "💳"),
    "post_office": ("우체국", "📮"),
    "clinic": ("보건진료소", "🏥"),
    "pharmacy": ("약국", "💊"),
    "library": ("도서관", "📚"),
    "books": ("서점", "📖"),
    "optician": ("안경점", "👓"),
    "smoking_area": ("흡연구역", "🚬"),
    "bus_stop": ("버스정류장", "🚌"),
    "bicycle_rental": ("따릉이", "🚲"),
    "car_sharing": ("카셰어링", "🚗"),
    "drinking_water": ("음수대", "🚰"),
    "toilets": ("화장실", "🚻"),
    "vending_machine": ("자판기", "🥤"),
}

# 윤곽선이 필요한 것(건물·길·면)과 점 하나로 찍히는 것(편의시설)은 출력 방식이 달라서 따로 받는다
QUERY_SHAPES = """
[out:json][timeout:180];
(
  way["building"]({bbox});
  way["highway"~"footway|path|pedestrian|service|residential|steps|living_street|tertiary|secondary"]({bbox});
  way["leisure"~"pitch|park|garden|track|playground"]({bbox});
  way["natural"="water"]({bbox});
  way["amenity"="parking"]({bbox});
);
out geom tags;
"""

QUERY_POIS = """
[out:json][timeout:180];
(
  nwr["amenity"]({bbox});
  nwr["shop"]({bbox});
  nwr["highway"="bus_stop"]({bbox});
);
out center tags;
"""


def _ask(query: str) -> list[dict]:
    body = query.format(bbox="{},{},{},{}".format(*BBOX))
    last = None
    for url in OVERPASS_SERVERS:
        try:
            r = requests.post(url, data={"data": body}, headers=HEADERS, timeout=300)
            r.raise_for_status()
            return r.json()["elements"]
        except Exception as e:
            print(f"  {url.split('/')[2]} 실패: {type(e).__name__}")
            last = e
    raise RuntimeError(f"Overpass 서버를 모두 시도했지만 실패했습니다: {last}")


def fetch() -> list[dict]:
    return _ask(QUERY_SHAPES) + _ask(QUERY_POIS)


class Projection:
    """위경도를 SVG 좌표로. 위도에 따라 가로가 줄어드는 것만 보정한 간단한 평면 투영."""

    def __init__(self, bbox: tuple[float, float, float, float], width: int):
        south, west, north, east = bbox
        self.west, self.north = west, north
        self.kx = math.cos(math.radians((south + north) / 2))
        self.scale = width / ((east - west) * self.kx)
        self.width = width
        self.height = round((north - south) * self.scale)

    def __call__(self, lat: float, lon: float) -> list[float]:
        x = (lon - self.west) * self.kx * self.scale
        y = (self.north - lat) * self.scale
        return [round(x, 1), round(y, 1)]


def _norm(name: str) -> str:
    return re.sub(r"[\s()]+", "", name).lower()


def _building_numbers() -> dict[str, str]:
    """학교 지도 자료의 건물 이름 → 번호"""
    if not BUILDINGS_JSON.exists():
        return {}
    data = json.loads(BUILDINGS_JSON.read_text(encoding="utf-8"))
    return {_norm(b["name"]): b["num"] for b in data.get("buildings", [])}


def build() -> dict:
    project = Projection(BBOX, WIDTH)
    numbers = _building_numbers()
    south, west, north, east = BBOX

    buildings, paths, areas, pois = [], [], [], []
    for el in fetch():
        tags = el.get("tags", {})
        geom = el.get("geometry")

        if geom and "building" in tags:
            name = tags.get("name", "")
            key = _norm(NAME_ALIASES.get(name, name))
            # 층수(없으면 높이에서 환산)를 받아 입체로 그릴 때 쓴다
            levels = tags.get("building:levels") or tags.get("building:levels:aboveground")
            try:
                levels = float(levels) if levels else None
            except ValueError:
                levels = None
            if levels is None and tags.get("height"):
                try:
                    levels = round(float(re.sub(r"[^\d.]", "", tags["height"])) / 3.3, 1)
                except ValueError:
                    levels = None
            buildings.append({
                "name": name,
                "num": numbers.get(key, ""),
                "levels": levels or 0,          # 0 이면 화면에서 기본값으로 처리
                "pts": [project(p["lat"], p["lon"]) for p in geom],
            })
            continue

        if geom and "highway" in tags and tags["highway"] != "bus_stop":
            paths.append({
                "kind": "foot" if tags["highway"] in ("footway", "path", "pedestrian", "steps") else "road",
                "pts": [project(p["lat"], p["lon"]) for p in geom],
            })
            continue

        if geom and ("leisure" in tags or tags.get("natural") == "water" or tags.get("amenity") == "parking"):
            kind = ("water" if tags.get("natural") == "water"
                    else "parking" if tags.get("amenity") == "parking"
                    else "pitch" if tags.get("leisure") in ("pitch", "track") else "green")
            areas.append({"kind": kind, "name": tags.get("name", ""),
                          "pts": [project(p["lat"], p["lon"]) for p in geom]})
            continue

        # 점 하나로 찍히는 편의시설
        kind = tags.get("amenity") or tags.get("shop") or tags.get("highway", "")
        if kind in POI_KINDS:
            center = el.get("center") or {"lat": el.get("lat"), "lon": el.get("lon")}
            if center.get("lat") is None:
                continue
            if not (south <= center["lat"] <= north and west <= center["lon"] <= east):
                continue
            label, icon = POI_KINDS[kind]
            pois.append({
                "kind": kind, "label": label, "icon": icon,
                "name": tags.get("name", ""),
                "pt": project(center["lat"], center["lon"]),
            })

    # 학교 건물이 있는 범위로 화면을 좁혀 캠퍼스가 꽉 차게 보이도록 한다
    campus = [b for b in buildings if b["num"]]   # 학교 건물로 확인된 것만 (주변 건물 제외)
    xs = [p[0] for b in campus for p in b["pts"]]
    ys = [p[1] for b in campus for p in b["pts"]]
    margin = 45
    focus = ([round(min(xs) - margin), round(min(ys) - margin),
              round(max(xs) - min(xs) + margin * 2), round(max(ys) - min(ys) + margin * 2)]
             if xs else [0, 0, project.width, project.height])

    return {
        "width": project.width,
        "height": project.height,
        "focus": focus,
        "collected": date.today().isoformat(),
        "source": "OpenStreetMap contributors (ODbL)",
        "buildings": buildings,
        "paths": paths,
        "areas": areas,
        "pois": pois,
    }


if __name__ == "__main__":
    data = build()
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8", newline="\n")
    matched = sum(1 for b in data["buildings"] if b["num"])
    print(f"건물 {len(data['buildings'])}개(번호 연결 {matched}) · 길 {len(data['paths'])} · "
          f"면 {len(data['areas'])} · 편의시설 {len(data['pois'])} → {OUT.name} "
          f"({OUT.stat().st_size // 1024}KB, {data['width']}x{data['height']})")
