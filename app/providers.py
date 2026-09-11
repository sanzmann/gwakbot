"""LLM 백엔드 추상화. .env 의 LLM_PROVIDER 로 groq / claude 를 전환한다.

각 provider 는 (system, messages) 를 받아 답변 텍스트 조각을 async 로 yield 하고,
SDK 별 예외는 사용자에게 보여줄 메시지를 담은 LLMError 로 통일한다.
"""
import os
from typing import AsyncIterator

from dotenv import load_dotenv

load_dotenv()

PROVIDER = os.getenv("LLM_PROVIDER", "groq").lower()

Messages = list[dict]  # [{"role": "user"|"assistant", "content": str}, ...]


class LLMError(Exception):
    """사용자에게 그대로 보여줘도 되는 한국어 메시지를 담는 예외."""


# ---------------------------------------------------------------- Groq

GROQ_MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")


async def _stream_groq(system: str, messages: Messages) -> AsyncIterator[str]:
    import groq

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise LLMError("GROQ_API_KEY 가 설정되지 않았습니다. .env 파일을 확인해주세요.")

    client = groq.AsyncGroq(api_key=api_key)
    try:
        stream = await client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "system", "content": system}, *messages],
            max_tokens=1024,
            temperature=0.3,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta
    except groq.AuthenticationError:
        raise LLMError("Groq API 키가 올바르지 않습니다.")
    except groq.RateLimitError:
        raise LLMError("지금 요청이 몰려서 잠시 쉬고 있어요. 1분 뒤에 다시 물어봐주세요.")
    except groq.APIStatusError as e:
        raise LLMError(f"Groq API 오류 ({e.status_code})")
    except groq.APIConnectionError:
        raise LLMError("네트워크 연결에 실패했습니다.")


# ---------------------------------------------------------------- Claude

CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5")


async def _stream_claude(system: str, messages: Messages) -> AsyncIterator[str]:
    import anthropic

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise LLMError("ANTHROPIC_API_KEY 가 설정되지 않았습니다. .env 파일을 확인해주세요.")

    client = anthropic.AsyncAnthropic(api_key=api_key)
    try:
        async with client.messages.stream(
            model=CLAUDE_MODEL,
            max_tokens=4096,
            # 지식 베이스가 포함된 시스템 프롬프트는 매 요청 동일하므로 캐싱
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=messages,
            output_config={"effort": "low"},
        ) as stream:
            async for text in stream.text_stream:
                yield text
    except anthropic.AuthenticationError:
        raise LLMError("Claude API 키가 올바르지 않습니다.")
    except anthropic.RateLimitError:
        raise LLMError("요청이 너무 많습니다. 잠시 후 다시 시도해주세요.")
    except anthropic.APIStatusError as e:
        raise LLMError(f"Claude API 오류 ({e.status_code})")
    except anthropic.APIConnectionError:
        raise LLMError("네트워크 연결에 실패했습니다.")


# ---------------------------------------------------------------- 선택

_PROVIDERS = {"groq": _stream_groq, "claude": _stream_claude}


def stream_completion(system: str, messages: Messages) -> AsyncIterator[str]:
    try:
        provider = _PROVIDERS[PROVIDER]
    except KeyError:
        raise LLMError(f"알 수 없는 LLM_PROVIDER: {PROVIDER} (groq 또는 claude)")
    return provider(system, messages)


def describe() -> str:
    """현재 어떤 백엔드/모델을 쓰는지 (로그·헬스체크용)."""
    model = GROQ_MODEL if PROVIDER == "groq" else CLAUDE_MODEL
    return f"{PROVIDER}:{model}"
