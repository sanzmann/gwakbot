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
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# 항상 통째로 넣는 기본 자료 (작고 자주 쓰임)
ALWAYS_INCLUDE = ("01_school_overview.md",)
CONTEXT_BUDGET_CHARS = 4000  # ≈ 2,400 토큰 (한국어 기준 0.6 tok/char)

_DATE_RE = re.compile(r"(20\d\d)[.\-](\d\d)[.\-](\d\d)")
_WORD_RE = re.compile(r"[가-힣a-zA-Z0-9]+")
_URL_IN_HEADING_RE = re.compile(r"\s*\(https?://[^)]*\)")
META_PREFIXES = ("수집 시각", "출처:", "각 게시판")  # 자동 수집 파일의 머리말은 검색 대상에서 제외


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


def select_context(query: str, budget: int = CONTEXT_BUDGET_CHARS) -> str:
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
    q = _bigrams(query)
    scored = []
    for c, gs in zip(chunks, grams):
        score = sum(math.log(1 + n / df[g]) for g in q & gs)
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
