"""장학제도안내 페이지에 걸린 한글 파일을 받아 장학금별 상세 내용을 data/ 에 저장.

목록만으로는 "ST근로장학금 조건이 뭐야?" 같은 질문에 답할 수 없어서, 첨부된 .hwp/.hwpx 본문까지 읽는다.
자주 바뀌지 않으므로 결과를 깃에 커밋한다. 실행: python -m app.scholarship
"""
from __future__ import annotations

import re
import urllib.parse
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from .hwp import extract

BASE = "https://www.seoultech.ac.kr"
PAGE = f"{BASE}/life/scholarship/janghag/"
FILE_SERVER = "https://for-a.seoultech.ac.kr/FileUploader?mode=downloadWeb"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUT = DATA_DIR / "21_scholarship_detail.md"
HEADERS = {"User-Agent": "Mozilla/5.0 (kwakbot; +https://github.com/sanzmann/gwakbot)", "Referer": PAGE}
TIMEOUT = 60
MAX_CHARS = 2500  # 장학금 하나당 본문 상한 (토큰 절약)

_FILEDOWN_RE = re.compile(r"fileDown\('([^']+)','([^']+)','([^']*)'")


def list_attachments() -> list[tuple[str, str, str, str]]:
    """[(분류, 장학금명, subDir, 서버 파일명)]"""
    soup = BeautifulSoup(requests.get(PAGE, headers=HEADERS, timeout=30).text, "lxml")
    items = []
    for category in soup.select("div.janghag div.m1"):
        cat = re.sub(r"\s+", " ", category.get_text(" ", strip=True))
        ul = category.find_next_sibling("ul")
        for a in (ul.find_all("a", href=True) if ul else []):
            m = _FILEDOWN_RE.search(a["href"])
            if m:
                items.append((cat, re.sub(r"\s+", " ", a.get_text(" ", strip=True)), m.group(1), m.group(2)))
    return items


def download(sub_dir: str, file_name: str) -> bytes:
    url = (f"{FILE_SERVER}&subDir={sub_dir}&fileName={urllib.parse.quote(file_name)}"
           f"&downloadFileNm={urllib.parse.quote(file_name)}")
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.content


def refresh_scholarship_details() -> dict:
    lines = [
        "# 장학금 상세 내용 (장학제도안내 첨부 한글파일에서 추출)",
        f"- 출처: {PAGE}",
        f"- 수집일: {date.today().isoformat()}",
        "- 원문은 한글(.hwp) 파일이라 표가 줄글로 풀려 있을 수 있음. 금액·기간은 반드시 원문/공지 확인 안내할 것",
        "",
    ]
    ok = failed = 0
    for cat, name, sub_dir, file_name in list_attachments():
        try:
            text = extract(download(sub_dir, file_name), file_name)
        except Exception as e:
            print(f"실패 {name}: {type(e).__name__} {e}")
            failed += 1
            continue
        if len(text) < 50:
            failed += 1
            continue
        lines.append(f"\n## {name} ({cat})")
        for para in text[:MAX_CHARS].split("\n"):
            para = para.strip()
            if para:
                lines.append(f"- [{name}] {para}")
        ok += 1
        print(f"{name:40} {len(text):6}자")

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return {"ok": ok, "failed": failed, "chars": OUT.stat().st_size}


if __name__ == "__main__":
    print(refresh_scholarship_details())
