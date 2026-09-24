"""질문과 관련된 지식 조각만 골라내는 간단한 검색기.

Groq 무료 티어는 분당 입력 토큰이 ~7,000 으로 빡빡해서 자료 전체를 매번 넣을 수 없다.
임베딩 없이 한글 2글자(바이그램) 겹침으로 점수를 매기는 방식 — 학교 공지처럼
고유명사·날짜 위주 텍스트에는 이 정도로 충분히 잘 맞는다.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# 항상 통째로 넣는 기본 자료 (작고 자주 쓰임)
ALWAYS_INCLUDE = ("01_school_overview.md",)
CONTEXT_BUDGET_CHARS = 4000  # ≈ 2,400 토큰 (한국어 기준 0.6 tok/char)

_DATE_RE = re.compile(r"(20\d\d)[.\-](\d\d)[.\-](\d\d)")
_WORD_RE = re.compile(r"[가-힣a-zA-Z0-9]+")
_URL_IN_HEADING_RE = re.compile(r"\s*\(https?://[^)]*\)")
META_PREFIXES = ("수집 시각", "수집일", "출처:", "각 게시판")  # 수집 파일의 머리말은 검색 대상에서 제외

# 질문에서 떼어낼 조사·어미 (2글자 초과 단어의 끝에서만)
_PARTICLE_RE = re.compile(r"(에서는|에서도|에서|에게|으로|이랑|한테|까지|부터|이나|이든|에는|에도|에|은|는|이|가|을|를|의|도|로|와|과|랑|야|요)$")
# 검색에 도움 안 되는 흔한 말
STOPWORDS = {
    "학교", "우리", "서울과기대", "과기대", "서울과학기술대학교", "곽봇", "좀", "혹시", "그리고", "근데",
    "있어", "있나", "있니", "있어요", "있나요", "없어", "어디", "어디야", "어디에", "어딨어", "뭐야", "뭐", "무엇",
    "언제", "언제야", "어떻게", "어떤", "알려줘", "알려주세요", "궁금해", "해줘", "보여줘", "말해줘", "관련", "대해",
    "정보", "안내", "질문", "이번", "오늘", "지금", "요즘", "최근", "제일", "가장",
}


# "오늘 점심 뭐야?" 처럼 상대적 날짜로 묻는 질문을, 자료에 적힌 날짜 표기로 바꿔 준다
_WEEKDAYS = "월화수목금토일"
_RELATIVE_DAYS = {"오늘": 0, "금일": 0, "내일": 1, "낼": 1, "모레": 2, "어제": -1}


def _expand_dates(query: str, today: date | None = None) -> str:
    today = today or date.today()
    extra = []
    for word, delta in _RELATIVE_DAYS.items():
        if word in query:
            d = today + timedelta(days=delta)
            extra += [f"{d.day}일", _WEEKDAYS[d.weekday()], f"{d.month}월", d.strftime("%Y-%m-%d")]
    if "이번주" in query or "이번 주" in query:
        extra.append(f"{today.month}월")
    return query + (" " + " ".join(extra) if extra else "")


# 학생이 쓰는 말과 학교 자료의 표기가 다를 때 검색어에 함께 넣어 준다
SYNONYMS = {
    "기숙사": "생활관", "생활관": "기숙사",
    "아침": "조식", "점심": "중식", "저녁": "석식",
    "조식": "아침", "중식": "점심", "석식": "저녁",
    "식당": "식단", "밥": "식단 식당", "메뉴": "식단",
    "등록금": "등록 납부", "수업료": "등록금",
    "빌려": "대출", "빌리": "대출",
    "휴학": "휴학 복학", "자퇴": "제적 자퇴",
}


def _expand_synonyms(words: list[str]) -> list[str]:
    out = list(words)
    for w in words:
        if w in SYNONYMS:
            out += SYNONYMS[w].split()
    return out


def _query_words(query: str) -> list[str]:
    words = []
    for w in _WORD_RE.findall(query):
        if len(w) > 2:
            w = _PARTICLE_RE.sub("", w)
        if w and w not in STOPWORDS:
            words.append(w)
    return _expand_synonyms(words)


@dataclass
class Chunk:
    source: str   # 파일명
    heading: str  # 가장 가까운 상위 제목
    text: str     # 실제 내용 한 줄/한 문단
    date: str     # 정렬용 YYYYMMDD (없으면 "")

    def render(self) -> str:
        return f"[{self.heading}] {self.text}"


def _bigrams(s: str) -> set[str]:
    grams = set()
    for w in _WORD_RE.findall(s):
        if len(w) == 1:
            grams.add(w)
        grams.update(w[i:i + 2] for i in range(len(w) - 1))
    return grams


def _chunk_file(path: Path) -> list[Chunk]:
    """'- ' 로 시작하는 줄은 각각 하나의 조각, 그 외 문단은 섹션 단위로 묶는다."""
    chunks: list[Chunk] = []
    title = path.stem
    heading = title
    para: list[str] = []

    def flush():
        if para:
            chunks.append(Chunk(path.name, heading, " ".join(para), ""))
            para.clear()

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.rstrip()
        if not line:
            flush()
            continue
        if line.startswith("#"):
            flush()
            h = _URL_IN_HEADING_RE.sub("", line.lstrip("#").strip())
            if line.startswith("# "):
                title = h.split("(")[0].strip()  # "최근 공지사항 (자동 수집)" -> "최근 공지사항"
                heading = title
            else:
                heading = f"{title} / {h}"
            continue
        if line.startswith("- "):
            flush()
            text = line[2:].strip()
            if text.startswith(META_PREFIXES):
                continue
            m = _DATE_RE.search(text)
            chunks.append(Chunk(path.name, heading, text, "".join(m.groups()) if m else ""))
        else:
            para.append(line.strip())
    flush()
    return chunks


def load_chunks() -> list[Chunk]:
    out = []
    for path in sorted(DATA_DIR.glob("*.md")):
        if path.name not in ALWAYS_INCLUDE:
            out.extend(_chunk_file(path))
    return out


PREV_WEIGHT = 0.3  # 직전 질문은 후속 질문("그건 언제야?") 보조용이라 약하게만 반영


def select_context(query: str, prev_query: str = "", budget: int = CONTEXT_BUDGET_CHARS) -> str:
    """항상 포함 자료 + 질문과 겹치는 조각을 점수·최신순으로 예산만큼 담아 문자열로."""
    parts = []
    for name in ALWAYS_INCLUDE:
        p = DATA_DIR / name
        if p.exists():
            parts.append(p.read_text(encoding="utf-8").strip())

    chunks = load_chunks()
    grams = [_bigrams(c.heading + " " + c.text) for c in chunks]
    # 흔한 바이그램("학기", "안내")은 낮게, 드문 것("장학", "셔틀")은 높게 — 간단한 IDF
    df = Counter(g for gs in grams for g in gs)
    n = len(chunks) or 1
    idf = lambda g: math.log(1 + n / df[g]) if g in df else 0.0
    q = _bigrams(" ".join(_query_words(_expand_dates(query))))
    q_prev = _bigrams(" ".join(_query_words(_expand_dates(prev_query)))) - q if prev_query else set()
    # 각 질문의 점수를 0~1 로 정규화해야 긴 직전 질문이 짧은 현재 질문을 덮지 않는다
    q_total = sum(idf(g) for g in q) or 1.0
    prev_total = sum(idf(g) for g in q_prev) or 1.0
    scored = []
    for c, gs in zip(chunks, grams):
        score = sum(idf(g) for g in q & gs) / q_total
        score += PREV_WEIGHT * sum(idf(g) for g in q_prev & gs) / prev_total
        if score > 0:
            scored.append((score, c.date, c))
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    if scored:  # 최고 점수 대비 너무 약한 매칭은 잡음이므로 버린다
        floor = scored[0][0] * 0.35
        scored = [t for t in scored if t[0] >= floor]

    used = sum(len(p) for p in parts)
    picked = []
    for _, _, c in scored:
        line = c.render()
        if used + len(line) > budget:
            continue
        picked.append(line)
        used += len(line) + 1
    if picked:
        parts.append("## 질문과 관련된 자료 (관련도·최신순)\n" + "\n".join(picked))
    return "\n\n".join(parts)
