"""교내 식당 메뉴 별점·한줄평.

제1·2학생회관(ST:Table / ST:Dining) 메뉴 한 가지마다 별점(0.5~5.0, 0.5 간격)과
한 줄 평을 남길 수 있다. 메뉴 id 는 app/menu.py 의 menu_item_id() 가 만든다.

- 저장: DATABASE_URL 이 있으면 Postgres(app/reviewdb.py), 없으면 reviews/reviews.jsonl.
  무료 호스팅의 디스크는 임시라서 파일로 두면 서버가 다시 뜰 때 리뷰가 사라진다.
- 로그인이 없으므로 '내 리뷰' 는 브라우저가 만든 임의의 client id 로 구분한다.
  IP 로 구분하면 학교 와이파이처럼 여럿이 한 IP 를 쓰는 곳에서 한 명만 쓰고 막혀버린다.
  대신 IP 는 장난 방지용 속도 제한에만 쓰고 저장하지 않는다.
- 한 사람(client)이 한 메뉴에 남기는 리뷰는 하나. 다시 남기면 덮어쓴다.
"""
from __future__ import annotations

import json
import re
import threading
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

from . import clock, reviewdb  # 한국 시간 기준 (서버는 UTC 로 돈다)

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "reviews" / "reviews.jsonl"

MAX_COMMENT = 80          # 한줄평이니까 짧게
RATINGS = [round(0.5 * i, 1) for i in range(1, 11)]   # 0.5 ~ 5.0
PER_IP_HOURLY = 20        # 같은 IP 에서 시간당 받을 리뷰 수 (공용 와이파이를 감안해 넉넉히)

# 아주 거친 금칙어 거르개. 이걸로 다 막히지는 않으므로 운영자가 지울 수 있게 해 둔다.
BANNED = re.compile(r"시발|씨발|병신|새끼|좆|지랄|엠창|개새|썅|ㅄ|ㅅㅂ|ㅆㅂ|ㅂㅅ")

_lock = threading.Lock()
_recent: dict[str, list] = defaultdict(list)

# 서버가 뜰 때 한 번 정해진다 (app/main.py 의 lifespan 에서 setup() 을 부른다)
_use_db = False


def setup() -> str:
    """리뷰 저장 위치를 정한다. 어디에 저장하는지 돌려준다 (/health 에 표시)."""
    global _use_db
    _use_db = reviewdb.setup()
    return "database" if _use_db else "file(임시 — 서버 재시작 시 사라짐)"


class ReviewError(Exception):
    """사용자에게 그대로 보여줄 한국어 안내."""


def _load() -> list[dict]:
    if not STORE.exists():
        return []
    out = []
    for line in STORE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def _save(items: list[dict]) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(json.dumps(it, ensure_ascii=False) for it in items)
    STORE.write_text(body + "\n" if body else "", encoding="utf-8", newline="\n")


def _check_rate(ip: str) -> None:
    now = clock.now()
    recent = [t for t in _recent[ip] if now - t < timedelta(hours=1)]
    if len(recent) >= PER_IP_HOURLY:
        raise ReviewError("리뷰가 너무 많이 들어왔어요. 잠시 후 다시 시도해 주세요.")
    recent.append(now)
    _recent[ip] = recent


def add(item_id: str, rating: float, comment: str, client: str, ip: str) -> dict:
    """별점·한줄평 한 건 저장. 같은 사람이 같은 메뉴에 다시 남기면 덮어쓴다."""
    try:
        rating = round(float(rating) * 2) / 2
    except (TypeError, ValueError):
        raise ReviewError("별점을 다시 선택해 주세요.")
    if rating not in RATINGS:
        raise ReviewError("별점은 0.5점부터 5점까지 0.5점 간격으로 줄 수 있어요.")

    comment = " ".join(comment.split())[:MAX_COMMENT]
    if BANNED.search(comment):
        raise ReviewError("한줄평에 쓸 수 없는 표현이 있어요.")
    if not item_id or not client:
        raise ReviewError("잘못된 요청이에요.")

    with _lock:
        _check_rate(ip)
        now = clock.now()
        review = {
            "id": now.strftime("%Y%m%d%H%M%S%f")[:18],
            "item": item_id,
            "rating": rating,
            "comment": comment,
            "client": client,
            "at": now.isoformat(timespec="seconds"),
        }
        if _use_db:
            reviewdb.upsert(review)
        else:
            # 같은 사람이 같은 메뉴에 남긴 기존 리뷰는 치운다
            items = [it for it in _load()
                     if not (it["item"] == item_id and it["client"] == client)]
            items.append(review)
            _save(items)
    return review


def remove(review_id: str) -> bool:
    """운영자가 부적절한 리뷰를 지운다."""
    if _use_db:
        return reviewdb.remove(review_id)
    with _lock:
        items = _load()
        kept = [it for it in items if it["id"] != review_id]
        if len(kept) == len(items):
            return False
        _save(kept)
        return True


def stats() -> dict[str, dict]:
    """메뉴 id → {count, avg}. 화면에서 별점 평균을 보여줄 때 쓴다."""
    if _use_db:
        return reviewdb.stats()
    out: dict[str, dict] = {}
    for it in _load():
        s = out.setdefault(it["item"], {"count": 0, "sum": 0.0})
        s["count"] += 1
        s["sum"] += it["rating"]
    return {k: {"count": v["count"], "avg": round(v["sum"] / v["count"], 2)}
            for k, v in out.items()}


def for_item(item_id: str, limit: int = 30) -> list[dict]:
    """한 메뉴에 달린 리뷰를 최신순으로. 한줄평이 없는 건(별점만) 빼고 보여준다."""
    if _use_db:
        return reviewdb.for_item(item_id, limit)
    items = [it for it in _load() if it["item"] == item_id and it["comment"]]
    items.sort(key=lambda it: it["at"], reverse=True)
    return [{"id": it["id"], "rating": it["rating"], "comment": it["comment"],
             "at": it["at"][:10]} for it in items[:limit]]


def mine(client: str) -> dict[str, float]:
    """이 사람이 남긴 메뉴별 별점 (화면에서 '내 별점' 으로 표시)."""
    if _use_db:
        return reviewdb.mine(client)
    return {it["item"]: it["rating"] for it in _load() if it["client"] == client}


def all_items() -> list[dict]:
    """운영자 화면용 전체 목록 (최신순)."""
    if _use_db:
        return reviewdb.all_items()
    items = _load()
    items.sort(key=lambda it: it["at"], reverse=True)
    return items


def summary() -> dict:
    if _use_db:
        return reviewdb.summary()
    items = _load()
    return {"total": len(items), "with_comment": sum(1 for it in items if it["comment"])}
