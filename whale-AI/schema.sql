-- ============================================================================
-- whale-AI · Supabase pgvector 스키마
-- ============================================================================
-- 예시 풀(examples) 테이블 + 유사도 검색 RPC(match_examples) 정의.
--
-- 이 파일은 Supabase 대시보드(SQL Editor)에서 1회 실행해 DB를 초기화한다.
-- 실행 후 `python scripts/seed_supabase.py` 로 예시를 적재한다.
--
-- 임베딩 차원: 1536 (OpenAI text-embedding-3-small)
-- 유사도: 코사인. match_examples 는 1 - (embedding <=> query) 로 similarity 를
--         [0,1] 범위(동일 벡터=1)로 반환한다.
-- ============================================================================

-- pgvector 확장 (Supabase 는 extensions 스키마에 설치)
create extension if not exists vector;

-- ── 예시 풀 테이블 ──────────────────────────────────────────────
create table if not exists public.examples (
    id        bigint generated always as identity primary key,
    input     text        not null,   -- 원본 일기 텍스트
    output    text        not null,   -- 변환된 결과 텍스트
    embedding vector(1536) not null    -- input 을 임베딩한 벡터
);

-- ── 코사인 유사도 검색 인덱스 ───────────────────────────────────
-- 행 수가 적으면 순차 스캔으로도 충분하지만, 데이터가 늘면 ANN 인덱스가 유리하다.
-- ivfflat 는 적재(시딩) 이후에 만들어야 리스트가 제대로 학습된다.
create index if not exists examples_embedding_cosine_idx
    on public.examples
    using ivfflat (embedding vector_cosine_ops)
    with (lists = 100);

-- ── 유사도 검색 RPC ─────────────────────────────────────────────
-- query_embedding 과 가까운 순으로 match_count 개를 반환한다.
create or replace function public.match_examples(
    query_embedding vector(1536),
    match_count     int
)
returns table (
    input      text,
    output     text,
    similarity float
)
language sql
stable
as $$
    select
        e.input,
        e.output,
        1 - (e.embedding <=> query_embedding) as similarity
    from public.examples e
    order by e.embedding <=> query_embedding
    limit match_count;
$$;

-- ============================================================================
-- 유저별 장기기억(user_memories) 테이블 + 검색 RPC(match_user_memories)
-- ============================================================================
-- user_id 에 references auth.users(id) 는 일부러 걸지 않는다 — 로컬에서
-- 임의 UUID 로 테스트하기 위함. FK 는 프론트 인증이 붙는 단계에서 추가한다.
-- (RLS 는 이 파일 마지막에서 켠다)

create table if not exists public.user_memories (
    id            bigint generated always as identity primary key,
    user_id       uuid not null,
    kind          text not null default 'diary',
    content       text not null,
    draft_id      uuid,
    embedding     vector(1536) not null,
    -- "적용하기" 시점에 함께 확정되는 값들.
    whale_message text,
    retry_count   int not null default 0,
    -- "등록" 시점에야 확정되는 값. 적용만 하고 등록을 안 하면 계속 NULL로 남는다.
    edited_text       text,
    -- 같은 draft 안에서 "다른 한마디"로 거절된 이전 제안들. [{"whale_message":..,"retry_count":..}, ...]
    -- 적용 자체를 안 하고 이탈한 세션은 여전히 이 테이블에 아예 안 남는다 (적용하기 시점에만 쓰기 때문).
    rejected_messages jsonb not null default '[]'::jsonb,
    created_at        timestamptz not null default now()
);

-- 기존 배포에 이미 테이블이 있는 경우를 위한 증분 마이그레이션.
alter table public.user_memories add column if not exists whale_message text;
alter table public.user_memories add column if not exists retry_count int not null default 0;
alter table public.user_memories add column if not exists edited_text text;
alter table public.user_memories add column if not exists rejected_messages jsonb not null default '[]'::jsonb;

-- ── 저장 형식 (crypto_utils.py, main.py 참고) ────────────────────
-- content / edited_text / whale_message 는 애플리케이션(main.py)이 AES-256-GCM
-- 으로 암호화한 base64 문자열을 그대로 넣는다 — 컬럼 타입은 바꿀 필요 없다(text 그대로).
-- rejected_messages 도 각 원소의 whale_message 필드만 같은 방식으로 암호화된
-- base64 문자열이고, retry_count 는 평문 그대로 둔다.
-- embedding 은 암호화하지 않는다 — match_user_memories 가 DB 안에서 <=> 코사인
-- 연산을 직접 해야 해서, 여기까지 암호화하면 서버 사이드 유사도 검색이 불가능해진다.
-- 키(MEMORY_ENC_KEY)가 없으면 이 컬럼들은 그냥 읽을 수 없는 바이트열이다 — DB가
-- 뚫려도(예: 서비스 키 유출) 내용 자체는 노출되지 않는다.
--
-- 주의: 이 마이그레이션 이전에 이미 쌓인 행은 content/edited_text/whale_message 가
-- 평문 그대로다. main.py 의 decrypt_text() 는 이런 행을 만나면 실패하는데,
-- _match_user_memories 호출부가 예외를 잡아 빈 리스트로 넘어가므로 500 은 나지 않고
-- 그 유저의 "과거 기억" 활용만 조용히 빠진다. 기존 행을 계속 쓰려면 별도 백필
-- 스크립트로 content 를 encrypt_text() 로 재저장해야 한다(다시 원문이 필요하므로,
-- 이 시점 이후에는 애초에 평문이 안 남아 백필도 불가능 — 운영 데이터가 있다면
-- 배포 전에 반드시 검토할 것).
comment on column public.user_memories.content is
    'AES-256-GCM 암호문(base64). crypto_utils.encrypt_text(aad=user_id) 로 생성.';
comment on column public.user_memories.edited_text is
    'AES-256-GCM 암호문(base64). content 와 동일한 방식.';
comment on column public.user_memories.whale_message is
    'AES-256-GCM 암호문(base64). content 와 동일한 방식.';
comment on column public.user_memories.rejected_messages is
    '[{"whale_message": "<AES-256-GCM 암호문(base64)>", "retry_count": int}, ...]';

-- 이 마이그레이션 이전(암호화 도입 전)에 쌓인 평문 행은
-- scripts/backfill_user_memories_encrypt.py 로 제자리에서 재암호화한다.
-- 별도 진행 표시 컬럼을 두지 않고, 이미 암호문인 값(crypto_utils.looks_encrypted)은
-- 스크립트가 자체적으로 건너뛰므로 몇 번을 다시 돌려도 안전하다(idempotent).

create index if not exists user_memories_user_idx
    on public.user_memories (user_id, created_at desc);

-- draft_id 중복 저장 방지 — "적용하기"를 두 번 눌러도 1행만 남는다.
-- 부분 인덱스(where draft_id is not null)로 만들면 안 된다: PostgREST 의 upsert 가
-- 만드는 `on conflict (draft_id) do nothing` 은 술어 없이는 부분 인덱스를 추론하지
-- 못한다. 일반 unique 인덱스도 NULL 은 서로 다른 값으로 보므로 draft_id 가 없는
-- 행은 그대로 여러 개 쌓인다.
create unique index if not exists user_memories_draft_uniq
    on public.user_memories (draft_id);

-- ivfflat 인덱스는 일부러 아직 만들지 않는다.
--   1) 빈 테이블에서 만들면 리스트(centroid)가 학습되지 않아 검색 품질이 떨어진다.
--   2) ivfflat 은 user_id 필터와 무관하게 후보를 뽑으므로, 유저가 늘면 내 기억이
--      후보에서 밀려 recall 이 떨어진다. 행이 적을 땐 순차 스캔이 더 정확하고 빠르다.
-- 수천 행 쌓인 뒤 아래를 실행할 것:
--   create index user_memories_embedding_idx
--       on public.user_memories using ivfflat (embedding vector_cosine_ops) with (lists = 100);

create or replace function public.match_user_memories(
    p_user_id       uuid,
    query_embedding vector(1536),
    match_count     int   default 3,
    min_similarity  float default 0.35
)
returns table (content text, created_at timestamptz, similarity float)
language sql stable as $$
    select m.content, m.created_at, 1 - (m.embedding <=> query_embedding) as similarity
    from public.user_memories m
    where m.user_id = p_user_id
      and m.kind = 'diary'
      and 1 - (m.embedding <=> query_embedding) >= min_similarity
    order by m.embedding <=> query_embedding
    limit match_count;
$$;

-- RLS: 서버는 secret 키라 RLS 를 우회하므로 동작에 영향이 없다.
-- 정책을 하나도 두지 않음으로써, 프론트가 publishable 키로 접근해도 남의 기억을
-- 읽을 수 없게 잠가둔다. 프론트에서 직접 조회할 일이 생기면 그때 정책을 추가한다.
alter table public.user_memories enable row level security;
