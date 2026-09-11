"""FastAPI 서버: 정적 채팅 UI + SSE 스트리밍 채팅 API."""
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import providers
from .bot import stream_reply

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

# 개인용 단계의 여유 있는 제한. 공개 전환 시 줄일 것.
MAX_MESSAGE_CHARS = 2000
MAX_HISTORY_TURNS = 10  # user+assistant 쌍 기준

app = FastAPI(title="곽봇", version="0.2.0")


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health():
    return {"ok": True, "llm": providers.describe()}


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
