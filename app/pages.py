"""학교 홈페이지의 정적 안내 페이지(학사안내, 오시는길, 전화번호 등)를 마크다운으로 변환해 data/ 에 저장.

공지와 달리 자주 바뀌지 않으므로 결과 파일을 깃에 커밋한다.
실행: python -m app.pages
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup, Tag

BASE = "https://www.seoultech.ac.kr"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
HEADERS = {"User-Agent": "Mozilla/5.0 (kwakbot; +https://github.com/sanzmann/gwakbot)"}

# (파일명, 제목, 경로). 파일명 앞 숫자는 주제별 묶음.
PAGES = [
    ("10_campus_location", "오시는 길 (교통)", "/intro/campinfo/location"),
    ("10_campus_parking", "주차 안내", "/intro/campinfo/parking"),
    ("11_campus_phone", "교내 전화번호", "/intro/campinfo/interph"),
    ("12_campus_facility", "편의시설 정보", "/life/student/welfare/info"),
    ("12_campus_gym", "체육관", "/life/student/welfare/gym"),
    ("12_campus_library", "도서관", "/life/support/library"),
    ("12_campus_housing", "생활관 (기숙사)", "/life/support/housing"),
    ("12_campus_clinic", "보건진료소", "/life/attatched/clinic"),
    ("12_campus_counsel", "학생상담센터", "/life/jobinfo/life"),
    ("13_history", "연혁", "/intro/univ/histroy/01"),
    ("13_mascot", "마스코트", "/intro/symbol/mascot/intro"),
    ("20_academic_course", "수강신청", "/life/info/college/course"),
    ("20_academic_rest", "휴학/복학", "/life/info/college/rest"),
    ("20_academic_caution", "학사경고", "/life/info/college/caution"),
    ("20_academic_leave", "제적/자퇴", "/life/info/college/leave"),
    ("20_academic_season", "계절학기", "/life/info/college/season"),
    ("20_academic_readmit", "재입학", "/life/info/college/readmit"),
    ("20_academic_change", "전과(부)", "/life/info/college/change"),
    ("20_academic_graduate", "학년수료 및 졸업", "/life/info/college/graduate"),
    ("20_academic_relearning", "재수강", "/life/info/college/relearning"),
    ("20_academic_tests", "시험과 성적", "/life/info/college/tests"),
    ("20_academic_attendance", "출석인정", "/life/info/college/attendance"),
    ("20_academic_exchange", "국내 타 대학 학점교류", "/life/info/college/exchange"),
    ("20_academic_multimajor", "다전공 (복수·부전공 등)", "/life/info/college/multimajor"),
    ("21_scholarship", "장학제도 안내 (교내·국가·교외 장학금 목록)", "/life/scholarship/janghag"),
    ("22_tuition_info", "등록 안내", "/life/tution/infotution"),
    ("22_tuition_pay", "등록금 납부 안내", "/life/tution/paiement"),
    ("22_tuition_divide", "등록금 분할납부 안내", "/life/tution/dividpay"),
    ("22_tuition_return", "등록금 반환 안내", "/life/tution/returnpay"),
    ("23_student_id", "학생증 발급", "/life/student/studentid"),
    ("23_student_club", "동아리", "/life/student/organ/club"),
    ("24_military_info", "학생 병무 안내", "/life/military/info"),
    ("24_military_reserve", "예비군 안내", "/life/military/reserve"),
    ("30_college_eng", "공과대학 소개", "/univ/univ/eng/intro"),
    ("30_college_itc", "정보통신대학 소개", "/univ/univ/itc/intro"),
    ("30_college_ebio", "에너지바이오대학 소개", "/univ/univ/ebio/intro"),
    ("30_college_mol", "조형대학 소개", "/univ/univ/mol/intro"),
    ("30_college_human", "인문사회대학 소개", "/univ/univ/human/intro"),
    ("30_college_tech", "기술경영융합대학 소개", "/univ/univ/tech/intro"),
    ("30_college_fusion", "미래융합대학 소개", "/univ/univ/fusion/intro"),
    ("30_college_cccs", "창의융합대학 소개", "/univ/univ/cccs/introduce"),
    ("30_college_liba", "교양대학 소개", "/univ/univ/liba/intro"),
]

# 본문에서 걷어낼 요소: 스크립트, 서브메뉴, 경로 표시, 버튼, 지도
NOISE_SELECTORS = ["script", "style", "noscript", "iframe", ".location", ".breadcrumb", "nav",
                   ".wrap_btn", ".sns", ".print", ".sub_menu", ".submenu", ".lnb", ".tab_menu",
                   "ul.tab", ".map", ".root_daum_roughmap", ".screen_hide", ".skip"]
MIN_CHARS = 120  # 이보다 짧으면 이미지/외부링크 페이지로 보고 건너뜀


def _clean(text: str) -> str:
    return re.sub(r"[ \t ]+", " ", text).strip()


def _table_to_lines(table: Tag) -> list[str]:
    """표는 행마다 한 줄 '- 셀1 | 셀2 | ...' 로. 검색기가 행 단위로 고를 수 있게."""
    lines = []
    for tr in table.find_all("tr"):
        cells = [_clean(c.get_text(" ", strip=True)) for c in tr.find_all(["th", "td"])]
        cells = [c for c in cells if c]
        if cells:
            lines.append("- " + " | ".join(cells))
    return lines


def _to_markdown(root: Tag) -> str:
    out: list[str] = []
    for el in root.descendants:
        if not isinstance(el, Tag):
            continue
        name = el.name
        if name in ("h2", "h3", "h4", "h5"):
            t = _clean(el.get_text(" ", strip=True))
            if t:
                out.append("\n" + "#" * (int(name[1]) - 0) + " " + t)  # h2 -> ##, h3 -> ###
        elif name == "table":
            out.extend(_table_to_lines(el))
            out.append("")
        elif name == "li" and not el.find_parent("table"):
            t = _clean(el.get_text(" ", strip=True))
            if t and not el.find("li"):  # 중첩 목록은 가장 안쪽만
                out.append("- " + t)
        elif name == "p" and not el.find_parent(["table", "li"]):
            t = _clean(el.get_text(" ", strip=True))
            if t:
                out.append(t)
                out.append("")
    # 연속 빈 줄 정리
    md = "\n".join(out)
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip()


def _scholarship_markdown(root: Tag) -> str:
    """장학제도안내는 목록만 HTML 이고 상세는 .hwp 첨부라, 분류별 목록 + 파일명을 남긴다."""
    lines = []
    for cat in root.select("div.janghag div.m1"):
        name = _clean(cat.get_text(" ", strip=True))
        ul = cat.find_next_sibling("ul")
        if not (name and ul):
            continue
        lines.append(f"\n## {name}")
        for li in ul.find_all("li", recursive=False):
            title = _clean(li.get_text(" ", strip=True))
            a = li.find("a", href=True)
            m = re.search(r"fileDown\('[^']*','[^']*','([^']*)'", a["href"]) if a else None
            if title:
                lines.append(f"- {name} - {title}" + (f" (상세: 첨부파일 {m.group(1)})" if m else ""))
    if lines:
        lines.append("\n- 각 장학금의 지급 기준·신청 방법은 위 페이지의 한글(.hwp) 첨부파일에 있음. "
                     "자격 조건은 '맞춤형장학조회'(https://www.seoultech.ac.kr/life/scholarship/lookup/) 에서 확인 가능")
        lines.append("- 학기별 신청 일정은 장학공지 게시판(https://www.seoultech.ac.kr/service/info/janghak/) 참고")
    return "\n".join(lines).strip()


def fetch_page(path: str) -> str:
    r = requests.get(BASE + path, headers=HEADERS, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")
    root = soup.select_one("#contents") or soup.body
    for sel in NOISE_SELECTORS:
        for el in root.select(sel):
            el.decompose()
    if root.select_one("div.janghag div.m1"):
        return _scholarship_markdown(root)
    # 학사안내류 상단의 형제 페이지 링크 목록 (링크만 잔뜩 있는 ul) 제거
    for ul in root.find_all("ul"):
        lis = ul.find_all("li", recursive=False)
        if len(lis) >= 5 and all(li.find("a") for li in lis):
            ul.decompose()
    return _to_markdown(root)


def refresh_pages() -> list[tuple[str, int]]:
    today = date.today().isoformat()
    report = []
    for fname, title, path in PAGES:
        try:
            md = fetch_page(path)
        except Exception as e:
            report.append((fname, -1))
            print(f"실패 {fname}: {e}")
            continue
        if len(md) < MIN_CHARS:
            report.append((fname, 0))
            print(f"건너뜀 {fname}: 본문이 거의 없음 ({len(md)}자)")
            continue
        header = f"# {title}\n- 출처: {BASE}{path}\n- 수집일: {today}\n\n"
        (DATA_DIR / f"{fname}.md").write_text(header + md + "\n", encoding="utf-8")
        report.append((fname, len(md)))
    return report


if __name__ == "__main__":
    for fname, n in refresh_pages():
        print(f"{fname:26} {n:>6}자")
