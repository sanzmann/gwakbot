"""리뷰를 Postgres(Supabase)에 보관한다.

무료 호스팅의 디스크는 임시라서 서버가 다시 뜰 때마다 파일이 사라진다.
리뷰는 쌓여야 의미가 있으므로 DATABASE_URL 이 있으면 이쪽에 저장한다.
없거나 연결에 실패하면 app/reviews.py 가 파일 저장으로 되돌아간다.

연결은 요청마다 새로 연다. 리뷰는 많아야 분당 몇 건이라 이 정도로 충분하고,
연결 풀을 들고 있다가 끊긴 연결을 잡는 것보다 단순하다.
"""
from __future__ import annotations

import logging
import os

log = logging.getLogger("kwakbot.reviewdb")

SCHEMA = """
create table if not exists menu_reviews (
    id      text primary key,
    item    text not null,
    rating  real not null,
    comment text not null default '',
    client  text not null,
    at      timestamptz not null default now(),
    unique (item, client)
);
create index if not exists menu_reviews_item_idx on menu_reviews (item);
"""


def url() -> str:
    return os.getenv("DATABASE_URL", "").strip()


def _connect():
    import psycopg

    # Supabase 의 트랜잭션 풀러(6543 포트)는 prepared statement 를 지원하지 않는다
    return psycopg.connect(url(), prepare_threshold=None, connect_timeout=10)


def setup() -> bool:
    """표를 만들어 두고 연결이 되는지 확인한다. 쓸 수 있으면 True."""
    if not url():
        return False
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(SCHEMA)
        log.info("리뷰를 데이터베이스에 보관합니다.")
        return True
    except Exception as e:
        log.error("리뷰 데이터베이스에 연결하지 못했습니다 (%s). "
                  "파일로 저장하지만 서버가 다시 뜨면 사라집니다.", e)
        return False


def upsert(review: dict) -> None:
    """같은 사람이 같은 메뉴에 다시 남기면 이전 것을 대신한다."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """insert into menu_reviews (id, item, rating, comment, client, at)
               values (%(id)s, %(item)s, %(rating)s, %(comment)s, %(client)s, %(at)s)
               on conflict (item, client) do update
                 set id = excluded.id, rating = excluded.rating,
                     comment = excluded.comment, at = excluded.at""",
            review)


def remove(review_id: str) -> bool:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("delete from menu_reviews where id = %s", (review_id,))
        return cur.rowcount > 0


def stats() -> dict[str, dict]:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("select item, count(*), avg(rating) from menu_reviews group by item")
        return {item: {"count": n, "avg": round(float(avg), 2)}
                for item, n, avg in cur.fetchall()}


def for_item(item_id: str, limit: int = 30) -> list[dict]:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""select id, rating, comment, at from menu_reviews
                       where item = %s and comment <> '' order by at desc limit %s""",
                    (item_id, limit))
        return [{"id": i, "rating": float(r), "comment": c, "at": at.strftime("%Y-%m-%d")}
                for i, r, c, at in cur.fetchall()]


def mine(client: str) -> dict[str, float]:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("select item, rating from menu_reviews where client = %s", (client,))
        return {item: float(rating) for item, rating in cur.fetchall()}


def all_items() -> list[dict]:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""select id, item, rating, comment, client, at
                       from menu_reviews order by at desc limit 500""")
        return [{"id": i, "item": it, "rating": float(r), "comment": c, "client": cl,
                 "at": at.isoformat(timespec="seconds")}
                for i, it, r, c, cl, at in cur.fetchall()]


def summary() -> dict:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("select count(*), count(*) filter (where comment <> '') from menu_reviews")
        total, with_comment = cur.fetchone()
        return {"total": total, "with_comment": with_comment}
