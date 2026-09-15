"""민감 텍스트를 DB에 넣기 전/꺼낸 후 AES-256-GCM 으로 암/복호화한다.

대상: user_memories.content / edited_text / whale_message, 그리고
rejected_messages 안의 whale_message. embedding 컬럼은 pgvector가 DB 안에서
코사인 연산(<=>)을 직접 해야 하므로 암호화하지 않는다 — 검색은 평문 벡터로,
표시용 텍스트는 이 모듈이 만드는 암호문으로 분리한다. (privacy_masking.py 의
정규식 마스킹은 이걸 대체하지 않는다 — 마스킹은 패턴에 안 걸리는 내용은 평문으로
남기는 손실 압축이고, 이 모듈은 저장된 값 자체를 읽지 못하게 만드는 것이라 목적이
다르다. 두 개를 같이 쓴다: 마스킹 후 텍스트를 암호화해서 저장한다.)

저장 형식: base64(nonce[12] || ciphertext || tag[16]) 문자열 하나 — 기존 text
컬럼에 그대로 들어간다(컬럼 타입 변경 불필요).

AAD 로 user_id 를 함께 묶는다. GCM 의 AAD 는 암호화되지 않지만 태그 검증에
포함되므로, 한 유저의 암호문 행을 다른 유저 행에 그대로 복사해 붙여도(예: 버그로
row-id 가 섞이는 경우) 복호화 시 InvalidTag 로 걸러진다.

키: MEMORY_ENC_KEY 환경변수에 base64 로 인코딩된 32바이트(AES-256) 키를 넣는다.
    생성: python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"
    로컬 .env 에 넣고, 배포 환경(ECS)에는 Secrets Manager/SSM 등으로 주입한다.
    키를 잃어버리면 이미 저장된 값은 복구할 수 없다 — 안전한 곳에 별도 백업해 둘 것.
"""
from __future__ import annotations

import base64
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_NONCE_LEN = 12  # GCM 표준 96bit nonce

_key: bytes | None = None


def _get_key() -> bytes:
    """MEMORY_ENC_KEY 를 1회만 읽어 캐시한다 (요청마다 env 조회/디코드 반복 방지)."""
    global _key
    if _key is not None:
        return _key

    raw = os.getenv("MEMORY_ENC_KEY")
    if not raw:
        raise RuntimeError(
            "MEMORY_ENC_KEY 환경변수가 없습니다. 생성: "
            'python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"'
        )
    try:
        key = base64.b64decode(raw, validate=True)
    except Exception as exc:
        raise RuntimeError("MEMORY_ENC_KEY 가 올바른 base64 문자열이 아닙니다.") from exc
    if len(key) != 32:
        raise RuntimeError(f"MEMORY_ENC_KEY 는 32바이트(AES-256)여야 합니다. 현재 {len(key)}바이트.")

    _key = key
    return _key


def _aad_bytes(aad: str | None) -> bytes | None:
    return aad.encode("utf-8") if aad is not None else None


def ensure_key_configured() -> None:
    """MEMORY_ENC_KEY 가 있고 형식이 맞는지 지금 확인한다.

    서버 기동/_ensure_ready 에서 미리 호출해 두면, 키가 없거나 32바이트가 아닐 때
    첫 암호화 요청 한복판이 아니라 시작 시점에 바로 실패한다.
    """
    _get_key()


def encrypt_text(plaintext: str | None, *, aad: str | None = None) -> str | None:
    """평문을 AES-256-GCM 으로 암호화해 base64 문자열로 돌려준다. None 은 그대로 None."""
    if plaintext is None:
        return None
    nonce = os.urandom(_NONCE_LEN)
    ct = AESGCM(_get_key()).encrypt(nonce, plaintext.encode("utf-8"), _aad_bytes(aad))
    return base64.b64encode(nonce + ct).decode("ascii")


def decrypt_text(blob: str | None, *, aad: str | None = None) -> str | None:
    """encrypt_text 로 만든 base64 문자열을 복호화한다. None 은 그대로 None.

    aad 는 encrypt_text 에 넘긴 값과 정확히 같아야 한다(보통 user_id) — 다르면
    (혹은 키가 바뀌었거나 데이터가 변조됐으면) InvalidTag → ValueError 로 실패한다.
    """
    if blob is None:
        return None
    raw = base64.b64decode(blob)
    nonce, ct = raw[:_NONCE_LEN], raw[_NONCE_LEN:]
    try:
        pt = AESGCM(_get_key()).decrypt(nonce, ct, _aad_bytes(aad))
    except InvalidTag as exc:
        raise ValueError("복호화 실패: 키/AAD 불일치 또는 데이터 변조") from exc
    return pt.decode("utf-8")


def looks_encrypted(value: str | None) -> bool:
    """value 가 encrypt_text 로 만든 base64 암호문처럼 보이면 True.

    실제로 복호화해서 확인하지는 않는다(AAD 를 모르면 확인 자체가 안 됨) — 백필
    스크립트가 "이미 암호화된 값을 또 암호화하는" 사고를 막는 용도의 휴리스틱이다.
    한국어 일기 평문이 우연히 이 조건(길이 28바이트 이상의 순수 base64)을 만족할
    가능성은 사실상 없다(한글 UTF-8 바이트는 base64 문자셋 밖의 문자를 만든다).
    """
    if not value:
        return False
    try:
        raw = base64.b64decode(value, validate=True)
    except Exception:
        return False
    return len(raw) >= _NONCE_LEN + 16  # nonce(12) + GCM tag(16) 최소 길이


def encrypt_rejected_messages(messages: list[dict], *, aad: str | None = None) -> list[dict]:
    """rejected_messages 리스트의 whale_message 만 암호화한다. retry_count 는 평문 유지."""
    return [{**m, "whale_message": encrypt_text(m.get("whale_message"), aad=aad)} for m in messages]


def decrypt_rejected_messages(messages: list[dict], *, aad: str | None = None) -> list[dict]:
    """encrypt_rejected_messages 의 역연산. 현재 서버 코드는 이 값을 다시 읽지 않지만,
    추후 관리자 도구/디버깅에서 필요할 수 있어 대칭으로 제공한다."""
    return [{**m, "whale_message": decrypt_text(m.get("whale_message"), aad=aad)} for m in messages]
