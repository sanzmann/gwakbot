"""학생 제보 보관.

곽봇이 틀린 답을 했거나, 자료에 없는 걸 알려주고 싶을 때 받는 창구다.
공개 게시판이 아니라 운영자만 보는 목록이라, 신고 대응·욕설 관리 같은 부담 없이
"학생이 아는 것"을 모을 수 있다.

- 저장: reports/reports.jsonl (한 줄에 한 건). 깃에는 올리지 않는다.
- 개인정보는 받지 않는다 (IP·이름·학번 저장 안 함).
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "reports" / "reports.jsonl"

MAX_MESSAGE = 1000
MAX_CONTEXT = 600
RATE_LIMIT = 30          # 시간당 받을 최대 건수 (장난 방지)

_lock = threading.Lock()
_recent: list[datetime] = []

KINDS = {
    "correction": "틀린 정보",
    "missing": "없는 정보",
    "idea": "건의",
}


def _too_many() -> bool:
    now = datetime.now()
    _recent[:] = [t for t in _recent if now - t < timedelta(hours=1)]
    if len(_recent) >= RATE_LIMIT:
        return True
    _recent.append(now)
    return False


def add(kind: str, message: str, question: str = "", answer: str = "") -> dict:
    """제보 한 건 저장. 저장된 내용을 돌려준다."""
    if _too_many():
        raise RuntimeError("제보가 너무 많이 들어왔어요. 잠시 후 다시 시도해주세요.")

    item = {
        "id": datetime.now().strftime("%Y%m%d%H%M%S%f")[:18],
        "at": datetime.now().isoformat(timespec="seconds"),
        "kind": kind if kind in KINDS else "idea",
        "message": message.strip()[:MAX_MESSAGE],
        "question": question.strip()[:MAX_CONTEXT],
        "answer": answer.strip()[:MAX_CONTEXT],
        "done": False,
    }
    with _lock:
        STORE.parent.mkdir(parents=True, exist_ok=True)
        with STORE.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    return item


def all_items() -> list[dict]:
    if not STORE.exists():
        return []
    items = []
    for line in STORE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                items.append(json.loads(line))
            except ValueError:
                continue
    items.sort(key=lambda it: it["at"], reverse=True)
    return items


def mark_done(report_id: str, done: bool = True) -> bool:
    """처리 완료 표시. 파일을 통째로 다시 쓴다 (건수가 많지 않으므로 충분)."""
    with _lock:
        items = all_items()
        found = False
        for it in items:
            if it["id"] == report_id:
                it["done"] = done
                found = True
        if found:
            items.sort(key=lambda x: x["at"])
            STORE.write_text(
                "\n".join(json.dumps(it, ensure_ascii=False) for it in items) + "\n",
                encoding="utf-8", newline="\n")
        return found


def summary() -> dict:
    items = all_items()
    return {"total": len(items), "todo": sum(1 for it in items if not it["done"])}
