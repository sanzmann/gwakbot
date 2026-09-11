"""FastAPI 서버: 정적 채팅 UI + SSE 스트리밍 채팅 API."""
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import providers, scraper
from .bot import stream_reply

log = logging.getLogger("kwakbot")
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

# 개인용 단계의 여유 있는 제한. 공개 전환 시 줄일 것.
MAX_MESSAGE_CHARS = 2000
MAX_HISTORY_TURNS = 4  # user+assistant 쌍 기준. Groq 무료 티어 토큰 한도 때문에 짧게
REFRESH_INTERVAL_SEC = 6 * 60 * 60  # 공지·학사일정 재수집 주기

last_refresh: dict = {}


async def _refresh_loop():
    global last_refresh
    while True:
        try:
            last_refresh = await asyncio.to_thread(scraper.refresh_all)
        except Exception as e:  # 수집 실패해도 서버는 계속 뜬다 (기존 파일 사용)
            log.warning("자동 수집 실패: %s", e)
        await asyncio.sleep(REFRESH_INTERVAL_SEC)


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(_refresh_loop())
    yield
    task.cancel()


app = FastAPI(title="곽봇", version="0.3.0", lifespan=lifespan)


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/health")
async def health():
    return {"ok": True, "llm": providers.describe(), "last_refresh": last_refresh}


@app.post("/api/chat")
async def chat(req: ChatRequest):
    if req.messages[-1].role != "user":
        raise HTTPException(400, "마지막 메시지는 user 여야 합니다.")

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
