"""학생 제보 보관.

곽봇이 틀린 답을 했거나, 자료에 없는 걸 알려주고 싶을 때 받는 창구다.
공개 게시판이 아니라 운영자만 보는 목록이라, 신고 대응·욕설 관리 같은 부담 없이
"학생이 아는 것"을 모을 수 있다.

- 저장: DATABASE_URL 이 있으면 Postgres(리뷰와 같은 데이터베이스), 없으면 reports/reports.jsonl.
  무료 호스팅의 디스크는 임시라서 파일로 두면 서버가 잠들었다 깨거나 다시 배포될 때 사라진다.
- 운영자가 '자료에 추가' 한 문장도 data/ 파일에 쓰는 것과 함께 데이터베이스에 남긴다.
  서버가 뜰 때 그 문장들을 data/ 파일에 다시 붙여 넣어, 재배포 뒤에도 답변에 반영된 채로 있다.
- 개인정보는 받지 않는다 (IP·이름·학번 저장 안 함).
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timedelta

from . import clock, reviewdb  # 한국 시간 기준 (서버는 UTC 로 돈다)
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "reports" / "reports.jsonl"
DATA_DIR = ROOT / "data"
STUDENT_FILE = "05_student_notes.md"   # 제보로 들어온 내용을 모으는 기본 파일

MAX_MESSAGE = 1000
MAX_CONTEXT = 600
RATE_LIMIT = 30          # 시간당 받을 최대 건수 (장난 방지)

log = logging.getLogger("kwakbot.reports")

_lock = threading.Lock()
_recent: list[datetime] = []

SCHEMA = """
create table if not exists reports (
    id       text primary key,
    at       timestamptz not null,
    kind     text not null,
    message  text not null,
    question text not null default '',
    answer   text not null default '',
    done     boolean not null default false
);
create table if not exists knowledge_notes (
    id    bigserial primary key,
    file  text not null,
    line  text not null,
    at    timestamptz not null default now()
);
"""

# 서버가 뜰 때 한 번 정해진다 (app/main.py 의 lifespan 에서 setup() 을 부른다)
_use_db = False

KINDS = {
    "correction": "틀린 정보",
    "missing": "없는 정보",
    "idea": "건의",
}


def _too_many() -> bool:
    now = clock.now()
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
        "id": clock.now().strftime("%Y%m%d%H%M%S%f")[:18],
        "at": clock.now().isoformat(timespec="seconds"),
        "kind": kind if kind in KINDS else "idea",
        "message": message.strip()[:MAX_MESSAGE],
        "question": question.strip()[:MAX_CONTEXT],
        "answer": answer.strip()[:MAX_CONTEXT],
        "done": False,
    }
    if _use_db:
        with reviewdb.connect() as conn, conn.cursor() as cur:
            cur.execute("""insert into reports (id, at, kind, message, question, answer, done)
                           values (%(id)s, %(at)s, %(kind)s, %(message)s, %(question)s, %(answer)s, %(done)s)""",
                        {**item, "at": item["at"] + "+09:00"})   # 한국 시간임을 밝혀 둔다 (DB 는 UTC)
        return item
    with _lock:
        STORE.parent.mkdir(parents=True, exist_ok=True)
        with STORE.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    return item


def all_items() -> list[dict]:
    if _use_db:
        with reviewdb.connect() as conn, conn.cursor() as cur:
            cur.execute("""select id, at, kind, message, question, answer, done
                           from reports order by at desc limit 500""")
            return [{"id": i, "at": at.astimezone(clock.KST).replace(tzinfo=None).isoformat(timespec="seconds"),
                     "kind": k, "message": m, "question": q, "answer": a, "done": d}
                    for i, at, k, m, q, a, d in cur.fetchall()]
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
    """처리 완료 표시. 파일이면 통째로 다시 쓴다 (건수가 많지 않으므로 충분)."""
    if _use_db:
        with reviewdb.connect() as conn, conn.cursor() as cur:
            cur.execute("update reports set done = %s where id = %s", (done, report_id))
            return cur.rowcount > 0
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


def knowledge_files() -> list[str]:
    """제보를 반영할 수 있는 자료 파일 목록 (자동 생성 파일 auto_* 는 제외)."""
    names = sorted(p.name for p in DATA_DIR.glob("*.md") if not p.name.startswith("auto_"))
    if STUDENT_FILE not in names:
        names.insert(0, STUDENT_FILE)
    return names


def append_knowledge(text: str, filename: str = STUDENT_FILE) -> Path:
    """운영자가 다듬은 내용을 자료 파일에 한 줄 추가한다. 서버 재시작 없이 바로 반영된다."""
    text = " ".join(text.split()).strip()
    if not text:
        raise ValueError("내용이 비어 있습니다.")
    if filename not in knowledge_files():
        raise ValueError("허용되지 않은 파일입니다.")

    line = f"- {text} (재학생 제보, {clock.now():%Y-%m-%d} 확인)"
    path = _write_line(filename, line)
    if _use_db:
        with reviewdb.connect() as conn, conn.cursor() as cur:
            cur.execute("insert into knowledge_notes (file, line) values (%s, %s)", (filename, line))
    return path


HEADER = (
    "# 재학생 제보 모음\n"
    "- 출처: 곽봇 제보함으로 들어온 재학생 제보를 운영자가 확인해 정리한 내용입니다.\n"
    "- 학교 홈페이지에 없는 현장 정보가 많으므로, 중요한 건 담당 부서 확인을 함께 안내하세요.\n\n"
)


def _write_line(filename: str, line: str) -> Path:
    path = DATA_DIR / filename
    with _lock:
        if not path.exists():
            path.write_text(HEADER, encoding="utf-8", newline="\n")
        with path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(line + "\n")
    return path


def _restore_notes() -> int:
    """데이터베이스에 남겨 둔 문장을 data/ 파일에 다시 붙인다. 이미 있는 줄은 건너뛴다."""
    with reviewdb.connect() as conn, conn.cursor() as cur:
        cur.execute("select file, line from knowledge_notes order by id")
        notes = cur.fetchall()
    added = 0
    for filename, line in notes:
        if "/" in filename or "\\" in filename or not filename.endswith(".md"):
            continue
        path = DATA_DIR / filename
        if path.exists() and line in path.read_text(encoding="utf-8").splitlines():
            continue
        _write_line(filename, line)
        added += 1
    return added


def setup() -> str:
    """제보 저장 위치를 정하고, 예전에 자료에 추가한 문장을 되살린다. (/health 에 표시)"""
    global _use_db
    _use_db = False
    if reviewdb.url():
        try:
            with reviewdb.connect() as conn, conn.cursor() as cur:
                cur.execute(SCHEMA)
            _use_db = True
            n = _restore_notes()
            log.info("제보를 데이터베이스에 보관합니다 (자료 %d줄 복원).", n)
        except Exception as e:
            log.error("제보 데이터베이스를 쓰지 못했습니다 (%s). 파일로 저장합니다.", e)
    return "database" if _use_db else "file(임시 — 서버 재시작 시 사라짐)"


def summary() -> dict:
    items = all_items()
    return {"total": len(items), "todo": sum(1 for it in items if not it["done"])}
