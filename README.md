# 곽봇 (KwakBot)

서울과학기술대학교 학생을 위한 안내 챗봇. FastAPI + LLM(Groq 무료 / Claude 선택) 기반.

## 기능
- 학교 정보(위치, 교통, 단과대학, 문의처 등) Q&A
- 학교 홈페이지 공지사항(일반/학사/장학/취업)·학사일정(학부+대학원)·식단 자동 수집 (GitHub Actions 가 매일 08:00·19:00 KST 에 수집해 저장소에 커밋)
- 식단: 생활관 식당 주간 식단표·이용시간, 교내 식당(ST:Table=제1학생회관 / ST:Dining=제2학생회관) 메뉴·가격, 테크노파크 주간 식단표(이미지)
- 학사안내·교통·전화번호·시설·장학·등록금 등 정적 안내 페이지 37개 수집 (`python -m app.pages`)
- 캠퍼스 지도의 건물 43개·주요 호실 500여 개 (학과 사무실, 식당, 은행 등 위치) (`python -m app.campus_map`)
- 졸업요건 요약(학번별 졸업학점·졸업필수항목), 학과별 교육과정·교과목 개요 (`python -m app.curriculum`)
- 장학금 상세 — 학교가 한글/PDF 로만 올린 안내문을 파싱 (`python -m app.scholarship`)
- 공지사항은 제목뿐 아니라 최신 글의 본문 일부까지 수집
- 위치를 묻는 답변에는 **핀 찍힌 캠퍼스 지도 이미지**를 함께 표시 (클릭하면 크게)
- 캠퍼스 지도 팝업: OSM 기반 **상세 지도**(건물 윤곽·길·편의점·흡연구역 등)와 학교 일러스트 지도 전환,
  확대·드래그, 건물 클릭 시 입주 학과·호실 정보 (`python -m app.osm_map` 으로 갱신)
- 질문과 관련된 자료만 골라 LLM 에 전달 (바이그램+IDF 검색) — 무료 티어 토큰 한도 대응
- `data/*.md` 에 적은 자료를 지식 베이스로 사용 (파일 추가만 하면 학습 없이 반영)
- 홈 대시보드: 오늘 식단, 다가오는 학사일정(D-day), 최근 공지, 자주 가는 사이트 바로가기
- 마스코트(테크뇽 로봇) 기반 채팅 UI, 추천 질문, 답변 실시간 스트리밍, 마크다운 렌더링

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

## 인터넷에 공개하기 (배포)

GitHub 저장소를 [Render](https://render.com) 에 연결하면, `main` 에 푸시할 때마다 자동으로
다시 배포되는 공개 주소(`https://이름.onrender.com`)가 생깁니다. 저장소에 `render.yaml` 이 들어 있어
설정을 따로 입력할 필요가 없습니다.

> GitHub Pages 로는 안 됩니다. Pages 는 정적 파일만 올릴 수 있는데, 곽봇은 `/api/chat` 을
> 처리할 파이썬 서버와 (공개하면 안 되는) Groq 키가 필요합니다.

1. 코드를 GitHub 에 올립니다 — `git push origin main`
2. Render 가입 → **New ＞ Blueprint** → 곽봇 저장소 선택 → `render.yaml` 을 읽어 설정이 채워집니다
3. `GROQ_API_KEY` 칸에 키를 붙여넣고 (`.env` 에 있는 값) **Apply**
4. 몇 분 뒤 주소가 나오면 접속 — 첫 접속 때 학교 홈페이지 수집이 돌아 조금 느립니다
5. 제보함은 `https://주소/admin/reports?token=토큰` — 토큰은 Render 대시보드의
   Environment 탭에서 자동 생성된 `ADMIN_TOKEN` 값입니다 (토큰 없이 접속하면 404)

### 자료는 GitHub Actions 가 모읍니다
웹서버는 학교 홈페이지를 긁지 않습니다. `.github/workflows/collect.yml` 이 매일 **08:00·19:00 (KST)** 에
수집해서 `data/auto_*` 를 저장소에 커밋하고, 그 커밋이 Render 재배포를 일으켜 반영됩니다.

무료 플랜은 15분마다 잠들고 방문자가 올 때 깨어나는데, 깰 때마다 긁으면 공지가 하루 몇 건
올라오지 않는데도 학교 서버에 하루 1,000번 넘게 요청하게 되기 때문입니다. 지금은 하루 90번으로 고정입니다.
깃에 자료가 담겨 있어서 서버는 깨어나자마자 바로 답할 수 있습니다.

- 급히 갱신하고 싶으면: GitHub 저장소 **Actions ＞ 자료 수집 ＞ Run workflow**
- 내 컴퓨터에서 수집기를 고쳐 확인할 때: `python -m app.scraper` 또는 `SCRAPE_ON_START=1`
- 마지막 수집 시각은 `/health` 의 `last_refresh` 에서 확인

### 공개 운영 시 알아둘 것
- **사용량 제한**: 한 사람(IP)당 하루 40개·1분에 8개, 전체 하루 1500개까지 질문을 받습니다.
  Groq 무료 한도를 한 명이 다 태우지 못하게 하는 장치입니다. `CHAT_LIMIT_PER_IP`,
  `CHAT_LIMIT_TOTAL`, `CHAT_LIMIT_PER_MIN` 으로 조절합니다 (`/health` 에서 오늘 사용량 확인).
- **무료 플랜은 15분간 접속이 없으면 잠듭니다.** 다음 접속자가 30초~1분 기다립니다.
  (유료 플랜으로 올리거나, 그대로 두고 "처음엔 좀 느려요" 라고 안내해도 됩니다.)
- **제보는 서버가 재시작되면 사라집니다** — 무료 플랜의 디스크는 임시 저장소입니다.
  제보가 들어오면 제보함에서 바로 `data/` 에 반영하고, 그 변경을 깃에 커밋하세요.
  (Render 의 유료 Persistent Disk 를 붙이면 보존됩니다.)
- **자료 수정은 깃으로**: 공개 서버의 `data/` 에 추가한 내용도 재시작 때 사라지므로,
  내 컴퓨터에서 고쳐 푸시하는 쪽이 안전합니다.
- **학교 서버 인증서**: 학교 홈페이지가 중간 인증서를 보내주지 않아서, `certs/` 의 중간 인증서를
  함께 신뢰 목록에 넣어 수집합니다 (`app/net.py`). 리눅스 서버에서도 그대로 동작합니다.

## 구조
```
app/
  main.py       FastAPI 서버, /api/chat SSE 스트리밍, /api/home 홈 카드 데이터
  home.py       수집한 자료에서 홈 화면 요약 생성
  reports.py    학생 제보 저장·조회 (reports/reports.jsonl)
  limits.py     공개 운영용 사용량 제한 (IP당/전체 하루 질문 수)
  clock.py      한국 시간 기준 날짜 (배포 서버는 UTC 로 돌기 때문)
  net.py        학교 서버 인증서 대응 (certifi + certs/*.pem 묶음, 윈도우·리눅스 공통)
  bot.py        시스템 프롬프트 구성
  providers.py  LLM 백엔드 (groq / claude), .env 의 LLM_PROVIDER 로 전환, Groq 모델 폴백
  retrieval.py  질문 관련 자료 검색 (바이그램 + IDF)
  scraper.py    공지·학사일정 수집 → data/auto_*.md  (수동: python -m app.scraper, 식단도 함께 갱신)
                평소엔 GitHub Actions 가 하루 2번 돌린다. 서버는 긁지 않고 깃에 담겨온 자료를 쓴다
  menu.py       생활관 식단표 + 교내 식당 메뉴 → data/auto_menu.md  (수동: python -m app.menu)
  curriculum.py 교육과정 PDF → data/25_curriculum_*.md  (수동, 연 1회면 충분)
  scholarship.py 장학금 첨부파일 → data/21_scholarship_detail.md  (수동)
  hwp.py        한글(.hwp/.hwpx)·PDF 본문 추출기
  pages.py      홈페이지 정적 안내 페이지 → data/NN_*.md  (수동: python -m app.pages, 결과는 깃에 커밋)
  campus_map.py 캠퍼스지도의 건물·시설·호실 → data/14_campus_map.md + static/campus_buildings.json(핀 좌표)
data/           학교 정보 마크다운 (지식 베이스). auto_*.md 는 자동 생성
static/         채팅 UI (img/ 에 마스코트 이미지)
.github/workflows/collect.yml  하루 2번 자동 수집 → data/auto_* 커밋 → 재배포
DEVLOG.md       개발 일지
```

## 제보 받기
학생이 답변 아래 '🚩 이 답변이 틀렸나요?' 또는 화면 맨 아래 '잘못된 정보 알려주기' 를 누르면 제보가 쌓입니다.
공개되지 않고 `reports/reports.jsonl` 에 저장되며, http://127.0.0.1:8000/admin/reports 에서 확인합니다.
제보마다 수정칸이 있어서, 자료에 넣을 문장으로 다듬어 '자료에 추가' 를 누르면 `data/` 에 바로 반영됩니다
(기본 파일은 `data/05_student_notes.md`, 다른 파일을 고를 수도 있음). 제보와 무관한 내용은 맨 위 '직접 추가' 칸으로.
(공개 서버에서는 `.env` 의 `ADMIN_TOKEN` 을 설정하고 `?token=값` 으로 접속)

## 성격 바꾸기
`persona.md` 를 고치면 이름·말투·설정이 바뀝니다 (서버 재시작 필요). 코드는 건드리지 않아도 됩니다.

## LLM 백엔드 바꾸기
`.env` 의 `LLM_PROVIDER` 를 `groq` 또는 `claude` 로 바꾸면 됩니다. 기본은 무료인 Groq(`qwen/qwen3.8-27b`).

## 지식 추가하기
`data/` 폴더에 `.md` 파일을 추가하면 됩니다. 학교 홈페이지에 없는 내용(재학생만 아는 정보)도
직접 적어두면 그대로 답변에 쓰입니다 — 예: `data/03_tips_registration.md` (수강신청 우선수강신청 기능).
이때 첫 줄에 출처와 날짜를 적어두면 나중에 검증하기 좋습니다.

- 낱개 사실(전화번호, 메뉴, 공지 등)은 `- ` 목록으로 한 줄씩
- 순서가 중요한 절차는 `- ` 없이 번호를 붙인 한 문단으로 (검색기가 한 덩어리로 유지해서 단계가 빠지지 않습니다) 파일명 순으로 읽히며 서버 재시작 없이 다음 요청부터 반영됩니다.
