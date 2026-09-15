# Whale AI Server

FastAPI 기반 칭찬고래 AI 서버입니다.

일기나 감정 문장을 입력하면 사용자가 스스로를 조금 더 따뜻하게 바라볼 수 있도록 짧은 칭찬/코칭 문장을 생성합니다.

## 시작하기

```bash
python -m pip install -r requirements.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

브라우저에서 아래 주소로 서버 상태를 확인합니다.

```text
http://127.0.0.1:8000/health
```

Swagger 문서는 아래 주소에서 확인합니다.

```text
http://127.0.0.1:8000/docs
```

## 환경 변수

서버 동작을 위해 아래 세 값이 모두 필요합니다.

| 변수 | 용도 |
|---|---|
| `OPENAI_API_KEY` | 임베딩(text-embedding-3-small) 및 생성(gpt-4o-mini) 호출 |
| `SUPABASE_URL` | pgvector가 설치된 Supabase 프로젝트 URL |
| `SUPABASE_KEY` | Supabase 서비스 키 (예시 검색 `match_examples`, 유저 장기기억 검색/저장 `match_user_memories` / `user_memories` insert에 사용) |

로컬에서는 PowerShell에서 직접 설정할 수 있습니다.

```powershell
$env:OPENAI_API_KEY = "sk-your-openai-api-key"
$env:SUPABASE_URL = "https://your-project-ref.supabase.co"
$env:SUPABASE_KEY = "your-service-role-key"
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

또는 프로젝트 루트에 `.env` 파일을 만들고 설정합니다.

```env
OPENAI_API_KEY=sk-your-openai-api-key
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_KEY=your-service-role-key
```

(`.env.example`은 예시 파일)

세 값 중 하나라도 없으면 서버는 뜨지만 요청 시 500(`환경변수가 설정되어 있지 않습니다`)을 반환합니다. `schema.sql`을 Supabase SQL Editor에서 먼저 실행해 `examples`/`user_memories` 테이블과 `match_examples`/`match_user_memories` 함수를 만들어둬야 합니다.

## 폴더 구조

```text
whale-data/
  main.py              # FastAPI 서버
  service_prompt.py    # 서비스 프롬프트 빌더
  requirements.txt     # Python 의존성
  Dockerfile           # Docker 실행 설정
  .dockerignore        # Docker 이미지 제외 파일
  .env.example         # 환경변수 예시

  out/                 # 서버가 참고하는 말투/예시 데이터
    coaching_fewshot_real.csv
    tone_reference.csv
    synthetic_dataset.jsonl

  seed/                # seed 데이터
    synthetic_seed.jsonl

  src/                 # synthetic 데이터 생성 코드
  eval/                # 평가 코드

  scripts/
    test_model.py      # Supabase 없이 GEN_MODEL만 단독 테스트
```

서버 실행에 직접 필요한 핵심 파일은 `main.py`, `service_prompt.py`, `out/`, `seed/`입니다.

## API

### Health Check

```text
GET /health
```

OpenAI API 키가 없어도 응답합니다.

응답 예시:

```json
{
  "status": "ok",
  "ready": false,
  "tone_phrases": 282,
  "startup_error": null
}
```

`ready`는 `/ai/whale-message`용 OpenAI/Supabase 클라이언트 준비 여부입니다.

### 인증

`/ai/*` 는 Supabase 세션 토큰이 필요합니다. `/health` 는 인증 없이 열려 있습니다(ECS 헬스체크가 사용).

```text
Authorization: Bearer <supabase access_token>
```

클라이언트에서 토큰 얻는 법:

```ts
const { data } = await supabase.auth.getSession();
const token = data.session?.access_token;
```

**`user_id` 는 요청 본문으로 받지 않습니다.** 본문 값은 클라이언트가 마음대로 채울 수 있어 남의 기억을 조회·저장할 수 있기 때문에, 서명이 검증된 토큰의 `sub` 만 신뢰합니다. 본문에 `user_id` 를 넣어도 무시됩니다.

검증은 Supabase 가 공개하는 JWKS(`{SUPABASE_URL}/auth/v1/.well-known/jwks.json`)의 공개키로 **서버 로컬에서** 처리합니다. 요청마다 Supabase 를 호출하지 않으며, 이를 위해 추가로 주입할 시크릿도 없습니다(`SUPABASE_URL` 에서 주소가 유도됨).

| 상황 | 응답 |
|---|---|
| 토큰 없음 | 401 |
| 서명 위조 · 만료 · 형식 오류 | 401 `유효하지 않은 토큰입니다.` |
| JWKS 를 가져오지 못함 (서버 측 장애) | 503 `인증 키를 가져오지 못했습니다.` |

### 고래 한마디 생성

```text
POST /ai/whale-message
```

일기/감정 입력을 받아 칭찬고래 문장을 생성합니다. 서버가 내부적으로 diary를 임베딩해 예시 풀(`match_examples`)과 해당 유저의 장기기억(`match_user_memories`)을 검색해 프롬프트에 반영합니다. **이 엔드포인트는 DB에 쓰지 않습니다.**

요청 예시:

```json
{
  "diary": "오늘은 3시에 퇴근함. 개피곤하네",
  "retry_count": 0
}
```

응답 예시:

```json
{
  "whale": "오늘 3시에 퇴근할 정도면 진짜 몸이 꽤 지쳤겠다. 그래도 오늘 하루를 끝까지 버티고 빠져나온 것만으로도 충분히 애썼어."
}
```

요청 필드:

| 필드 | 타입 | 필수 | 설명 |
|---|---|---:|---|
| `diary` | string | 예 | 사용자의 일기/감정 입력 |
| `draft_id` | string(uuid) | 아니오 | 클라이언트 측 초안 식별자 |
| `retry_count` | number | 아니오 | 재생성 횟수. 기본값은 0 |

`user_id`는 요청 본문에 넣지 않습니다. [인증](#인증) 참고.

Swagger에서 테스트할 때는 우측 상단 **Authorize** 로 토큰을 넣고, 본문에는 JSON만 입력합니다.

```json
{
  "diary": "오늘은 3시에 퇴근함. 개피곤하네",
  "retry_count": 0
}
```

### 장기기억 저장

```text
POST /ai/memory
```

"적용하기" 시점의 일기 원문을 임베딩해 `user_memories`에 적재합니다. 고래 답변이 아니라 **일기 원문**을 저장해야 다음 검색에서 자기 응답이 되돌아오는 self-retrieval을 막을 수 있습니다.

요청 필드:

| 필드 | 타입 | 필수 | 설명 |
|---|---|---:|---|
| `original_text` | string | 예 | 임베딩해 저장할 일기 원문 |
| `draft_id` | string(uuid) | 아니오 | 클라이언트 측 초안 식별자. 같은 값으로 두 번 보내면 두 번째는 무시됩니다 |
| `whale_message` | string | 아니오 | "적용하기" 시점에 화면에 떠 있던 고래 한마디 (트래킹용, 검색에는 안 씀) |
| `retry_count` | int | 아니오 | "다른 한마디"를 누른 횟수 (기본 0) |
| `rejected_messages` | array | 아니오 | 같은 draft 안에서 거절된 이전 제안들. `[{"whale_message": "...", "retry_count": 0}, ...]` |

기억 소유자(`user_id`)는 토큰에서 결정됩니다. [인증](#인증) 참고.

응답 예시:

```json
{ "ok": true }
```

### 장기기억 최종본 채우기

```text
PATCH /ai/memory
```

"적용하기" 시점엔 등록 전이라 최종 수정본을 알 수 없다. 유저가 실제로 "등록"을 눌러 게시글이 저장된 직후, 같은 `draft_id` 행에 최종 텍스트를 채워 넣는다.

요청 필드:

| 필드 | 타입 | 필수 | 설명 |
|---|---|---:|---|
| `draft_id` | string(uuid) | 예 | `POST /ai/memory` 때 쓴 것과 같은 값 |
| `edited_text` | string | 예 | 실제로 등록된 최종 텍스트 |

같은 `user_id` + `draft_id` 행이 없으면 조용히 아무 일도 하지 않습니다(0 rows updated). 응답은 `POST`와 동일하게 `{ "ok": true }`.

## PowerShell 테스트

서버를 켠 뒤 새 PowerShell 창에서 실행합니다.

```powershell
# 토큰은 앱에서 supabase.auth.getSession() 으로 얻은 access_token 을 넣습니다.
$token = "<supabase access_token>"

$body = @{
  diary = "오늘은 3시에 퇴근함. 개피곤하네"
  retry_count = 0
} | ConvertTo-Json

$res = Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/ai/whale-message" `
  -Method Post `
  -ContentType "application/json; charset=utf-8" `
  -Headers @{ Authorization = "Bearer $token" } `
  -Body $body

$res.whale
```

한글이 깨져 보이면 아래 설정 후 다시 실행합니다.

```powershell
chcp 65001
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
```

## 로컬 모델 테스트

Supabase 없이 `GEN_MODEL`(gpt-4o-mini)과 `service_prompt.py`의 검증기(`generate_with_guard`)만 빠르게 확인하고 싶을 때 사용합니다. `OPENAI_API_KEY`만 있으면 됩니다.

```bash
python scripts/test_model.py
```

내부에 정의된 상실/이별, 자책, 애매한 경계 등 다양한 일기 샘플을 순서대로 넣어보고 각각의 고래 답변과 검증 통과 여부를 출력합니다.

## Docker

이미지를 빌드합니다.

```bash
docker build -t whale-ai .
```

컨테이너를 실행합니다.

```bash
docker run --rm -p 8000:8000 -e OPENAI_API_KEY=$OPENAI_API_KEY whale-ai
```

PowerShell에서 환경변수를 넘길 때는 아래처럼 실행합니다.

```powershell
$env:OPENAI_API_KEY = "sk-your-openai-api-key"

docker run --rm -p 8000:8000 `
  -e OPENAI_API_KEY=$env:OPENAI_API_KEY `
  whale-ai
```

`.env` 파일을 사용할 수도 있습니다.

```bash
docker run --rm -p 8000:8000 --env-file .env whale-ai
```

## 모델

OpenAI 모델은 `main.py`에서 관리합니다.

```text
EMBED_MODEL = text-embedding-3-small
GEN_MODEL = gpt-4o-mini
```

임베딩 모델은 현재 일기와 비슷한 예시를 찾는 데 사용하고, 생성 모델은 최종 칭찬고래 답변을 만드는 데 사용합니다.

## 장기기억

서버가 Supabase pgvector(`user_memories` 테이블)에 유저별 장기기억을 직접 저장·검색합니다.

- 쓰기는 `POST /ai/memory`(적용하기)와 `PATCH /ai/memory`(등록)에서만 일어납니다. `/ai/whale-message`는 조회만 하고 DB에 쓰지 않습니다.
- 임베딩 대상은 항상 일기 원문(`content`)입니다. 고래 답변이나 요약을 임베딩하지 않습니다(자기 응답이 되돌아오는 self-retrieval 방지). `whale_message`/`edited_text`는 트래킹용 컬럼일 뿐 검색에는 쓰이지 않습니다.
- 유사도 임계값은 0.35(`PAST_RECORD_SIM_THRESHOLD`, `main.py`)이며, 관련 기억이 없으면 빈 배열이 정상 결과입니다. 억지로 top-k를 채우지 않습니다.
- 한 행이 AI 보조 편집 한 사이클을 나타냅니다: `content`(수정 전 원문) → `whale_message`(고래 제안) + `retry_count`(재시도 횟수) → `edited_text`(등록된 최종본, 등록 전까지 NULL).

흐름:

```text
POST /ai/whale-message  → diary 임베딩 → match_examples + match_user_memories 조회 → 프롬프트 조합 → 고래 답변만 반환 (쓰기 없음)
POST /ai/memory          → original_text(일기 원문) 임베딩 → user_memories에 insert (whale_message, retry_count 포함)
PATCH /ai/memory         → 같은 draft_id 행의 edited_text를 등록된 최종 텍스트로 update
```

## 보안

- 실제 `OPENAI_API_KEY`는 코드에 넣지 않습니다.
- 실제 키가 들어간 `.env`는 GitHub에 올리지 않습니다.
- 운영 환경에서는 Secret Manager, Kubernetes Secret, 배포 플랫폼의 Environment Variables 기능으로 주입합니다.
- `service_role` 같은 관리자 키가 필요한 경우에도 앱/프론트/공개 저장소에 넣지 않습니다.

## 인프라 전달 정보

```text
앱 엔트리: main:app
실행 명령: uvicorn main:app --host 0.0.0.0 --port 8000
포트: 8000
필수 환경변수: OPENAI_API_KEY, SUPABASE_URL, SUPABASE_KEY
헬스체크: GET /health
고래 생성 API: POST /ai/whale-message  (DB 조회만, 쓰기 없음)
장기기억 저장 API: POST /ai/memory      (DB insert)
Swagger: GET /docs
```

운영에서는 `OPENAI_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`를 Secret/환경변수로 주입해야 합니다.

DB 쪽은 Supabase SQL Editor에서 `schema.sql`을 1회 실행해 초기화합니다 (`examples`/`user_memories` 테이블, `match_examples`/`match_user_memories` 함수).

현재 CORS는 전체 허용입니다.

```python
allow_origins=["*"]
```

운영 프론트 도메인이 확정되면 해당 도메인으로 제한하는 것을 권장합니다.

## 체크

문법 검사는 아래 명령어로 확인합니다.

```bash
python -m py_compile main.py service_prompt.py
```

서버 상태는 아래 명령어로 확인합니다.

```bash
curl http://127.0.0.1:8000/health
```

## AI Safety / Privacy

`POST /ai/whale-message`는 고래 답변과 함께 `safety`, `privacy` 메타데이터를 반환합니다.

```json
{
  "whale": "회사에서 무시당한 것 같아서 마음이 많이 가라앉았겠다구.",
  "safety": {
    "level": "safe",
    "flagged": false,
    "categories": [],
    "category_scores": {},
    "action": "generate",
    "resources": [],
    "is_risky": false,
    "risk_type": null
  },
  "privacy": {
    "masked": false,
    "types": []
  }
}
```

### Safety

AI safety는 OpenAI Moderation API와 한국어 맥락 분류 로직을 함께 사용합니다.

| level | is_risky | risk_type | action |
| --- | --- | --- | --- |
| `safe` | `false` | `null` | `generate` |
| `self_harm_support` | `true` | `self_harm` | `supportive_generation` |
| `self_harm_intent` | `true` | `self_harm` | `crisis_support` |
| `self_harm_instructions` | `true` | `self_harm` | `crisis_block_generation` |
| `policy_flagged` | `true` | `policy` | `policy_blocked` |

`crisis_support`, `crisis_block_generation`이면 GPT 생성을 건너뛰고 위기 안내 문장과 상담 전화 리소스를 반환합니다.

`policy_blocked`이면 GPT 생성을 건너뛰고 고정 차단 문장을 반환합니다.

```text
이 이야기는 내가 담아내기 어려운 주제야. 다른 이야기를 들려줄래?
```

### Privacy Masking

개인정보는 백엔드에서 AI 처리 전에 rule-based로 마스킹합니다. OpenAI API 호출, embedding, memory 저장에는 마스킹된 텍스트를 사용합니다.

| token | 대상 |
| --- | --- |
| `[PHONE]` | 전화번호 |
| `[EMAIL]` | 이메일 |
| `[ADDRESS]` | 주소 |
| `[ID_NUMBER]` | 주민등록번호 형식 |
| `[CARD]` | 카드번호 형식 |
| `[ACCOUNT]` | 계좌번호 형식 |

예시:

```text
입력: 내 번호는 010-1234-5678이고 메일은 test@example.com이야.
AI/DB 처리: 내 번호는 [PHONE]이고 메일은 [EMAIL]이야.
```

응답의 `privacy` 필드는 마스킹 여부와 탐지된 타입을 알려줍니다.

```json
{
  "privacy": {
    "masked": true,
    "types": ["EMAIL", "PHONE"]
  }
}
```

### Local Test

Supabase/JWT 없이 개인정보 마스킹만 테스트할 수 있습니다.

```powershell
py scripts/test_privacy_masking_local.py
```

직접 문장을 넣어 테스트할 수도 있습니다.

```powershell
py scripts/test_privacy_masking_local.py "내 번호는 010-1234-5678이고 메일은 test@example.com이야"
```

OpenAI moderation/safety까지 함께 테스트하려면 `OPENAI_API_KEY`만 설정하면 됩니다. Supabase 값은 필요 없습니다.

```powershell
$env:OPENAI_API_KEY="sk-..."
py scripts/test_privacy_masking_local.py --with-openai
```

프론트 전달사항은 `FRONTEND_HANDOFF.md`를 참고합니다.
