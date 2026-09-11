# 곽봇 (KwakBot)

서울과학기술대학교 학생을 위한 안내 챗봇. FastAPI + LLM(Groq 무료 / Claude 선택) 기반.

## 기능
- 학교 정보(위치, 교통, 단과대학, 문의처 등) Q&A
- `data/*.md` 에 적은 자료를 지식 베이스로 사용 (파일 추가만 하면 학습 없이 반영)
- 웹 채팅 UI, 답변 실시간 스트리밍

## 실행 방법

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy .env.example .env          # GROQ_API_KEY 채우기 (console.groq.com 무료 발급)
uvicorn app.main:app --reload
```

브라우저에서 http://127.0.0.1:8000 접속.

## 구조
```
app/
  main.py       FastAPI 서버, /api/chat SSE 스트리밍
  bot.py        시스템 프롬프트 구성
  providers.py  LLM 백엔드 (groq / claude), .env 의 LLM_PROVIDER 로 전환
  knowledge.py  data/*.md 로더
data/           학교 정보 마크다운 (지식 베이스)
static/         채팅 UI
DEVLOG.md       개발 일지
```

## LLM 백엔드 바꾸기
`.env` 의 `LLM_PROVIDER` 를 `groq` 또는 `claude` 로 바꾸면 됩니다. 기본은 무료인 Groq(`qwen/qwen3.8-27b`).

## 지식 추가하기
`data/` 폴더에 `.md` 파일을 추가하면 됩니다. 파일명 순으로 읽히며 서버 재시작 없이 다음 요청부터 반영됩니다.
