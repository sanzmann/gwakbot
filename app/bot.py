"""곽봇 핵심: 시스템 프롬프트 구성과 LLM 호출."""
from datetime import date
from typing import AsyncIterator

from .providers import stream_completion
from .retrieval import select_context

SYSTEM_PROMPT = """당신은 '곽봇'입니다. 서울과학기술대학교(서울과기대, SeoulTech) 학생들을 돕는 친근한 안내 챗봇입니다.

역할:
- 학사 일정, 캠퍼스 건물·시설, 학과·단과대학, 교내 서비스, 교통, 학교 생활 전반에 대한 질문에 답합니다.
- 아래 <knowledge> 안의 자료를 최우선 근거로 삼아 답합니다.
- 자료에 없는 내용은 추측하지 말고 "제가 가진 자료에는 없어요"라고 솔직히 말하고, 확인할 수 있는 곳(학교 홈페이지, 해당 부서)을 안내합니다.
- 답변은 반드시 한국어로, 간결하고 핵심만. 필요하면 목록을 사용하세요. 매번 자기소개나 인사로 시작하지 마세요.
- 학교와 무관한 질문도 가볍게 도와줄 수 있지만, 본업은 서울과기대 안내임을 잊지 마세요.
- 공지사항·학사일정 자료는 학교 홈페이지에서 자동 수집한 것입니다. 공지는 제목만 있으므로 관련 글을 골라 제목·날짜·부서와 함께 링크를 안내하세요.
- "이번 주", "다음 달" 같은 상대적 날짜 질문은 오늘 날짜({today})를 기준으로 계산하세요.

<knowledge>
{knowledge}
</knowledge>"""


def build_system(query: str, prev_query: str = "") -> str:
    """질문과 관련된 자료만 골라 넣은 시스템 프롬프트 (Groq 무료 티어 토큰 한도 대응)."""
    return SYSTEM_PROMPT.format(knowledge=select_context(query, prev_query), today=date.today().isoformat())


def stream_reply(messages: list[dict]) -> AsyncIterator[str]:
    """대화 기록을 받아 곽봇의 답변을 텍스트 조각 단위로 스트리밍한다."""
    # 직전 user 메시지는 "그건 언제야?" 같은 후속 질문을 위해 약한 가중치로만 검색에 반영
    user_turns = [m["content"] for m in messages if m["role"] == "user"]
    prev = user_turns[-2] if len(user_turns) > 1 else ""
    return stream_completion(build_system(user_turns[-1], prev), messages)
