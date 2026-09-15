"""
칭찬고래 AI 서버 — FastAPI
===========================
play.py의 로컬 루프를 HTTP API로 바꾼 것이다.
예시는 Supabase pgvector에서 유사도 검색하고, GPT 호출은 검증기(generate_with_guard)를 거친다.

엔드포인트:
  GET   /health              → 서버 상태 확인 (인증 불필요)
  POST  /ai/whale-message    → 일기 입력 → 고래 한마디 반환 (인증 필요)
  POST  /ai/memory           → 원문 + 고래 한마디 저장 → 유저 장기기억(user_memories)에 적재 (인증 필요)
  PATCH /ai/memory           → 등록 시점의 최종 수정본을 같은 draft_id 행에 채워 넣음 (인증 필요)
  POST  /ai/client-timing    → 앱이 잰 왕복 시간을 로그로만 남김 (인증 필요, 측정용)

지연 측정: /ai/* 요청은 요청당 한 줄 `[latency] {json}` 으로 구간을 남긴다.
쿼리 예시와 벤치 방법은 scripts/bench_whale_message.py 위쪽 주석 참고.

/ai/* 는 Supabase 세션 토큰이 필요하다. user_id 는 요청 본문이 아니라 토큰에서
꺼내므로 클라이언트가 남의 id 를 보내도 소용이 없다. 자세한 내용은 _current_user_id 참고.
"""
from __future__ import annotations

import csv, json, os, random, re, time
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock
from uuid import UUID

import jwt
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from openai import OpenAI
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from supabase import Client, create_client

from ai_safety import (
    CRISIS_WHALE_MESSAGE,
    CRISIS_RESOURCES,
    MODERATION_MODEL,
    POLICY_BLOCKED_MESSAGE,
    SafetyDecision,
    classify_safety,
    parse_moderation_result,
    merge_safety_decisions,
    risk_type_for_level,
    should_block_policy_generation,
    should_policy_block_before_generation,
    should_skip_context_classifier,
    should_skip_generation,
)
from crypto_utils import decrypt_text, encrypt_rejected_messages, encrypt_text, ensure_key_configured
from privacy_masking import MaskingResult, mask_sensitive_info
import service_prompt as sp

# ── 경로 설정 ────────────────────────────────────────────────
ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
TONE_REFERENCE = ROOT / "out" / "tone_reference.csv"

EMBED_MODEL = "text-embedding-3-small"
GEN_MODEL = "gpt-4o-mini"
GEN_MAX_TOKENS = 220
SAFETY_CONTEXT_MODEL = "gpt-4o-mini"
SAFETY_CONTEXT_MAX_TOKENS = 80
TOP_EXAMPLES = 4
TOP_TONE_PHRASES = 6
TOP_PAST_RECORDS = 3
PAST_RECORD_SIM_THRESHOLD = 0.35

# ── 인증 설정 ────────────────────────────────────────────────
# Supabase 는 토큰을 비대칭 키로 서명하고 공개키를 JWKS 로 공개한다. 덕분에 서버가
# 공개키만 받아 두면 요청마다 Supabase 에 물어볼 필요 없이 로컬에서 검증할 수 있고,
# 따로 주입할 시크릿도 없다 (SUPABASE_URL 에서 JWKS 주소가 유도된다).
#
# HS256(대칭키)은 의도적으로 넣지 않는다. 공개키를 HMAC 비밀키로 오인하게 만드는
# alg confusion 공격이 가능해지기 때문이다.
JWT_ALGORITHMS = ["ES256", "RS256"]
JWT_AUDIENCE = "authenticated"
# 서버 간 시계 오차 허용치. 실측 시 로컬-Supabase 간 11초 차이가 관측됐고,
# 이게 없으면 정상 토큰이 iat/exp 검사에서 401 로 튕긴다.
JWT_LEEWAY_SECONDS = 60

# ── 전역 상태 (서버 시작 시 1회 초기화) ───────────────────────
_client: OpenAI | None = None
_supabase: Client | None = None
_jwks_client: jwt.PyJWKClient | None = None
_tone_pool: list[str] = []
_ready = False
_startup_error: str | None = None
_init_lock = Lock()
_bearer_scheme = HTTPBearer(description="Supabase 세션의 access_token")


# ── 헬퍼 ───────────────────────────────────────────────────
def _embed_batch(texts: list[str]) -> list[list[float]]:
    """여러 텍스트를 한 번의 API 호출로 임베딩 (요청당 왕복 횟수 절감)."""
    if _client is None:
        raise RuntimeError("OpenAI client is not initialized")
    if not texts:
        return []
    r = _client.embeddings.create(model=EMBED_MODEL, input=texts)
    return [d.embedding for d in r.data]


def _match_examples(qvec: list[float], k: int) -> list[dict]:
    """Supabase pgvector에서 유사 예시 top-k를 검색한다."""
    if _supabase is None:
        raise RuntimeError("Supabase client is not initialized")
    resp = _supabase.rpc(
        "match_examples",
        {"query_embedding": qvec, "match_count": k},
    ).execute()
    # v4 few-shot은 anchor/appraisal/empathy/reframe/reply 를 그대로 시연한다.
    # match_examples 는 이 필드가 채워진 행만 돌려주므로(schema_v4_examples.sql),
    # 아직 백필되지 않은 예시는 애초에 여기까지 오지 않는다.
    return [
        {
            "input": r["input"],
            "output": r["output"],
            "anchor": r["anchor"],
            "appraisal": r.get("appraisal") or "",
            "empathy": r.get("empathy") or "",
            "reframe": r.get("reframe") or "none",
            "reply": r.get("reply") or r["output"],
        }
        for r in (resp.data or [])
    ]


def _match_user_memories(user_id: str, qvec: list[float], k: int = TOP_PAST_RECORDS) -> list[str]:
    if _supabase is None:
        raise RuntimeError("Supabase client is not initialized")
    resp = _supabase.rpc(
        "match_user_memories",
        {
            "p_user_id": user_id,
            "query_embedding": qvec,
            "match_count": k,
            "min_similarity": PAST_RECORD_SIM_THRESHOLD,
        },
    ).execute()
    # content 는 암호문으로 저장돼 있다 (crypto_utils.encrypt_text). RPC 는 p_user_id
    # 로 이미 필터링해서 돌려주므로, 그 값을 그대로 AAD 로 써서 복호화한다.
    return [decrypt_text(r["content"], aad=user_id) for r in (resp.data or [])]


def _insert_user_memory(
    user_id: str,
    content: str,
    vec: list[float],
    draft_id: str | None,
    whale_message: str | None,
    retry_count: int,
    rejected_messages: list[dict] | None,
) -> None:
    """일기 원문 + 고래 한마디를 장기기억에 적재한다. ("적용하기" 시점)

    draft_id 에는 unique 인덱스(user_memories_draft_uniq)가 걸려 있다.
    유저가 "적용하기"를 두 번 눌러도 같은 일기가 두 번 쌓이면 안 되므로,
    같은 draft_id 가 이미 있으면 에러 대신 조용히 무시한다(on conflict do nothing).
    draft_id 가 None 이면 NULL 은 서로 충돌하지 않으므로 그냥 새 행으로 쌓인다.

    edited_text 는 여기서 채우지 않는다 — "적용하기" 시점엔 아직 등록 전이라
    최종 수정본을 모른다. 등록 시점에 _finalize_user_memory 가 채운다.

    rejected_messages 는 같은 draft 안에서 "다른 한마디"로 거절된 이전 제안들이다.
    "첫 제안이 별로였다"는 것 자체가 선호 신호라, 최종 적용본만 남기면 사라진다.

    content/whale_message/rejected_messages 는 여기서 AES-256-GCM 으로 암호화해서
    넣는다 (crypto_utils.py). embedding 은 pgvector 가 DB 안에서 코사인 연산을
    해야 하므로 암호화하지 않고 평문 벡터 그대로 넣는다 — 검색은 벡터로, 표시는
    암호문 컬럼으로 분리되어 있다.
    """
    if _supabase is None:
        raise RuntimeError("Supabase client is not initialized")
    _supabase.table("user_memories").upsert(
        {
            "user_id": user_id,
            "kind": "diary",
            "content": encrypt_text(content, aad=user_id),
            "draft_id": draft_id,
            "embedding": vec,
            "whale_message": encrypt_text(whale_message, aad=user_id),
            "retry_count": retry_count,
            "rejected_messages": encrypt_rejected_messages(rejected_messages or [], aad=user_id),
        },
        on_conflict="draft_id",
        ignore_duplicates=True,
    ).execute()


def _finalize_user_memory(user_id: str, draft_id: str, edited_text: str) -> None:
    """등록 시점에 실제로 게시된 최종 수정본을 같은 draft_id 행에 채운다.

    user_id 까지 조건에 걸어야 한다 — service key 는 RLS 를 우회하므로,
    여기서 막지 않으면 남의 draft_id 를 넣어 엉뚱한 행을 덮어쓸 수 있다.

    edited_text 도 _insert_user_memory 의 content 와 같은 방식(AES-256-GCM,
    aad=user_id)으로 암호화해서 넣는다.
    """
    if _supabase is None:
        raise RuntimeError("Supabase client is not initialized")
    _supabase.table("user_memories").update(
        {"edited_text": encrypt_text(edited_text, aad=user_id)}
    ).eq("draft_id", draft_id).eq("user_id", user_id).execute()


def _get_jwks_client() -> jwt.PyJWKClient:
    """JWKS 클라이언트를 1회만 만들어 재사용한다 (공개키를 캐시해 매 요청 왕복을 없앤다)."""
    global _jwks_client
    if _jwks_client is None:
        url = os.environ["SUPABASE_URL"].rstrip("/") + "/auth/v1/.well-known/jwks.json"
        _jwks_client = jwt.PyJWKClient(url, cache_keys=True)
    return _jwks_client


def _current_user_id(
    request: Request,
    cred: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> UUID:
    """Authorization: Bearer <access_token> 을 검증하고 user_id 를 돌려준다.

    user_id 를 요청 본문으로 받지 않는 이유: 본문 값은 클라이언트가 마음대로 쓸 수
    있어서 남의 기억을 조회·저장할 수 있다. 서명이 검증된 토큰의 sub 만 신뢰한다.

    PyJWKClient 의 JWK set 캐시는 수명이 기본 300초라, 5분에 한 번은 Supabase 로
    JWKS 를 다시 받아오는 왕복이 섞인다. 그 비용이 얼마인지 보려고 시간을 재서
    request.state 에 남긴다 (timing_middleware 가 읽어 간다).
    """
    t_auth_start = time.perf_counter()
    try:
        _ensure_ready()
        token = cred.credentials

        try:
            signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
        except jwt.PyJWKClientConnectionError as exc:
            # JWKS 를 못 받아온 것은 클라이언트 잘못이 아니므로 401 이 아니라 503 이다.
            raise HTTPException(status_code=503, detail="인증 키를 가져오지 못했습니다.") from exc
        except jwt.PyJWTError as exc:
            # 형식이 깨진 토큰(DecodeError)이나 JWKS 에 없는 kid 로 서명된 토큰.
            # 이 단계에서 안 잡으면 그대로 500 이 된다.
            raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.") from exc

        try:
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=JWT_ALGORITHMS,
                audience=JWT_AUDIENCE,
                leeway=JWT_LEEWAY_SECONDS,
            )
        except jwt.PyJWTError as exc:
            raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.") from exc

        sub = claims.get("sub")
        if not sub:
            raise HTTPException(status_code=401, detail="토큰에 사용자 정보가 없습니다.")
        try:
            return UUID(sub)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail="토큰의 사용자 정보가 올바르지 않습니다.") from exc
    finally:
        request.state.t_auth = time.perf_counter() - t_auth_start


def _load_tone_phrases() -> list[str]:
    if not TONE_REFERENCE.exists():
        return []
    with open(TONE_REFERENCE, encoding="utf-8") as f:
        return [r["text"].strip() for r in csv.DictReader(f) if r.get("text") and r["text"].strip()]


def _ensure_ready() -> None:
    global _client, _supabase, _ready, _startup_error

    if _ready:
        return

    with _init_lock:
        if _ready:
            return

        missing = [
            v for v in ("OPENAI_API_KEY", "SUPABASE_URL", "SUPABASE_KEY", "MEMORY_ENC_KEY") if not os.getenv(v)
        ]
        if missing:
            raise HTTPException(status_code=500, detail=f"환경변수가 설정되어 있지 않습니다: {', '.join(missing)}")

        try:
            ensure_key_configured()  # 형식(base64/32바이트)이 틀리면 첫 요청이 아니라 여기서 바로 500
            _client = OpenAI()
            _supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
            _ready = True
            _startup_error = None
        except Exception as exc:
            _startup_error = str(exc)
            raise HTTPException(status_code=500, detail=f"AI 초기화에 실패했습니다: {_startup_error}") from exc


# ── Lifespan (시작·종료 훅) ──────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _tone_pool
    _tone_pool = _load_tone_phrases()
    print(f"서버 준비 완료. 말투 조각 {len(_tone_pool)}개.")
    yield


# ── FastAPI 앱 ───────────────────────────────────────────────
app = FastAPI(title="칭찬고래 AI", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],    # 실서비스 시 프론트엔드 도메인으로 제한
    allow_methods=["*"],
    allow_headers=["*"],
    # 브라우저는 기본적으로 몇 개 헤더만 JS 에 노출한다. 명시하지 않으면
    # 클라이언트에서 response.headers.get("Server-Timing") 이 항상 null 이 된다.
    expose_headers=["Server-Timing", "X-Whale-Latency"],
)


def _fmt(seconds: float | None) -> str:
    return "-" if seconds is None else f"{seconds:.2f}s"


def _ms(seconds: float | None) -> int | None:
    """초 → 정수 밀리초. Logs Insights 가 숫자 필드로 파싱해야 stats/pct 가 먹는다."""
    return None if seconds is None else round(seconds * 1000)


def _issue_label(issue: str, limit: int = 60) -> str:
    """검증 이슈에서 진단부만 뽑는다.

    이슈 문자열은 "무엇이 틀렸나 → 어떻게 고쳐라" 형태고, 뒤쪽 교정 지시는 모델에게
    주는 것이라 로그에선 길기만 하다. 앞부분만 남겨야 CloudWatch 에서 규칙별로
    몇 번 걸렸는지 세어 볼 수 있다.
    """
    label = issue.split(" → ", 1)[0].strip()
    return label if len(label) <= limit else label[:limit] + "…"


# 이슈 문자열에는 「걸린 문장」이나 (41자, 최소 60자 필요) 같은 그 요청만의 값이 붙는다.
# 집계용 필드에 그대로 넣으면 요청마다 값이 달라져 by guard_rules 로 세는 게 무의미해지고,
# 「」 안에는 일기에서 복사된 조각이라 원문이 로그에 남는다. 규칙 이름만 남긴다.
_RULE_DETAIL = re.compile(r"[「『][^」』]*[」』]|\([^)]*\)")


def _rule_key(issue: str) -> str:
    return _RULE_DETAIL.sub("", issue.split(" → ", 1)[0]).split(":", 1)[0].strip(" :")


# 핸들러 안에서 재는 시간에는 인증(JWKS 왕복)·본문 파싱·스레드풀 대기가 빠져 있다.
# 프론트의 왕복 시간(11~13s)과 서버 로그(수 초)가 어긋나는 구간이 바로 거기라,
# 핸들러 바깥에서 한 겹 더 잰다. 잰 값은 Server-Timing 헤더로도 돌려주므로
# 클라이언트가 "네트워크 = 왕복 - 서버전체" 를 바로 계산할 수 있다.
#
# 로그는 요청당 딱 한 줄, JSON 으로 찍는다. 구간마다 print 를 흩뿌리면 CloudWatch
# 에서 한 요청의 조각들을 다시 붙여야 해서 p95 를 뽑을 수가 없다. 한 줄로 모으면
# Logs Insights 가 필드로 파싱해 주므로 아래 쿼리가 그대로 먹는다:
#
#   fields @timestamp, total_ms, gen_ms, gpt_calls, guard_attempts
#   | filter ep = "/ai/whale-message"
#   | stats count(*), pct(total_ms,50), pct(total_ms,95), max(total_ms) by guard_attempts
@app.middleware("http")
async def timing_middleware(request: Request, call_next):
    t0 = time.perf_counter()
    # 첫 요청은 OpenAI/Supabase 클라이언트 초기화(_ensure_ready)를 떠안는다.
    # 이걸 구분해 두지 않으면 배포 직후 한 건이 p95 를 통째로 끌어올린다.
    cold = not _ready
    response = await call_next(request)
    total = time.perf_counter() - t0

    # request.state 는 ASGI scope 에 붙어 있어서 미들웨어와 핸들러가 같은 dict 를
    # 본다. 핸들러/의존성이 남겨 둔 구간값을 여기서 그대로 읽는다.
    t_auth = getattr(request.state, "t_auth", None)
    t_handler = getattr(request.state, "t_handler", None)
    phases: dict = getattr(request.state, "latency_marks", None) or {}

    marks = [f"total;dur={total * 1000:.0f}"]
    if t_auth is not None:
        marks.append(f"auth;dur={t_auth * 1000:.0f}")
    if t_handler is not None:
        marks.append(f"handler;dur={t_handler * 1000:.0f}")
    for name in ("mod", "embed", "gen"):
        value = phases.get(f"{name}_ms")
        if value is not None:
            marks.append(f"{name};dur={value}")
    response.headers["Server-Timing"] = ", ".join(marks)

    # /health 는 로드밸런서가 수 초마다 때려서 로그를 덮어버린다. /ai/* 만 남긴다.
    if request.url.path.startswith("/ai/"):
        record = {
            "ep": request.url.path,
            "method": request.method,
            "status": response.status_code,
            "total_ms": _ms(total),
            "auth_ms": _ms(t_auth),
            "handler_ms": _ms(t_handler),
            # 인증도 핸들러도 아닌 구간(본문 파싱, 스레드풀 대기, 응답 직렬화).
            # 여기가 크면 워커가 모자란 것이라 코드가 아니라 배포 설정을 봐야 한다.
            "other_ms": _ms(total - (t_auth or 0.0) - (t_handler or 0.0)),
            "cold": cold,
            **phases,
        }
        print(f"[latency] {json.dumps(record, ensure_ascii=False, separators=(',', ':'))}")

        # 벤치 스크립트가 CloudWatch 를 거치지 않고 바로 구간을 읽을 수 있게 헤더로도
        # 돌려준다. 헤더는 latin-1 로 인코딩되므로 한글이 섞인 값(guard_rules)은 뺀다.
        numeric = {k: v for k, v in record.items() if isinstance(v, (int, float, bool)) or v is None}
        response.headers["X-Whale-Latency"] = json.dumps(numeric, separators=(",", ":"))
    return response


# ── 요청 / 응답 스키마 ────────────────────────────────────────
# user_id 는 본문에 없다 — Authorization 헤더의 토큰에서 꺼낸다(_current_user_id).
# draft_id 는 UUID 로 받는다. str 로 두면 형식이 틀린 값이 그대로 Postgres 까지
# 내려가 22P02 로 터지면서 500 이 된다. UUID 로 선언하면 FastAPI 가 422 로 돌려준다.
class WhaleRequest(BaseModel):
    diary: str
    draft_id: UUID | None = None
    retry_count: int = 0


class SafetyInfo(BaseModel):
    level: str
    flagged: bool
    categories: list[str] = Field(default_factory=list)
    category_scores: dict[str, float] = Field(default_factory=dict)
    action: str
    resources: list[dict[str, str]] = Field(default_factory=list)
    is_risky: bool
    risk_type: str | None = None


class PrivacyInfo(BaseModel):
    masked: bool
    types: list[str] = Field(default_factory=list)


class WhaleResponse(BaseModel):
    whale: str
    safety: SafetyInfo | None = None
    privacy: PrivacyInfo | None = None


class RejectedMessage(BaseModel):
    whale_message: str
    retry_count: int


class MemoryRequest(BaseModel):
    original_text: str
    draft_id: UUID | None = None
    whale_message: str | None = None
    retry_count: int = 0
    rejected_messages: list[RejectedMessage] = []


class MemoryFinalizeRequest(BaseModel):
    draft_id: UUID
    edited_text: str


class ClientTiming(BaseModel):
    """앱이 실제로 체감한 왕복 시간. 서버 로그만으로는 안 보이는 구간을 채운다.

    서버가 3초에 끝나도 사용자가 기다린 시간은 그보다 길다. 그 차이(TLS 핸드셰이크,
    모바일 네트워크, JSON 파싱)를 서버 로그와 같은 로그 그룹에 남겨야 draft_id 로
    이어 붙여서 "체감 10초 중 서버 몇 초"를 한 화면에서 볼 수 있다.

    길이 상한을 두는 이유: 이 엔드포인트는 클라이언트가 보낸 문자열을 그대로 로그에
    쓴다. 상한이 없으면 로그를 원하는 만큼 부풀릴 수 있다.
    """
    endpoint: str = Field(max_length=64)
    e2e_ms: int = Field(ge=0, le=600_000)
    server_total_ms: int | None = Field(default=None, ge=0, le=600_000)
    draft_id: UUID | None = None
    retry_count: int = Field(default=0, ge=0, le=100)
    ok: bool = True
    error: str | None = Field(default=None, max_length=120)
    platform: str | None = Field(default=None, max_length=32)
    app_version: str | None = Field(default=None, max_length=32)


def _moderate_diary(diary: str, marks: dict) -> SafetyDecision:
    if _client is None:
        raise RuntimeError("OpenAI client is not initialized")
    # moderation API 와 문맥 분류(gpt-4o-mini)는 별개의 OpenAI 왕복이다.
    # moderation 결과가 키워드나 표면 형태를 놓쳐도 diary 전체 맥락으로 정책 위반을
    # 판정할 수 있도록, 위기 조기 반환을 제외한 모든 diary에 문맥 분류를 적용한다.
    t0 = time.perf_counter()
    mod_resp = _client.moderations.create(
        model=MODERATION_MODEL,
        input=diary,
    )
    marks["mod_api_ms"] = _ms(time.perf_counter() - t0)

    moderation = parse_moderation_result(mod_resp.results[0])
    if should_skip_context_classifier(moderation):
        # 위기 판정·CSAE면 문맥 분류를 건너뛴다. mod_ctx_ms 가 없는 건 "안 돌았다"는 뜻.
        return moderation

    contextual_level = None
    t0 = time.perf_counter()
    contextual_level = _classify_diary_safety_context(diary)
    marks["mod_ctx_ms"] = _ms(time.perf_counter() - t0)

    return classify_safety(
        mod_resp.results[0],
        diary,
        contextual_level=contextual_level,
    )


def _moderate_generated_text(text: str, marks: dict) -> SafetyDecision:
    if _client is None:
        raise RuntimeError("OpenAI client is not initialized")

    t0 = time.perf_counter()
    response = _client.moderations.create(
        model=MODERATION_MODEL,
        input=text,
    )
    marks["output_mod_ms"] = _ms(time.perf_counter() - t0)
    # anchor 그라운딩 때문에 고래 답변이 diary 속 단어("싸웠다", "심한 말")를 그대로
    # 옮기는 경우가 많다. parse_moderation_result만 쓰면 입력 쪽에 있는 benign 폭력
    # 오탐 예외(merge_safety_decisions)를 안 타서, 일상적인 다툼 서술도 moderation이
    # violence로 잘못 반응하면 그대로 차단돼버린다. merge를 거쳐 같은 예외를 적용한다.
    return merge_safety_decisions(parse_moderation_result(response.results[0]), text=text)


def _classify_diary_safety_context(diary: str) -> str:
    if _client is None:
        raise RuntimeError("OpenAI client is not initialized")

    system = (
        "You classify Korean diary text for a mental-health support app. "
        "Judge the overall context, not isolated keywords. "
        "Return JSON only with one field: level. "
        "Allowed levels: safe, self_harm_support, self_harm_intent, self_harm_instructions, policy_flagged.\n\n"
        "Definitions:\n"
        "- safe: distress, sadness, burnout, regret, loneliness, anxiety, or ordinary conflict without self-harm risk.\n"
        "- self_harm_support: passive self-harm or suicide thoughts, past self-harm, urges, fear of losing control, eating self-punishment, or asking how to get help for self-harm. No clear immediate plan or method request.\n"
        "- self_harm_intent: imminent or planned self-harm/suicide, goodbye/final-message context, selected time/place, being alone with danger, inability to stay safe, or likely immediate action.\n"
        "- self_harm_instructions: asks for methods, preparation, concealment, location, lethal details, dose, rescue avoidance, or how to make self-harm more effective.\n"
        "- policy_flagged: non-self-harm violence, hate, harassment, illicit instructions, sexual content, sexual harassment, unwanted sexual messages, or wrongdoing.\n\n"
        "If uncertain between safe and self_harm_support, choose self_harm_support. "
        "If uncertain between self_harm_support and self_harm_intent, choose self_harm_intent only when the text implies near-term action or inability to stay safe. "
        "If the user asks to write sexual jokes, sexual messages, harassment, threats, insults, or wrongdoing toward another person, choose policy_flagged."
    )
    resp = _client.chat.completions.create(
        model=SAFETY_CONTEXT_MODEL,
        temperature=0,
        max_tokens=SAFETY_CONTEXT_MAX_TOKENS,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": diary},
        ],
    )
    try:
        obj = json.loads(resp.choices[0].message.content or "{}")
    except json.JSONDecodeError:
        return "safe"
    return str(obj.get("level") or "safe")


def _safety_info(decision: SafetyDecision) -> SafetyInfo:
    is_crisis = should_skip_generation(decision)
    return SafetyInfo(
        level=decision.level,
        flagged=decision.flagged,
        categories=decision.categories,
        category_scores=decision.category_scores,
        action=decision.action,
        resources=CRISIS_RESOURCES if is_crisis else [],
        is_risky=decision.level != "safe",
        risk_type=risk_type_for_level(decision.level),
    )


def _privacy_info(masking: MaskingResult) -> PrivacyInfo:
    return PrivacyInfo(masked=masking.masked, types=masking.types)


def _generate_whale_text(
    diary: str,
    past_records: list[str] | None,
    examples: list[dict] | None,
    tone_phrases: list[str],
    retry_count: int,
    marks: dict,
) -> str:
    if _client is None:
        raise RuntimeError("OpenAI client is not initialized")

    # generate_with_guard 는 검증 실패 시 GPT를 순차 재호출한다. 실측상 응답 시간의
    # 80%가 여기고, 그 안에서는 호출 횟수가 곧 지연이다(3회 = 7.60s). max_fix_attempts
    # 를 1로 줄인 게 이번에 검증할 수정이라, 횟수·회차별 소요시간과 "어떤 규칙에 걸려서
    # 다시 불렀는지"를 요청 로그 한 줄에 같이 실어 둔다. 규칙을 더 손보려면 근거가 있어야 한다.
    call_durations: list[float] = []
    attempt_rules: list[str] = []

    def call_llm(msgs):
        t0 = time.perf_counter()
        resp = _client.chat.completions.create(
            model=GEN_MODEL,
            temperature=0.7,
            max_tokens=GEN_MAX_TOKENS,
            response_format={"type": "json_object"},
            messages=msgs,
        )
        call_durations.append(time.perf_counter() - t0)
        return resp.choices[0].message.content

    def on_attempt(attempt: int, issues: list[str]) -> None:
        # on_attempt 는 그 회차의 call_llm 직후에 불리므로 인덱스가 1:1 로 맞는다.
        elapsed = call_durations[attempt - 1] if attempt <= len(call_durations) else None
        attempt_rules.extend(_rule_key(i) for i in issues)
        if not issues:
            print(f"[guard] {attempt}회차 {_fmt(elapsed)} 통과")
            return
        print(
            f"[guard] {attempt}회차 {_fmt(elapsed)} 실패 {len(issues)}건: "
            + " | ".join(_issue_label(i) for i in issues)
        )

    whale, issues = sp.generate_with_guard(
        call_llm,
        diary,
        past_records=past_records,
        examples=examples,
        tone_phrases=tone_phrases,
        retry_count=retry_count,
        on_attempt=on_attempt,
    )

    marks["gpt_calls"] = len(call_durations)
    marks["gpt_ms"] = _ms(sum(call_durations))
    # 회차별 값. 1회차만 느린 건지 매 호출이 고른지가 갈린다(전자면 프롬프트 길이,
    # 후자면 모델·리전 문제).
    marks["gpt_each_ms"] = ",".join(str(_ms(d)) for d in call_durations)
    marks["guard_attempts"] = len(call_durations)
    marks["guard_pass"] = not issues
    # generate_with_guard 는 구조 검증(JSON 파싱/anchor) 실패에만 재호출한다.
    # 말투/스타일 위반은 재호출 없이 그대로 반환하므로, guard_fallback=True 가
    # 곧 "재호출을 다 쓰고 실패"를 뜻하지 않는다 — 1회차에 말투 위반만 있어도 True.
    marks["guard_fallback"] = bool(issues)
    # 규칙별로 몇 번 걸렸는지 세려면 이름이 로그에 있어야 한다. 배열 대신 구분자
    # 문자열로 두는 건 Logs Insights 에서 `like /anchor/` 로 바로 필터하기 위해서다.
    marks["guard_rules"] = "|".join(dict.fromkeys(attempt_rules))

    if issues:
        print(
            f"[guard] 미해결 {len(issues)}건(재호출 없이 반환): "
            + " | ".join(_issue_label(i) for i in issues)
        )
    return whale.strip()


# ── 엔드포인트 ───────────────────────────────────────────────
@app.get("/health")
def health():
    return {
        "status": "ok",
        "ready": _ready,
        "tone_phrases": len(_tone_pool),
        "startup_error": _startup_error,
    }


@app.post("/ai/whale-message", response_model=WhaleResponse)
def get_whale(
    req: WhaleRequest,
    request: Request,
    user_id: UUID = Depends(_current_user_id),
):
    # 구간별 타이밍은 여기서 dict 에 쌓고, 미들웨어가 요청당 한 줄 JSON 으로 찍는다.
    # 조기 반환·예외로 빠져도 쌓인 만큼은 남도록 request.state 에 먼저 붙여 둔다.
    marks: dict = {}
    request.state.latency_marks = marks
    t_request_start = time.perf_counter()
    try:
        diary = req.diary.strip()
        if not diary:
            raise HTTPException(status_code=400, detail="diary는 비어 있으면 안 됩니다.")

        # 일기 길이는 프롬프트 토큰 수를 좌우한다. 지연이 길이에 비례하는지 봐야
        # "느린 요청"이 모델 문제인지 입력 문제인지 갈린다.
        marks["diary_len"] = len(diary)
        marks["retry_count"] = req.retry_count
        marks["draft_id"] = str(req.draft_id) if req.draft_id else None

        t0 = time.perf_counter()
        masked = mask_sensitive_info(diary)
        marks["mask_ms"] = _ms(time.perf_counter() - t0)
        marks["masked"] = masked.masked
        diary_for_ai = masked.text

        _ensure_ready()

        # moderation 은 OpenAI 왕복이 1~2회(모더레이션 + 조건부 문맥 분류)다.
        # 임베딩과 한 구간으로 묶어 재면 생성 앞단 비용이 통째로 "임베딩"으로 보인다.
        t0 = time.perf_counter()
        safety = _moderate_diary(diary_for_ai, marks)
        marks["mod_ms"] = _ms(time.perf_counter() - t0)

        # 차단으로 끝난 요청은 GPT 생성을 안 타서 훨씬 빠르다. 표시해 두지 않으면
        # 정상 요청과 섞여 p50 을 실제보다 낙관적으로 만든다.
        if should_skip_generation(safety):
            marks["early_return"] = "crisis"
            return WhaleResponse(
                whale=CRISIS_WHALE_MESSAGE,
                safety=_safety_info(safety),
                privacy=_privacy_info(masked),
            )
        if should_policy_block_before_generation(safety, diary_for_ai):
            marks["early_return"] = "policy"
            return WhaleResponse(
                whale=POLICY_BLOCKED_MESSAGE,
                safety=_safety_info(safety),
                privacy=_privacy_info(masked),
            )

        t0 = time.perf_counter()
        qvec = _embed_batch([diary_for_ai])[0]
        marks["embed_ms"] = _ms(time.perf_counter() - t0)

        # examples가 0개면 None으로 넘겨서 service_prompt.py의 DEFAULT_EXAMPLES 안전망이 켜지게 한다.
        t0 = time.perf_counter()
        examples = _match_examples(qvec, TOP_EXAMPLES) or None
        marks["examples_ms"] = _ms(time.perf_counter() - t0)

        # 과거 기억은 있으면 좋은 부가 정보다. 검색이 실패해도 한마디는 나가야 하므로
        # 여기서 삼키고 빈 리스트로 진행한다 (기억 없는 신규 유저와 같은 상태가 된다).
        t0 = time.perf_counter()
        try:
            past_records = _match_user_memories(str(user_id), qvec)
        except Exception as exc:
            print(f"[warn] 과거 기억 검색 실패, 기억 없이 진행합니다: {exc}")
            past_records = []
        marks["memories_ms"] = _ms(time.perf_counter() - t0)
        # 과거 기억이 붙으면 프롬프트가 길어진다. 기억 많은 계정이 느린지 보려면 개수가 필요하다.
        marks["memories"] = len(past_records)

        tone_phrases = random.sample(_tone_pool, min(TOP_TONE_PHRASES, len(_tone_pool))) if _tone_pool else []

        t0 = time.perf_counter()
        whale = _generate_whale_text(
            diary_for_ai,
            past_records=past_records,
            examples=examples,
            tone_phrases=tone_phrases,
            retry_count=req.retry_count,
            marks=marks,
        )
        marks["gen_ms"] = _ms(time.perf_counter() - t0)

        output_safety = _moderate_generated_text(whale, marks)
        if should_skip_generation(output_safety):
            marks["early_return"] = "output_crisis"
            return WhaleResponse(
                whale=CRISIS_WHALE_MESSAGE,
                safety=_safety_info(output_safety),
                privacy=_privacy_info(masked),
            )
        if should_block_policy_generation(output_safety):
            marks["early_return"] = "output_policy"
            return WhaleResponse(
                whale=POLICY_BLOCKED_MESSAGE,
                safety=_safety_info(output_safety),
                privacy=_privacy_info(masked),
            )

        return WhaleResponse(
            whale=whale,
            safety=_safety_info(safety),
            privacy=_privacy_info(masked),
        )
    finally:
        # 조기 반환·예외로 빠져나가도 미들웨어가 핸들러 구간을 알 수 있게 항상 남긴다.
        request.state.t_handler = time.perf_counter() - t_request_start


@app.post("/ai/memory")
def save_memory(req: MemoryRequest, user_id: UUID = Depends(_current_user_id)):
    text = req.original_text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="original_text는 비어 있으면 안 됩니다.")
    masked = mask_sensitive_info(text)
    text_for_storage = masked.text
    _ensure_ready()
    vec = _embed_batch([text_for_storage])[0]
    _insert_user_memory(
        str(user_id),
        text_for_storage,
        vec,
        str(req.draft_id) if req.draft_id else None,
        req.whale_message,
        req.retry_count,
        [m.model_dump() for m in req.rejected_messages],
    )
    return {"ok": True, "privacy": {"masked": masked.masked, "types": masked.types}}


@app.patch("/ai/memory")
def finalize_memory(req: MemoryFinalizeRequest, user_id: UUID = Depends(_current_user_id)):
    text = req.edited_text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="edited_text는 비어 있으면 안 됩니다.")
    masked = mask_sensitive_info(text)
    _ensure_ready()
    _finalize_user_memory(str(user_id), str(req.draft_id), masked.text)
    return {"ok": True, "privacy": {"masked": masked.masked, "types": masked.types}}


@app.post("/ai/client-timing")
def report_client_timing(req: ClientTiming, _: UUID = Depends(_current_user_id)):
    """앱이 잰 왕복 시간을 서버 로그로 옮긴다. 측정용이라 저장은 하지 않는다.

    인증을 거는 이유는 두 가지다. 아무나 로그를 채워 넣지 못하게 하는 것과,
    앱이 이미 들고 있는 토큰을 그대로 쓰면 되니 클라이언트 코드가 늘지 않는 것.

    OpenAI 도 DB 도 건드리지 않으므로 이 호출 자체는 측정 대상 지연에 영향을 주지
    않는다(앱에서도 응답을 기다리지 않고 fire-and-forget 으로 보낸다).
    """
    record = req.model_dump()
    record["draft_id"] = str(req.draft_id) if req.draft_id else None
    # 서버가 응답을 만든 뒤 앱이 받기까지 걸린 시간. 여기가 크면 코드가 아니라
    # 네트워크·리전 문제이므로 서버 최적화로는 안 줄어든다.
    if req.server_total_ms is not None:
        record["network_ms"] = max(0, req.e2e_ms - req.server_total_ms)
    print(f"[latency-client] {json.dumps(record, ensure_ascii=False, separators=(',', ':'))}")
    return {"ok": True}
