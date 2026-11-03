"""HTTPS 연결 준비.

학교 서버(www.seoultech.ac.kr 등)가 중간 인증서를 함께 보내지 않는다.
브라우저는 중간 인증서를 스스로 받아오지만, 파이썬은 그러지 않아서
"unable to get local issuer certificate" 로 연결이 끊긴다.

그래서 기본 인증서 묶음(certifi)에 모자란 중간 인증서(certs/*.pem)를 더한
묶음 파일을 만들어 두고, requests 가 그것을 쓰도록 환경변수로 지정한다.
윈도우·리눅스 어디서 돌려도 같은 방식으로 동작한다 (배포 서버 포함).

검증을 끄는 방식(verify=False)은 쓰지 않는다 — 중간자 공격에 그대로 노출되기 때문.
"""
from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

log = logging.getLogger("kwakbot.net")

ROOT = Path(__file__).resolve().parent.parent
EXTRA_CERT_DIR = ROOT / "certs"
_bundle: Path | None = None


def _build_bundle() -> Path | None:
    """certifi 묶음 + certs/*.pem 을 합친 임시 파일을 만든다."""
    try:
        import certifi
    except ImportError:
        log.warning("certifi 가 없어 기본 인증서 설정을 그대로 씁니다.")
        return None

    extras = sorted(EXTRA_CERT_DIR.glob("*.pem")) if EXTRA_CERT_DIR.exists() else []
    if not extras:
        return Path(certifi.where())

    parts = [Path(certifi.where()).read_text(encoding="utf-8")]
    parts += [p.read_text(encoding="utf-8") for p in extras]
    out = Path(tempfile.gettempdir()) / "kwakbot-ca-bundle.pem"
    out.write_text("\n".join(parts), encoding="utf-8", newline="\n")
    log.info("인증서 묶음 준비: certifi + 추가 %d개 → %s", len(extras), out.name)
    return out


def use_system_certificates() -> bool:
    """수집기들이 import 할 때 호출. 성공하면 True."""
    global _bundle
    if _bundle is not None:
        return True

    bundle = _build_bundle()
    if bundle is None:
        return False
    _bundle = bundle
    # requests / urllib / openssl 계열이 모두 이 묶음을 쓰게 한다
    os.environ.setdefault("REQUESTS_CA_BUNDLE", str(bundle))
    os.environ.setdefault("SSL_CERT_FILE", str(bundle))

    # 윈도우에서는 OS 인증서 저장소도 함께 쓰면 더 안전하다 (중간 인증서 자동 조회)
    try:
        import truststore

        truststore.inject_into_ssl()
    except Exception:
        pass
    return True


use_system_certificates()
