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

from .clock import KST

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
-- 한줄평에 누른 '도움돼요(1)' / '별로예요(-1)'. 한 사람이 한 한줄평에 하나
create table if not exists review_votes (
    review_id text not null,
    client    text not null,
    vote      smallint not null check (vote in (-1, 1)),
    at        timestamptz not null default now(),
    primary key (review_id, client)
);
"""


def url() -> str:
    return os.getenv("DATABASE_URL", "").strip()


def _connect():
    import psycopg

    # Supabase 의 트랜잭션 풀러(6543 포트)는 prepared statement 를 지원하지 않는다
    return psycopg.connect(url(), prepare_threshold=None, connect_timeout=10)


connect = _connect   # 제보함(app/reports.py)도 같은 데이터베이스를 쓴다


def setup() -> bool:
    """표를 만들어 두고 연결이 되는지 확인한다. 쓸 수 있으면 True."""
    if not url():
        return False
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(SCHEMA)
            # 2026-11-17 이전 버전은 한국 시각을 시간대 없이 넣어 UTC 로 저장됐다 (9시간 늦게 보임).
            # id 가 작성 시각(한국 시간, YYYYMMDDHHMMSS…)이므로 그걸로 바로잡는다. 맞는 줄은 건드리지 않는다
            cur.execute("""update menu_reviews
                           set at = to_timestamp(left(id, 14), 'YYYYMMDDHH24MISS')::timestamp at time zone 'Asia/Seoul'
                           where id ~ '^[0-9]{14}'
                             and abs(extract(epoch from at - (to_timestamp(left(id, 14), 'YYYYMMDDHH24MISS')::timestamp
                                                                at time zone 'Asia/Seoul'))) > 3600""")
            if cur.rowcount:
                log.info("리뷰 %d건의 작성 시각을 한국 시간으로 바로잡았습니다.", cur.rowcount)
        log.info("리뷰를 데이터베이스에 보관합니다.")
        return True
    except Exception as e:
        log.error("리뷰 데이터베이스에 연결하지 못했습니다 (%s). "
                  "파일로 저장하지만 서버가 다시 뜨면 사라집니다.", e)
        return False


def upsert(review: dict) -> None:
    """같은 사람이 같은 메뉴에 다시 남기면 이전 것을 대신한다.
    다시 쓴 한줄평은 다른 글이므로 이전 글에 받은 좋아요·싫어요는 지운다."""
    review = {**review, "at": review["at"] + "+09:00"}   # 한국 시간임을 밝혀 둔다 (DB 는 UTC)
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""delete from review_votes where review_id in
                       (select id from menu_reviews where item = %(item)s and client = %(client)s)""", review)
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
        gone = cur.rowcount > 0
        cur.execute("delete from review_votes where review_id = %s", (review_id,))
        return gone


def stats() -> dict[str, dict]:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("select item, count(*), avg(rating) from menu_reviews group by item")
        return {item: {"count": n, "avg": round(float(avg), 2)}
                for item, n, avg in cur.fetchall()}


def _kst_day(at) -> str:
    return at.astimezone(KST).strftime("%Y-%m-%d")


def for_item(item_id: str, client: str = "", limit: int = 30) -> list[dict]:
    """도움이 된 순(좋아요 − 싫어요), 같으면 최신순."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""select r.id, r.rating, r.comment, r.at, r.client = %(client)s,
                              count(v.vote) filter (where v.vote = 1),
                              count(v.vote) filter (where v.vote = -1),
                              coalesce(max(v.vote) filter (where v.client = %(client)s), 0)
                       from menu_reviews r left join review_votes v on v.review_id = r.id
                       where r.item = %(item)s and r.comment <> ''
                       group by r.id
                       order by coalesce(sum(v.vote), 0) desc, r.at desc
                       limit %(limit)s""",
                    {"client": client, "item": item_id, "limit": limit})
        return [{"id": i, "rating": float(r), "comment": c, "at": _kst_day(at), "mine": bool(me),
                 "up": up, "down": down, "my": int(my)}
                for i, r, c, at, me, up, down, my in cur.fetchall()]


def vote(review_id: str, client: str, value: int) -> dict:
    """좋아요(1)·싫어요(-1)·취소(0). 바뀐 수를 돌려준다. 남의 한줄평에만 누를 수 있다."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("select client from menu_reviews where id = %s", (review_id,))
        row = cur.fetchone()
        if not row:
            raise LookupError("없는 한줄평")
        if row[0] == client:
            raise PermissionError("내 한줄평")
        if value:
            cur.execute("""insert into review_votes (review_id, client, vote) values (%s, %s, %s)
                           on conflict (review_id, client) do update set vote = excluded.vote, at = now()""",
                        (review_id, client, value))
        else:
            cur.execute("delete from review_votes where review_id = %s and client = %s", (review_id, client))
        cur.execute("""select count(*) filter (where vote = 1), count(*) filter (where vote = -1)
                       from review_votes where review_id = %s""", (review_id,))
        up, down = cur.fetchone()
        return {"up": up, "down": down, "my": value}


def mine(client: str) -> dict[str, float]:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("select item, rating from menu_reviews where client = %s", (client,))
        return {item: float(rating) for item, rating in cur.fetchall()}


def all_items() -> list[dict]:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("""select id, item, rating, comment, client, at
                       from menu_reviews order by at desc limit 500""")
        return [{"id": i, "item": it, "rating": float(r), "comment": c, "client": cl,
                 "at": at.astimezone(KST).replace(tzinfo=None).isoformat(timespec="seconds")}
                for i, it, r, c, cl, at in cur.fetchall()]


def summary() -> dict:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("select count(*), count(*) filter (where comment <> '') from menu_reviews")
        total, with_comment = cur.fetchone()
        return {"total": total, "with_comment": with_comment}
