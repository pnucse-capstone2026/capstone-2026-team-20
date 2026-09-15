-- ============================================================================
-- examples 테이블 v4 구조화 필드 추가
-- ============================================================================
-- Supabase 대시보드(SQL Editor)에서 1회 실행한다.
--
-- 왜 필요한가
--   프롬프트 v4(39f5164)부터 few-shot 의 assistant 턴을 plain text 가 아니라
--   {anchor, appraisal, empathy, reframe, reply} JSON 으로 보여준다.
--   그런데 examples 테이블에는 input/output 밖에 없어서, DB 예시가 하나라도 검색되면
--   _example_to_assistant_json() 이 ex["anchor"] 에서 KeyError 로 터졌다(500).
--   DEFAULT_EXAMPLES 안전망은 검색 결과가 0건일 때만 켜지므로, 사실상 모든 요청이 실패했다.
--
-- 이 파일만 실행해도 서비스는 바로 복구된다
--   아래 match_examples 는 v4 필드가 채워진 행만 돌려준다. 백필 전에는 0건이 나오고,
--   서버는 예전처럼 DEFAULT_EXAMPLES 로 떨어져서 정상 동작한다.
--   백필(scripts/backfill_examples_v4.py)이 끝나는 만큼 자동으로 DB 예시가 쓰이기 시작한다.
-- ============================================================================

-- ── 1) 컬럼 추가 ────────────────────────────────────────────────
-- output 은 지우지 않는다. 백필의 원본이고, 예전 형식으로 되돌릴 때도 필요하다.
alter table public.examples
    add column if not exists anchor    text,
    add column if not exists appraisal text,
    add column if not exists empathy   text,
    add column if not exists reframe   text,
    add column if not exists reply     text;

comment on column public.examples.anchor is
    '답변의 근거가 된 일기 원문 문장. v4 few-shot 렌더에 필수';
comment on column public.examples.reframe is
    '재해석 문장. 재해석하면 안 되는 경우 문자열 ''none''';
comment on column public.examples.reply is
    'empathy + reframe 을 이어붙인 최종 한마디. output 을 분해한 결과';

-- ── 2) 검색 RPC 교체 ────────────────────────────────────────────
-- returns table 이 바뀌므로 create or replace 로는 안 되고 먼저 지워야 한다.
drop function if exists public.match_examples(vector(1536), int);

create or replace function public.match_examples(
    query_embedding vector(1536),
    match_count     int
)
returns table (
    input      text,
    output     text,
    anchor     text,
    appraisal  text,
    empathy    text,
    reframe    text,
    reply      text,
    similarity float
)
language sql
stable
as $$
    select
        e.input,
        e.output,
        e.anchor,
        e.appraisal,
        e.empathy,
        e.reframe,
        e.reply,
        1 - (e.embedding <=> query_embedding) as similarity
    from public.examples e
    -- 아직 백필되지 않은 행은 v4 로 렌더할 수 없다. 반쪽짜리를 내보내면 서버가 터진다.
    where e.anchor is not null
      and e.reply is not null
    order by e.embedding <=> query_embedding
    limit match_count;
$$;

-- ── 3) 진행 상황 확인용 ─────────────────────────────────────────
-- 백필이 얼마나 됐는지 볼 때 쓴다.
--   select count(*) filter (where anchor is not null) as done,
--          count(*) as total
--   from public.examples;
