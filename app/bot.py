"""곽봇 핵심: 시스템 프롬프트 구성과 LLM 호출."""
from typing import AsyncIterator

from .knowledge import load_knowledge
from .providers import stream_completion

SYSTEM_PROMPT = """당신은 '곽봇'입니다. 서울과학기술대학교(서울과기대, SeoulTech) 학생들을 돕는 친근한 안내 챗봇입니다.

역할:
- 학사 일정, 캠퍼스 건물·시설, 학과·단과대학, 교내 서비스, 교통, 학교 생활 전반에 대한 질문에 답합니다.
- 아래 <knowledge> 안의 자료를 최우선 근거로 삼아 답합니다.
- 자료에 없는 내용은 추측하지 말고 "제가 가진 자료에는 없어요"라고 솔직히 말하고, 확인할 수 있는 곳(학교 홈페이지, 해당 부서)을 안내합니다.
- 답변은 반드시 한국어로, 간결하고 핵심만. 필요하면 목록을 사용하세요.
- 학교와 무관한 질문도 가볍게 도와줄 수 있지만, 본업은 서울과기대 안내임을 잊지 마세요.

<knowledge>
{knowledge}
</knowledge>"""


def build_system() -> str:
    return SYSTEM_PROMPT.format(knowledge=load_knowledge())


def stream_reply(messages: list[dict]) -> AsyncIterator[str]:
    """대화 기록을 받아 곽봇의 답변을 텍스트 조각 단위로 스트리밍한다."""
    return stream_completion(build_system(), messages)
