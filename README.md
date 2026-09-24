# 곽봇 (KwakBot)

서울과학기술대학교 학생을 위한 안내 챗봇. FastAPI + LLM(Groq 무료 / Claude 선택) 기반.

## 기능
- 학교 정보(위치, 교통, 단과대학, 문의처 등) Q&A
- 학교 홈페이지 공지사항(일반/학사/장학/취업)·학사일정(학부+대학원)·식단 자동 수집 (서버 시작 시 + 6시간마다)
- 식단: 생활관 식당 주간 식단표·이용시간, 교내 식당(ST:Table/ST:Dining) 메뉴·가격
- 학사안내·교통·전화번호·시설·장학·등록금 등 정적 안내 페이지 37개 수집 (`python -m app.pages`)
- 캠퍼스 지도의 건물 43개·주요 호실 500여 개 (학과 사무실, 식당, 은행 등 위치) (`python -m app.campus_map`)
- 위치를 묻는 답변에는 **핀 찍힌 캠퍼스 지도 이미지**를 함께 표시 (클릭하면 크게)
- 질문과 관련된 자료만 골라 LLM 에 전달 (바이그램+IDF 검색) — 무료 티어 토큰 한도 대응
- `data/*.md` 에 적은 자료를 지식 베이스로 사용 (파일 추가만 하면 학습 없이 반영)
- 웹 채팅 UI, 답변 실시간 스트리밍, 마크다운 렌더링

## 실행 방법

**Windows 에서 가장 쉬운 방법**: `곽봇 실행.bat` 더블클릭 → 서버가 켜지고 브라우저가 자동으로 열림. 창을 닫으면 종료.

처음 한 번은 아래 설치가 필요:

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
  providers.py  LLM 백엔드 (groq / claude), .env 의 LLM_PROVIDER 로 전환, Groq 모델 폴백
  retrieval.py  질문 관련 자료 검색 (바이그램 + IDF)
  scraper.py    공지·학사일정 수집 → data/auto_*.md  (수동: python -m app.scraper, 식단도 함께 갱신)
  menu.py       생활관 식단표 + 교내 식당 메뉴 → data/auto_menu.md  (수동: python -m app.menu)
  pages.py      홈페이지 정적 안내 페이지 → data/NN_*.md  (수동: python -m app.pages, 결과는 깃에 커밋)
  campus_map.py 캠퍼스지도의 건물·시설·호실 → data/14_campus_map.md + static/campus_buildings.json(핀 좌표)
data/           학교 정보 마크다운 (지식 베이스). auto_*.md 는 자동 생성
static/         채팅 UI
DEVLOG.md       개발 일지
```

## LLM 백엔드 바꾸기
`.env` 의 `LLM_PROVIDER` 를 `groq` 또는 `claude` 로 바꾸면 됩니다. 기본은 무료인 Groq(`qwen/qwen3.8-27b`).

## 지식 추가하기
`data/` 폴더에 `.md` 파일을 추가하면 됩니다. 파일명 순으로 읽히며 서버 재시작 없이 다음 요청부터 반영됩니다.
