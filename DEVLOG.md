# 곽봇 개발 일지

## 2026-09-11 — 프로젝트 시작
- 목표: 서울과학기술대학교 학생용 안내 챗봇 "곽봇"
- 스택 결정: Python 3.10 + FastAPI + Claude API (`claude-opus-5`), 순수 HTML/JS 채팅 UI
- 지식 베이스 방식: `data/*.md` 파일을 시스템 프롬프트에 주입 (프롬프트 캐싱 적용). RAG/벡터DB는 자료가 커지면 검토
- 구현:
  - `app/bot.py` — AsyncAnthropic 스트리밍, 시스템 프롬프트, 지식 주입
  - `app/main.py` — `/api/chat` SSE 엔드포인트, 에러 처리(인증/레이트리밋/네트워크)
  - `static/index.html` — 스트리밍 표시되는 채팅 UI, 다크모드 대응
  - `data/01_school_overview.md` — 학교 기본 정보 초안 (검증 필요)
- 다음 할 일:
  - [ ] 학교 정보 자료 검증 및 보강 (학사일정, 건물 위치, 셔틀, 식당 등)
  - [ ] 공지사항 크롤링/조회 기능
  - [ ] GitHub 원격 저장소 연결
