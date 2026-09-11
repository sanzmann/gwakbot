"""FastAPI 서버: 정적 채팅 UI + SSE 스트리밍 채팅 API."""
import json
from pathlib import Path

import anthropic
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .bot import stream_reply

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="곽봇", version="0.1.0")


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health():
    return {"ok": True}


@app.post("/api/chat")
async def chat(req: ChatRequest):
    if req.messages[-1].role != "user":
        raise HTTPException(400, "마지막 메시지는 user 여야 합니다.")

    history = [m.model_dump() for m in req.messages]

    async def event_stream():
        try:
            async for chunk in stream_reply(history):
                yield f"data: {json.dumps({'text': chunk}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except anthropic.AuthenticationError:
            yield f"data: {json.dumps({'error': 'API 키가 올바르지 않습니다. .env 를 확인하세요.'}, ensure_ascii=False)}\n\n"
        except anthropic.RateLimitError:
            yield f"data: {json.dumps({'error': '요청이 너무 많습니다. 잠시 후 다시 시도해주세요.'}, ensure_ascii=False)}\n\n"
        except anthropic.APIStatusError as e:
            yield f"data: {json.dumps({'error': f'API 오류 ({e.status_code})'}, ensure_ascii=False)}\n\n"
        except anthropic.APIConnectionError:
            yield f"data: {json.dumps({'error': '네트워크 연결에 실패했습니다.'}, ensure_ascii=False)}\n\n"
        except TypeError as e:
            # SDK 가 API 키를 못 찾으면 TypeError 를 던진다
            if "authentication" not in str(e).lower():
                raise
            yield f"data: {json.dumps({'error': 'ANTHROPIC_API_KEY 가 설정되지 않았습니다. .env 파일을 만들어주세요.'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
