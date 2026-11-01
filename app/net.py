"""HTTPS 연결 준비.

학교 서버(www.seoultech.ac.kr 등)가 중간 인증서를 함께 보내지 않아서,
파이썬 기본 인증서 묶음(certifi)만으로는 "unable to get local issuer certificate" 로 연결이 끊긴다.
브라우저는 중간 인증서를 알아서 받아오기 때문에 사람 눈에는 멀쩡해 보인다.

운영체제 인증서 저장소를 쓰면(truststore) 중간 인증서를 자동으로 찾아 주므로 그대로 연결된다.
수집기들이 import 할 때 한 번만 적용하면 된다.
"""
from __future__ import annotations

import logging

log = logging.getLogger("kwakbot.net")
_applied = False


def use_system_certificates() -> bool:
    """OS 인증서 저장소를 쓰도록 전환. 성공하면 True."""
    global _applied
    if _applied:
        return True
    try:
        import truststore
    except ImportError:
        log.warning("truststore 가 설치돼 있지 않아 기본 인증서 묶음을 사용합니다.")
        return False
    truststore.inject_into_ssl()
    _applied = True
    return True


use_system_certificates()
