"""단과대학별 교육과정 PDF 에서 학과별 교과목·이수학점을 뽑아 data/25_curriculum_*.md 로 저장.

학교가 교육과정을 PDF 로만 제공해서, "컴공 졸업학점"·"3학년 전공과목" 류 질문에 답하려면 필요하다.
서울과기대에는 공개 강의시간표 시스템이 없어서, 여기 실린 교육과정표가 '개설 교과목' 정보의 전부다.
자주 바뀌지 않으므로(연 1회) 결과를 깃에 커밋한다. 실행: python -m app.curriculum
"""
from __future__ import annotations

import io
import re
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

BASE = "https://www.seoultech.ac.kr"
PAGE = f"{BASE}/life/info/college/schedule/"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
HEADERS = {"User-Agent": "Mozilla/5.0 (kwakbot; +https://github.com/sanzmann/gwakbot)", "Referer": PAGE}
TIMEOUT = 120

# 올해 교육과정만 수집 (지난 학년도 PDF 는 양이 너무 커서 제외)
YEAR_RE = re.compile(r"(\d{4})학년도 교육과정\(([^)]+)\)")
# 학과 구분: "2026 교육과정" 다음 줄이 학과명인 페이지에서 섹션이 시작된다
SECTION_HEAD_RE = re.compile(r"^\d{4}\s*교육과정$")
GRADE = "(?:전공필수|전공선택|기초필수|기초선택|교양필수|교양선택|교직|일반선택)"
# 교과목 행: "3 1 전공선택 183014 공학수학(3) 3 3 0"
COURSE_RE = re.compile(rf"^(\d)\s+(\d)\s+({GRADE})\s+(\d{{5,6}})\s+(.+?)(?:\s+(\d+)\s+\d+\s+\d+(?:\s.*)?)?$")
# 학년/학기가 생략된 이어지는 행
COURSE_CONT_RE = re.compile(rf"^({GRADE})\s+(\d{{5,6}})\s+(.+?)(?:\s+(\d+)\s+\d+\s+\d+(?:\s.*)?)?$")
# 교과목 개요 시작 행: "101046 프로그래밍언어 (Programming Language)"
OVERVIEW_RE = re.compile(r"^(\d{5,6})\s+(\S.*?)\s*\((.+)\)\s*$")
# 졸업/이수학점 안내 행
CREDIT_RE = re.compile(r"(졸업학점|이수학점|최저\s*이수|졸업\s*요건|필수\s*이수)")
MAX_OVERVIEW_CHARS = 300


def list_pdfs(year: int | None = None) -> list[tuple[str, str, str]]:
    """[(학년도, 단과대학, PDF URL)] — 최신 학년도만."""
    soup = BeautifulSoup(requests.get(PAGE, headers=HEADERS, timeout=30).text, "lxml")
    found = []
    for tr in soup.select("#contents table tr"):
        label = " ".join(td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"]))
        a = tr.find("a", href=True)
        m = YEAR_RE.search(label)
        if a and m and ".pdf" in a["href"].lower():
            href = a["href"]
            found.append((m.group(1), m.group(2), href if href.startswith("http") else BASE + href))
    if not found:
        return []
    latest = year or max(int(y) for y, _, _ in found)
    return [(y, c, u) for y, c, u in found if int(y) == latest]


def pdf_pages(url: str) -> list[str]:
    data = requests.get(url, headers=HEADERS, timeout=TIMEOUT).content
    reader = PdfReader(io.BytesIO(data))
    return [(p.extract_text() or "") for p in reader.pages]


def _norm(line: str) -> str:
    """PDF 추출 텍스트에 섞인 널 문자·제어문자를 지우고 공백을 정리한다."""
    return re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f]+", " ", line)).strip()


def _course_line(grade: str, number: str, name: str, credit: str | None, year: str, semester: str) -> str:
    when = f"{year}학년 {semester}학기 " if year else ""
    return f"{when}{grade} | {name.strip()}" + (f" | {credit}학점" if credit else "") + f" | 교과목번호 {number}"


def parse_pages(pages: list[str]) -> list[tuple[str, list[str]]]:
    """페이지들을 훑어 (학과명, [교과목·이수학점 줄]) 로 묶는다."""
    sections: dict[str, list[str]] = {}
    current = "(학과 미상)"
    year = semester = ""
    overview_key = ""      # 교과목 개요를 모으는 중인 과목
    overview_buf: list[str] = []

    def flush_overview():
        nonlocal overview_key, overview_buf
        if overview_key and overview_buf:
            body = " ".join(overview_buf)[:MAX_OVERVIEW_CHARS]
            sections.setdefault(current, []).append(f"[교과목 개요] {overview_key}: {body}")
        overview_key, overview_buf = "", []

    for page in pages:
        lines = [_norm(ln) for ln in page.splitlines()]
        lines = [ln for ln in lines if ln]
        # 페이지 머리에서 학과 전환 감지
        for i, ln in enumerate(lines[:3]):
            if SECTION_HEAD_RE.match(ln) and i + 1 < len(lines):
                flush_overview()
                current = lines[i + 1]
                year = semester = ""
                break

        in_overview = any(ln.startswith("[교과목") for ln in lines[:2])
        for ln in lines:
            if ln.startswith("[교과목"):
                in_overview = True
                continue
            if m := COURSE_RE.match(ln):
                flush_overview()
                in_overview = False
                year, semester = m.group(1), m.group(2)
                sections.setdefault(current, []).append(
                    _course_line(m.group(3), m.group(4), m.group(5), m.group(6), year, semester))
                continue
            if not in_overview and (m := COURSE_CONT_RE.match(ln)) and year:
                sections.setdefault(current, []).append(
                    _course_line(m.group(1), m.group(2), m.group(3), m.group(4), year, semester))
                continue
            if in_overview:
                if m := OVERVIEW_RE.match(ln):
                    flush_overview()
                    overview_key = f"{m.group(2)} ({m.group(3)})"
                elif overview_key:
                    overview_buf.append(ln)
                continue
            if CREDIT_RE.search(ln) and len(ln) < 160 and any(c.isdigit() for c in ln):
                sections.setdefault(current, []).append(f"[이수학점] {ln}")
    flush_overview()
    return [(d, rows) for d, rows in sections.items()]


def refresh_curriculum() -> dict:
    today = date.today().isoformat()
    report = {}
    for year, college, url in list_pdfs():
        try:
            sections = parse_pages(pdf_pages(url))
        except Exception as e:
            print(f"실패 {college}: {type(e).__name__} {e}")
            report[college] = -1
            continue
        slug = re.sub(r"[^가-힣A-Za-z0-9]", "", college)
        lines = [
            f"# {year}학년도 교육과정 — {college}",
            f"- 출처: {PAGE} ({year}학년도 교육과정 PDF)",
            f"- 수집일: {today}",
            "- 학과별 개설 교과목(학년·학기·이수구분·학점)과 이수학점 기준입니다.",
            "- 실제 이번 학기 시간표(요일·강의실·담당교수)는 통합정보시스템에서 확인해야 합니다.",
            "",
        ]
        total = 0
        for dept, rows in sections:
            if len(rows) < 3:
                continue
            lines.append(f"\n## {college} {dept}")
            lines += [f"- [{dept}] {r}" for r in rows]
            total += len(rows)
        if total < 10:
            print(f"건너뜀 {college}: 추출된 줄 {total}")
            report[college] = 0
            continue
        (DATA_DIR / f"25_curriculum_{slug}.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        report[college] = total
        print(f"{college:24} {total:5}줄")
    return report


if __name__ == "__main__":
    print(refresh_curriculum())
