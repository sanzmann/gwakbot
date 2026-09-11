"""data/ 폴더의 마크다운 파일을 읽어 곽봇의 지식 베이스 문자열로 합친다."""
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_knowledge() -> str:
    """data/*.md 를 파일명 순으로 읽어 하나의 문자열로 반환."""
    parts = []
    for path in sorted(DATA_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8").strip()
        if text:
            parts.append(f"<document name=\"{path.name}\">\n{text}\n</document>")
    return "\n\n".join(parts)
