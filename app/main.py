"""FastAPI 서버: 정적 채팅 UI + SSE 스트리밍 채팅 API."""
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import os
from html import escape
from urllib.parse import urlencode

from . import admin, canned, home, limits, providers, reports, reviews, scraper
from .bot import stream_reply

log = logging.getLogger("kwakbot")


def _token_qs(request: Request) -> str:
    token = request.query_params.get("token", "")
    return f"?token={token}" if token else ""
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

# 개인용 단계의 여유 있는 제한. 공개 전환 시 줄일 것.
MAX_MESSAGE_CHARS = 2000
MAX_HISTORY_TURNS = 4  # user+assistant 쌍 기준. Groq 무료 티어 토큰 한도 때문에 짧게
REFRESH_INTERVAL_SEC = 6 * 60 * 60  # 공지·학사일정 재수집 주기

# 평소에는 서버가 학교 홈페이지를 긁지 않는다.
# 무료 호스팅은 15분마다 잠들고 방문자가 올 때 깨어나는데, 깰 때마다 긁으면
# 공지가 하루 몇 건 올라오지 않는데도 학교 서버에 하루 1,000번 넘게 요청하게 된다.
# 대신 GitHub Actions 가 하루 두 번 긁어 data/auto_*.md 를 저장소에 커밋하고,
# 그 커밋이 재배포를 일으켜 최신 자료가 반영된다 (.github/workflows/collect.yml).
# 직접 돌려보고 싶을 때는 SCRAPE_ON_START=1 로 켠다.
SCRAPE_ON_START = os.getenv("SCRAPE_ON_START", "").strip() in ("1", "true", "yes")

last_refresh: dict = {}


def _collected_at() -> str:
    """깃에 담겨온 자료의 수집 시각 (auto_notices.md 첫머리에 적혀 있다)."""
    path = Path(__file__).resolve().parent.parent / "data" / "auto_notices.md"
    try:
        for line in path.read_text(encoding="utf-8").splitlines()[:5]:
            if "수집 시각" in line:
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return ""


async def _refresh_loop():
    global last_refresh
    while True:
        try:
            last_refresh = await asyncio.to_thread(scraper.refresh_all)
        except Exception as e:  # 수집 실패해도 서버는 계속 뜬다 (기존 파일 사용)
            log.warning("자동 수집 실패: %s", e)
        await asyncio.sleep(REFRESH_INTERVAL_SEC)


review_store = "?"
report_store = "?"


@asynccontextmanager
async def lifespan(_: FastAPI):
    global last_refresh, review_store, report_store
    review_store = await asyncio.to_thread(reviews.setup)
    report_store = await asyncio.to_thread(reports.setup)
    if not SCRAPE_ON_START:
        last_refresh = {"source": "github-actions", "collected_at": _collected_at()}
        log.info("자료는 저장소에 담겨온 것을 씁니다 (수집 시각 %s)", last_refresh["collected_at"])
        yield
        return
    task = asyncio.create_task(_refresh_loop())
    yield
    task.cancel()


app = FastAPI(title="곽봇", version="0.3.0", lifespan=lifespan)


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)


class ReviewRequest(BaseModel):
    item: str = Field(min_length=1, max_length=40)
    rating: float = Field(ge=0.5, le=5.0)
    comment: str = Field(default="", max_length=reviews.MAX_COMMENT)
    client: str = Field(min_length=8, max_length=40)


class VoteRequest(BaseModel):
    client: str = Field(min_length=8, max_length=40)
    vote: int = Field(ge=-1, le=1)      # 1 도움돼요 · -1 별로예요 · 0 취소


class ReportRequest(BaseModel):
    kind: str = Field(default="idea", max_length=20)
    message: str = Field(min_length=2, max_length=reports.MAX_MESSAGE)
    question: str = Field(default="", max_length=reports.MAX_CONTEXT)
    answer: str = Field(default="", max_length=reports.MAX_CONTEXT)


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/health")
async def health():
    return {"ok": True, "llm": providers.describe(), "last_refresh": last_refresh,
            "usage": limits.status(), "reviews": review_store, "reports": report_store}


@app.get("/api/home")
async def home_summary():
    """홈 화면 카드에 쓸 요약 (오늘 식단·최근 공지·다가오는 일정·바로가기)."""
    return home.home_summary()


@app.get("/api/menu")
async def menu_items(client: str = ""):
    """교내 식당(제1·2학생회관) 판매 메뉴 + 별점 평균. 리뷰 화면이 쓴다."""
    return {"halls": home.menu_halls(), "stats": reviews.stats(),
            "mine": reviews.mine(client) if client else {}}


@app.get("/api/menu/{item_id}/reviews")
async def menu_reviews(item_id: str, client: str = ""):
    """한줄평 목록 (도움이 된 순). client 를 주면 내 글인지·내가 누른 표시도 함께 준다."""
    return {"reviews": await asyncio.to_thread(reviews.for_item, item_id, client[:40])}


@app.post("/api/menu/review/{review_id}/vote")
async def vote_review(review_id: str, req: VoteRequest, request: Request):
    """남의 한줄평에 '도움돼요' / '별로예요'. 같은 걸 다시 누르면 취소(0)."""
    try:
        return await asyncio.to_thread(reviews.vote, review_id, req.client, req.vote, _client_ip(request))
    except reviews.ReviewError as e:
        raise HTTPException(400, str(e))


@app.post("/api/menu/review")
async def add_review(req: ReviewRequest, request: Request):
    """별점·한줄평 등록. 같은 사람이 같은 메뉴에 다시 남기면 덮어쓴다."""
    try:
        reviews.add(req.item, req.rating, req.comment, req.client, _client_ip(request))
    except reviews.ReviewError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "stats": reviews.stats().get(req.item, {"count": 0, "avg": 0})}


@app.post("/api/report")
async def create_report(req: ReportRequest):
    """학생 제보 접수. 공개되지 않고 운영자만 본다."""
    try:
        item = await asyncio.to_thread(reports.add, req.kind, req.message, req.question, req.answer)
    except RuntimeError as e:
        raise HTTPException(429, str(e))
    except Exception as e:
        log.error("제보 저장 실패: %s", e)
        raise HTTPException(503, "제보를 저장하지 못했어요. 잠시 후 다시 시도해 주세요.")
    log.info("제보 접수: %s %s", item["kind"], item["message"][:40])
    return {"ok": True}


def _is_admin(request: Request) -> bool:
    return admin.valid(request.cookies.get(admin.COOKIE))


def _check_admin(request: Request) -> None:
    """운영자 화면 보호: 채팅창 `su -` 로 받은 쿠키, 또는 주소의 토큰.
    둘 다 설정이 없으면 내 컴퓨터에서만 허용."""
    if _is_admin(request):
        return
    token = os.getenv("ADMIN_TOKEN", "")
    if token:
        if request.query_params.get("token") != token:
            raise HTTPException(404, "not found")
        return
    if (request.client.host if request.client else "") not in ("127.0.0.1", "::1"):
        raise HTTPException(404, "not found")


@app.get("/admin/reports", response_class=HTMLResponse)
async def admin_reports(request: Request, saved: str = ""):
    _check_admin(request)
    items = reports.all_items()
    files = reports.knowledge_files()
    qs = _token_qs(request)

    def file_options(selected: str = reports.STUDENT_FILE) -> str:
        return "".join(
            f"<option value='{escape(f)}'{' selected' if f == selected else ''}>{escape(f)}</option>"
            for f in files)

    rows = []
    for it in items:
        ctx = ""
        if it["question"]:
            ctx = (f"<div class=ctx><b>질문</b> {escape(it['question'])}"
                   f"<br><b>답변</b> {escape(it['answer'][:300])}</div>")
        # 제보 내용을 그대로 담아둔 수정칸 — 다듬어서 바로 자료에 넣는다
        editor = (
            f"<form class=apply method=post action='/admin/reports/{it['id']}/apply{qs}'>"
            f"<textarea name=text rows=3 placeholder='자료에 넣을 문장으로 다듬어 주세요'>"
            f"{escape(it['message'])}</textarea>"
            f"<div class=applyrow><select name=target>{file_options()}</select>"
            f"<button class=primary>자료에 추가</button></div></form>")
        rows.append(
            f"<li class={'done' if it['done'] else 'todo'}>"
            f"<div class=meta>{it['at']} · {reports.KINDS.get(it['kind'], it['kind'])}"
            f"<form method=post action='/admin/reports/{it['id']}/toggle{qs}'>"
            f"<button>{'되돌리기' if it['done'] else '처리함'}</button></form></div>"
            f"<div class=msg>{escape(it['message'])}</div>{ctx}{editor}</li>")

    direct = (
        f"<form class='apply direct' method=post action='/admin/knowledge{qs}'>"
        f"<textarea name=text rows=2 placeholder='제보와 무관하게 직접 추가할 내용'></textarea>"
        f"<div class=applyrow><select name=target>{file_options()}</select>"
        f"<button class=primary>자료에 추가</button></div></form>")
    banner = f"<p class=saved>✓ {escape(saved)} 에 추가했어요. 바로 답변에 반영됩니다.</p>" if saved else ""
    s = reports.summary()
    return f"""<!DOCTYPE html><html lang=ko><head><meta charset=utf-8>
<title>곽봇 제보함</title><style>
body{{font-family:-apple-system,'Malgun Gothic',sans-serif;max-width:760px;margin:24px auto;padding:0 16px;color:#1b2230}}
h1{{font-size:20px}} ul{{list-style:none;padding:0}}
li{{border:1px solid #e2e7ef;border-radius:12px;padding:12px 14px;margin:10px 0}}
li.done{{opacity:.5}} .meta{{display:flex;gap:10px;align-items:center;font-size:12px;color:#6b7687}}
.meta form{{margin-left:auto}} .msg{{margin-top:6px;white-space:pre-wrap}}
.ctx{{margin-top:8px;font-size:12.5px;color:#6b7687;background:#f5f7fb;border-radius:8px;padding:8px 10px}}
button{{font-size:12px;padding:4px 10px;border:1px solid #cfd7e3;background:#fff;border-radius:999px;cursor:pointer}}
button.primary{{background:#1f6feb;border-color:#1f6feb;color:#fff;padding:6px 14px}}
.apply{{margin-top:10px}}
.apply textarea{{width:100%;padding:9px 11px;border:1px solid #cfd7e3;border-radius:10px;
  font-size:13.5px;font-family:inherit;resize:vertical;box-sizing:border-box}}
.applyrow{{display:flex;gap:8px;margin-top:6px;align-items:center}}
.applyrow select{{flex:1;padding:6px 8px;border:1px solid #cfd7e3;border-radius:8px;font-size:12.5px;font-family:inherit}}
.direct{{border:1px dashed #cfd7e3;border-radius:12px;padding:12px 14px;margin-bottom:14px}}
.saved{{background:#e7f6ec;border:1px solid #b7e3c6;color:#1c6b3a;border-radius:10px;padding:9px 12px;font-size:13px}}
h2{{font-size:14px;color:#6b7687;margin:18px 0 6px}}
</style></head><body><h1>곽봇 제보함</h1>
<p>전체 {s['total']}건 · 처리 안 함 {s['todo']}건</p>
{banner}
<h2>직접 추가</h2>
{direct}
<h2>제보</h2>
<ul>{''.join(rows) or '<li>아직 제보가 없어요.</li>'}</ul></body></html>"""


@app.post("/admin/reports/{report_id}/toggle")
async def toggle_report(report_id: str, request: Request):
    _check_admin(request)
    items = {it["id"]: it for it in reports.all_items()}
    reports.mark_done(report_id, not items.get(report_id, {}).get("done", False))
    return RedirectResponse(f"/admin/reports{_token_qs(request)}", status_code=303)


def _back(request: Request, saved: str) -> RedirectResponse:
    token = request.query_params.get("token", "")
    params = urlencode({k: v for k, v in (("token", token), ("saved", saved)) if v})
    return RedirectResponse(f"/admin/reports?{params}", status_code=303)


@app.post("/admin/reports/{report_id}/apply")
async def apply_report(report_id: str, request: Request,
                       text: str = Form(...), target: str = Form(reports.STUDENT_FILE)):
    """제보를 다듬은 문장을 자료에 추가하고 처리 완료로 표시한다."""
    _check_admin(request)
    try:
        path = reports.append_knowledge(text, target)
    except ValueError as e:
        raise HTTPException(400, str(e))
    reports.mark_done(report_id, True)
    log.info("제보 반영: %s → %s", report_id, path.name)
    return _back(request, path.name)


@app.post("/admin/reviews/{review_id}/delete")
async def delete_review(review_id: str, request: Request):
    """부적절한 한줄평을 지운다."""
    _check_admin(request)
    reviews.remove(review_id)
    return RedirectResponse(f"/admin/reviews{_token_qs(request)}", status_code=303)


@app.get("/admin/reviews", response_class=HTMLResponse)
async def admin_reviews(request: Request):
    _check_admin(request)
    qs = _token_qs(request)
    names = {it["id"]: f"{h['name']} · {it['brand']} {it['name']}"
             for h in home.menu_halls() for it in h["items"]}
    rows = []
    for it in reviews.all_items():
        rows.append(
            f"<li><div class=meta>{it['at'][:16].replace('T', ' ')} · ★{it['rating']}"
            f"<form method=post action='/admin/reviews/{it['id']}/delete{qs}'>"
            f"<button>삭제</button></form></div>"
            f"<div class=msg><b>{escape(names.get(it['item'], it['item']))}</b><br>"
            f"{escape(it['comment']) or '<i>별점만</i>'}</div></li>")
    s = reviews.summary()
    return f"""<!DOCTYPE html><html lang=ko><head><meta charset=utf-8>
<title>곽봇 식당 리뷰</title><style>
body{{font-family:-apple-system,'Malgun Gothic',sans-serif;max-width:760px;margin:24px auto;padding:0 16px;color:#1b2230}}
h1{{font-size:20px}} ul{{list-style:none;padding:0}}
li{{border:1px solid #e2e7ef;border-radius:12px;padding:12px 14px;margin:10px 0}}
.meta{{display:flex;gap:10px;align-items:center;font-size:12px;color:#6b7687}}
.meta form{{margin-left:auto}} .msg{{margin-top:6px;white-space:pre-wrap;font-size:14px}}
button{{font-size:12px;padding:4px 10px;border:1px solid #cfd7e3;background:#fff;border-radius:999px;cursor:pointer}}
</style></head><body><h1>곽봇 식당 리뷰</h1>
<p>전체 {s['total']}건 · 한줄평 {s['with_comment']}건 · <a href="/admin/reports{qs}">제보함</a></p>
<ul>{''.join(rows) or '<li>아직 리뷰가 없어요.</li>'}</ul></body></html>"""


@app.post("/admin/knowledge")
async def add_knowledge(request: Request,
                        text: str = Form(...), target: str = Form(reports.STUDENT_FILE)):
    """제보와 무관하게 운영자가 직접 자료를 추가한다."""
    _check_admin(request)
    try:
        path = reports.append_knowledge(text, target)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _back(request, path.name)


class LoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=200)


def _admin_state() -> dict:
    s = reports.summary()
    return {"admin": True, "todo": s["todo"], "total": s["total"]}


@app.post("/api/admin/login")
async def admin_login(req: LoginRequest, request: Request):
    """채팅창에서 `su -` 다음에 넣은 비밀번호를 확인한다. 맞으면 로그인 쿠키를 준다."""
    if not admin.enabled():
        raise HTTPException(404, "not found")
    try:
        ok = admin.login(req.password, _client_ip(request))
    except admin.TooManyTries:
        raise HTTPException(429, "너무 많이 틀렸어요. 15분 뒤에 다시 시도하세요.")
    if not ok:
        log.warning("관리자 로그인 실패 (%s)", _client_ip(request))
        raise HTTPException(401, "su: 인증 실패")
    log.info("관리자 로그인")
    res = JSONResponse(await asyncio.to_thread(_admin_state))
    https = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
    res.set_cookie(admin.COOKIE, admin.issue(), max_age=admin.TTL, httponly=True,
                   samesite="strict", secure=https, path="/")
    return res


@app.post("/api/admin/logout")
async def admin_logout():
    res = JSONResponse({"admin": False})
    res.delete_cookie(admin.COOKIE, path="/")
    return res


@app.get("/api/admin/me")
async def admin_me(request: Request):
    """새로고침해도 관리자 모드를 이어 가도록, 로그인 상태와 밀린 제보 수를 알려준다."""
    if not _is_admin(request):
        return {"admin": False}
    return await asyncio.to_thread(_admin_state)


def _client_ip(request: Request) -> str:
    """배포 환경에서는 프록시를 거치므로 X-Forwarded-For 의 첫 주소를 쓴다."""
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@app.post("/api/chat")
async def chat(req: ChatRequest, request: Request):
    if req.messages[-1].role != "user":
        raise HTTPException(400, "마지막 메시지는 user 여야 합니다.")

    # 탄생 이야기처럼 글자 그대로 답해야 하는 물음은 AI 를 거치지 않는다 (사용량에도 안 셈)
    fixed = canned.reply(req.messages[-1].content)
    if fixed:
        async def fixed_stream():
            yield _sse({"text": fixed})
            yield "data: [DONE]\n\n"
        return StreamingResponse(fixed_stream(), media_type="text/event-stream")

    # 공개 운영: 한 사람이 무료 한도를 다 태우지 못하게 막는다
    try:
        limits.check(_client_ip(request))
    except limits.LimitExceeded as e:
        raise HTTPException(429, str(e))

    # 오래된 대화는 잘라서 토큰 낭비를 막는다
    history = [m.model_dump() for m in req.messages[-(MAX_HISTORY_TURNS * 2):]]

    async def event_stream():
        try:
            async for chunk in stream_reply(history):
                yield _sse({"text": chunk})
            yield "data: [DONE]\n\n"
        except providers.LLMError as e:
            yield _sse({"error": str(e)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
