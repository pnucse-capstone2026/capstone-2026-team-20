"""코칭 고래 프롬프트 + 임베딩/재시도 헬퍼."""
from __future__ import annotations
import hashlib, json, time
import numpy as np
from eval import config

SYSTEM_PROMPT = """[최우선 금지] 어떤 문장도 반드시 지킬 것:
- "~구나", "~겠구나", "~겠네", "~겠어", "~겠다", "~겠지만", "~겠지"로 끝나는 문장 절대 금지.

너는 사용자의 일기를 읽고, 스스로를 칭찬하도록 돕는 고래다. 글을 대신 써주지 않는다.
말투는 사용자를 잘 아는 다정한 친구에 가깝다. 훈계하거나 관찰하듯 말하지 않는다.

[작성 규칙]
1. 일기에 적힌 구체적 단어·상황을 직접 꺼내 감정을 짧게 인정한다. ("힘들었겠구나" 같은 형식적 공감 금지)
2. 원문에 실제로 있는 행동 하나를 콕 짚어 칭찬한다. 원문의 구체적 표현을 그대로 쓸 것.
3. 원문에 없는 사실·성취는 절대 지어내지 않는다.
4. 마지막 문장에서만 사용자가 직접 자기칭찬 글을 다시 써보도록 권한다. 질문은 딱 하나.
5. 엄수: 2~3문장. 다정한 반말 구어체. "~나봐", "~하지 않았어?", "~필요하다구", "~이어졌잖아"처럼 자연스러운 말끝을 쓴다.
6. 금지: '정말 대단해', '멋져' 같은 빈 찬사를 원문 내용과 분리해서 쓰지 않는다.
7. [참고 예시]는 말투·온도만 배운다. 첫 문장 구조·단어를 그대로 따라 쓰지 않는다.

순수 텍스트만 반환한다. JSON·따옴표·머리말 없이."""


def build_user_message(diary: str, examples: list[dict] | None) -> str:
    parts = []
    if examples:
        lines = ["[참고 예시 — 말투·접근만, 내용 베끼기 금지]"]
        for ex in examples:
            lines.append(f"일기: {ex['input']}")
            lines.append(f"고래: {ex['output']}")
        parts.append("\n".join(lines))
    parts.append("[오늘의 일기]\n" + diary)
    parts.append("위 일기를 읽고, 칭찬 포인트를 짚어주고 직접 다시 써보도록 이끄는 고래의 한마디를 건네줘.")
    return "\n\n".join(parts)


def _retry(fn, tries=5):
    for i in range(tries):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                raise
            print(f"  ! 재시도 {2**i}s: {e}")
            time.sleep(2**i)


def _key(t): return hashlib.sha1(f"{config.EMBED_MODEL}::{t}".encode()).hexdigest()


def embed_texts(client, texts):
    config.EMBED_CACHE.parent.mkdir(parents=True, exist_ok=True)
    cache = json.loads(config.EMBED_CACHE.read_text(encoding="utf-8")) if config.EMBED_CACHE.exists() else {}
    miss = [t for t in set(texts) if _key(t) not in cache]
    for i in range(0, len(miss), 100):
        batch = miss[i:i+100]
        r = _retry(lambda: client.embeddings.create(model=config.EMBED_MODEL, input=batch))
        for t, item in zip(batch, r.data):
            cache[_key(t)] = item.embedding
    config.EMBED_CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return {t: cache[_key(t)] for t in texts}


def cosine_top_k(query_vec, pool_vecs, k):
    q = np.array(query_vec, dtype=np.float32); q /= np.linalg.norm(q) + 1e-9
    m = np.array(pool_vecs, dtype=np.float32); m /= np.linalg.norm(m, axis=1, keepdims=True) + 1e-9
    return list(np.argsort(-(m @ q))[:k])
