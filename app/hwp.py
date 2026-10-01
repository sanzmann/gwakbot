"""한글 문서(.hwp / .hwpx) 에서 본문 텍스트만 뽑아낸다.

학교가 장학금·학사 안내를 한글 파일로만 올리는 경우가 많아서 필요하다.
- .hwpx: ZIP + XML 이라 쉬움
- .hwp: OLE 복합문서. BodyText 스트림을 zlib 로 풀고 레코드를 훑어 PARA_TEXT(태그 67)만 모은다
"""
from __future__ import annotations

import io
import re
import struct
import zipfile
import zlib

import olefile

HWPTAG_PARA_TEXT = 67
# 8 WCHAR(16바이트) 를 차지하는 확장 제어문자 (표·그림 등)
EXTENDED_CONTROLS = {1, 2, 3, 11, 12, 14, 15, 16, 17, 18, 21, 22, 23}

# 본문에 남길 문자 범위 — 제어문자 파싱 과정에서 섞여 들어오는 깨진 글자를 걸러낸다
_KEEP = re.compile(
    r"[\n\t\x20-\x7e"            # 개행·탭·ASCII
    r"　-〿"             # CJK 문장부호
    r"㄰-㆏"             # 한글 자모
    r"가-힣"             # 한글 음절
    r"一-鿿"             # 한자
    r" -⁯←-⋿①-⓿■-➿"  # 각종 기호
    r"＀-￯]+"           # 전각
)


def _clean(text: str) -> str:
    text = "".join(_KEEP.findall(text))
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return "\n".join(line.strip() for line in text.splitlines()).strip()


def hwp_text(data: bytes) -> str:
    """HWP 5.0 (OLE) 본문 텍스트."""
    ole = olefile.OleFileIO(io.BytesIO(data))
    try:
        compressed = bool(ole.openstream("FileHeader").read()[36] & 1)
        parts: list[str] = []
        for entry in sorted(e for e in ole.listdir() if e[0] == "BodyText"):
            raw = ole.openstream(entry).read()
            if compressed:
                raw = zlib.decompress(raw, -15)
            parts.append(_section_text(raw))
    finally:
        ole.close()
    return _clean("\n".join(parts))


def _section_text(raw: bytes) -> str:
    out: list[str] = []
    i = 0
    while i + 4 <= len(raw):
        value = struct.unpack("<I", raw[i:i + 4])[0]
        tag, size = value & 0x3FF, (value >> 20) & 0xFFF
        i += 4
        if size == 0xFFF:  # 크기가 12비트를 넘으면 뒤 4바이트가 실제 크기
            size = struct.unpack("<I", raw[i:i + 4])[0]
            i += 4
        payload, i = raw[i:i + size], i + size
        if tag != HWPTAG_PARA_TEXT:
            continue
        chars, j = [], 0
        while j + 1 < len(payload):
            ch = struct.unpack("<H", payload[j:j + 2])[0]
            if ch in EXTENDED_CONTROLS:
                j += 16
                continue
            j += 2
            if ch in (10, 13):
                chars.append("\n")
            elif ch >= 32:
                chars.append(chr(ch))
        out.append("".join(chars))
    return "\n".join(out)


def hwpx_text(data: bytes) -> str:
    """HWPX (ZIP+XML) 본문 텍스트."""
    parts = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = sorted(n for n in z.namelist() if re.match(r"Contents/section\d+\.xml", n))
        for name in names:
            xml = z.read(name).decode("utf-8", "ignore")
            xml = xml.replace("</hp:p>", "\n")
            parts.append(re.sub(r"<[^>]+>", "", xml))
    return _clean("\n".join(parts))


def pdf_text(data: bytes, max_pages: int = 40) -> str:
    """PDF 본문 텍스트 (학교가 안내문을 PDF 로 올리는 경우)."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return _clean("\n".join((p.extract_text() or "") for p in reader.pages[:max_pages]))


def extract(data: bytes, filename: str = "") -> str:
    """확장자나 매직바이트로 형식을 판단해 본문을 뽑는다."""
    if data[:5] == b"%PDF-" or filename.lower().endswith(".pdf"):
        return pdf_text(data)
    if data[:4] == b"PK\x03\x04" or filename.lower().endswith(".hwpx"):
        return hwpx_text(data)
    return hwp_text(data)
