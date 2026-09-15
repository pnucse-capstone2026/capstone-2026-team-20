"""
칭찬고래 AI 파트 — 대화형 테스트 (DB 없이 로컬에서)
======================================================
실서비스 흐름을 그대로 돌리되, Supabase가 할 일만 로컬로 대체한다.
  - 과거 기록: .local_memory.json 에 쌓고 그 안에서 임베딩 유사도 검색
  - 부스 예시: out/coaching_fewshot_real.csv 에서 검색
  - OpenAI(임베딩 + gpt-4o-mini) 호출만 진짜
→ 프롬프트 조립·모델 호출은 실서비스와 동일(service_prompt.py 사용).

실행:  export OPENAI_API_KEY=sk-...  &&  python play.py
"""
import csv, json, os, random, time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import service_prompt as sp

ROOT = Path(__file__).parent
MEMORY_FILE = ROOT / ".local_memory.json"
REAL_ANCHOR = ROOT / "out" / "coaching_fewshot_real.csv"
TONE_REFERENCE = ROOT / "out" / "tone_reference.csv"
SEED = ROOT / "seed" / "synthetic_seed.jsonl"
EMBED_MODEL = "text-embedding-3-small"
GEN_MODEL = "gpt-4o-mini"
MAX_HANMADI = 3
TOP_SIMILAR_MEMORY = 3
TOP_RECENT_MEMORY = 3
TOP_EXAMPLES = 2
TOP_TONE_PHRASES = 6


# ── OpenAI ─────────────────────────────────────────────
def get_client():
    from openai import OpenAI

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError(
            "OPENAI_API_KEY is not set. In the same PowerShell session, run: "
            '$env:OPENAI_API_KEY = "sk-..."'
        )
    return OpenAI()


def _retry(fn, tries=5):
    for i in range(tries):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                raise
            print(f"  ! 재시도 {2**i}s: {e}")
            time.sleep(2**i)


def embed(client, text):
    r = _retry(lambda: client.embeddings.create(model=EMBED_MODEL, input=[text]))
    return r.data[0].embedding


def cosine_top_k(qvec, items, k):
    """items: [{'embedding':[...], ...}] → 유사도 상위 k개 항목."""
    if not items:
        return []
    q = np.array(qvec, dtype=np.float32); q /= np.linalg.norm(q) + 1e-9
    m = np.array([it["embedding"] for it in items], dtype=np.float32)
    m /= np.linalg.norm(m, axis=1, keepdims=True) + 1e-9
    idx = np.argsort(-(m @ q))[:k]
    return [items[i] for i in idx]


def pick_memory_context(qvec, memory_items):
    """최근 흐름 + 의미상 유사한 기억을 함께 넣는다."""
    recent = list(reversed(memory_items[-TOP_RECENT_MEMORY:]))
    similar = cosine_top_k(qvec, memory_items, TOP_SIMILAR_MEMORY)

    picked = []
    seen = set()
    for item in recent + similar:
        text = item.get("text", "")
        if text and text not in seen:
            picked.append(text)
            seen.add(text)
    return picked


# ── 로컬 데이터 ─────────────────────────────────────────
def load_memory():
    if MEMORY_FILE.exists():
        return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
    return []


def save_memory(mem):
    MEMORY_FILE.write_text(json.dumps(mem, ensure_ascii=False), encoding="utf-8")


def load_examples(client):
    """부스 실제 칭찬 + 손글씨 seed를 {input, output, embedding}로."""
    pool = [{"input": e["input"], "output": e["output"]} for e in sp.DEFAULT_EXAMPLES]
    if REAL_ANCHOR.exists():
        with open(REAL_ANCHOR, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r.get("input") and r.get("reply"):
                    pool.append({"input": r["input"].strip(), "output": r["reply"].strip()})
    if SEED.exists():
        for line in SEED.read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                pool.append({"input": d["diary"], "output": d["whale"]})
    print(f"예시 풀 {len(pool)}개 임베딩 중...")
    for p in pool:
        p["embedding"] = embed(client, p["input"])
    return pool


def load_tone_phrases():
    """부스 원문에서 뽑은 실제 말투 조각."""
    if not TONE_REFERENCE.exists():
        return []
    with open(TONE_REFERENCE, encoding="utf-8") as f:
        return [r["text"].strip() for r in csv.DictReader(f) if r.get("text") and r["text"].strip()]


# ── 한마디 생성 ─────────────────────────────────────────────
def make_hanmadi(client, diary, memory_items, example_pool, tone_pool, retry_count, qvec):
    past = pick_memory_context(qvec, memory_items)
    examples = [{"input": e["input"], "output": e["output"]}
                for e in cosine_top_k(qvec, example_pool, TOP_EXAMPLES)]

    def call_llm(msgs):
        temp = 0.7 if retry_count == 0 else 0.9
        resp = _retry(lambda: client.chat.completions.create(
            model=GEN_MODEL, temperature=temp, messages=msgs))
        return resp.choices[0].message.content

    whale, issues = sp.generate_with_guard(
        call_llm, diary, past, examples, retry_count=retry_count
    )
    if issues:
        print(f"  ↻ 교정 후 반환 (이슈: {issues[0][:40]})")

    return whale, past, examples


# ── 메인 루프 ──────────────────────────────────────────
def main():
    client = get_client()
    examples = load_examples(client)
    tone_phrases = load_tone_phrases()
    print(f"말투 조각 {len(tone_phrases)}개 로드됨. (tone_reference.csv)")
    memory = load_memory()
    print(f"\n로컬 과거 기록 {len(memory)}개 로드됨. (.local_memory.json)")
    print("\n=== 오늘 일기를 입력하세요. (q=종료) ===")

    while True:
        diary = input("\n📓 일기> ").strip()
        if diary.lower() in ("q", "quit", "exit"):
            print("종료."); break
        if not diary:
            continue

        qvec = embed(client, diary)
        count = 0
        msg, past, used_ex = make_hanmadi(client, diary, memory, examples, tone_phrases, count, qvec)
        count += 1
        if past:
            preview = " / ".join(t[:20] + "…" for t in past[:3])
            print(f"   (참고한 과거 기록 {len(past)}개: {preview})")
        print(f"\n🐳 고래의 한마디 ({count}/{MAX_HANMADI})\n   {msg}")

        while True:
            cmd = input(f"\n[r]다른 한마디({count}/{MAX_HANMADI}) / [엔터]저장하고 다음 / [q]종료 > ").strip().lower()
            if cmd == "r":
                if count >= MAX_HANMADI:
                    print("   더 못 만들어 (최대 3번). 엔터로 저장하고 다음.")
                    continue
                msg, _, _ = make_hanmadi(client, diary, memory, examples, tone_phrases, count, qvec)
                count += 1
                print(f"\n🐳 고래의 한마디 ({count}/{MAX_HANMADI})\n   {msg}")
            elif cmd == "q":
                print("종료."); save_memory(memory); return
            else:
                # ★ 원문 + 임베딩을 과거 기록에 저장 (수정본 아님 — 원문이 미래의 기억)
                memory.append({"text": diary, "embedding": qvec,
                               "created_at": datetime.now(timezone.utc).isoformat()})
                save_memory(memory)
                print(f"   저장됨 → 과거 기록 {len(memory)}개")
                break


if __name__ == "__main__":
    main()
