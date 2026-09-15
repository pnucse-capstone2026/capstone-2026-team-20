"""코칭 한마디 평가 메인.

흐름:
  1) synthetic_dataset(diary,whale) 로드 → N_EVAL개를 테스트셋으로 분리
  2) few-shot 풀 = 남은 synthetic + seed(12) + 실제앵커(18, input/reply)
  3) 테스트 일기마다 × 조건(off/on)으로 고래 한마디 생성
  4) gpt-4o로 4축 채점 → 조건별 평균 비교
실행: OPENAI_API_KEY 설정 후 `python -m eval.run_eval`
"""
import csv, json, random, statistics as stats
from eval import config
from eval.judge import AXES, score
from eval.prompts import SYSTEM_PROMPT, build_user_message, cosine_top_k, embed_texts, _retry


def get_client():
    from openai import OpenAI
    return OpenAI()


def load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_synthetic():
    if not config.SYNTHETIC.exists():
        raise SystemExit(
            f"테스트셋 없음: {config.SYNTHETIC}\n"
            f"→ 생성기로 만든 synthetic_dataset.jsonl을 out/ 에 두세요 "
            f"(`python -m src.generate_synthetic`)."
        )
    rows = [r for r in load_jsonl(config.SYNTHETIC) if r.get("diary") and r.get("whale")]
    if len(rows) < 4:
        raise SystemExit(f"유효한 synthetic 행이 너무 적습니다({len(rows)}).")
    return rows


def build_pool(pool_syn):
    """few-shot 후보를 {input, output}로 통일."""
    pool = [{"input": r["diary"], "output": r["whale"]} for r in pool_syn]
    # seed
    try:
        for r in load_jsonl(config.SEED):
            pool.append({"input": r["diary"], "output": r["whale"]})
    except FileNotFoundError:
        pass
    # 실제 앵커 (input, reply)
    if config.REAL_ANCHOR.exists():
        with open(config.REAL_ANCHOR, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r.get("input") and r.get("reply"):
                    pool.append({"input": r["input"].strip(), "output": r["reply"].strip()})
    return pool


def generate(client, diary, examples):
    resp = _retry(lambda: client.chat.completions.create(
        model=config.GEN_MODEL, temperature=config.TEMPERATURE,
        messages=[{"role": "system", "content": SYSTEM_PROMPT},
                  {"role": "user", "content": build_user_message(diary, examples)}]))
    return resp.choices[0].message.content.strip()


def run(client=None):
    client = client or get_client()
    rng = random.Random(config.SEED_RNG)
    syn = load_synthetic()
    rng.shuffle(syn)
    n_eval = min(config.N_EVAL, max(1, len(syn) // 3))
    test, pool_syn = syn[:n_eval], syn[n_eval:]
    pool = build_pool(pool_syn)
    print(f"테스트셋 {len(test)} / few-shot 풀 {len(pool)} (synthetic {len(pool_syn)} + seed + 실제앵커)")

    # 임베딩: 테스트 일기 + 풀 input
    test_diaries = [t["diary"] for t in test]
    pool_inputs = [p["input"] for p in pool]
    print("임베딩 생성 중...")
    emb = embed_texts(client, test_diaries + pool_inputs)
    pool_vecs = [emb[i] for i in pool_inputs]

    results = []
    total = len(test) * len(config.CONDITIONS); done = 0
    for t in test:
        diary = t["diary"]
        for cond in config.CONDITIONS:
            done += 1
            print(f"[{done}/{total}] {cond['name']}")
            examples = None
            if cond["few_shot"] and pool:
                idx = cosine_top_k(emb[diary], pool_vecs, cond["k"])
                examples = [pool[i] for i in idx]
            out = generate(client, diary, examples)
            sc = score(client, diary, out)
            results.append({
                "condition": cond["name"], "diary": diary, "whale_output": out,
                "reference": t["whale"],
                **{a: sc[a] for a in AXES},
                "avg": round(sum(sc[a] for a in AXES) / len(AXES), 3),
                "judge_comment": sc.get("comment", ""),
            })

    _write(results)
    summary = _summarize(results)
    _print(summary)
    config.SUMMARY_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {config.RESULTS_CSV}\n      {config.SUMMARY_JSON}")
    return summary


def _write(results):
    config.RESULTS_CSV.parent.mkdir(parents=True, exist_ok=True)
    fields = ["condition", "diary", "whale_output", "reference", *AXES, "avg", "judge_comment"]
    with open(config.RESULTS_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(results)


def _summarize(results):
    out = {}
    for cond in config.CONDITIONS:
        sub = [r for r in results if r["condition"] == cond["name"]]
        if sub:
            out[cond["name"]] = {"n": len(sub),
                                 **{a: round(stats.mean(r[a] for r in sub), 3) for a in AXES},
                                 "overall_avg": round(stats.mean(r["avg"] for r in sub), 3)}
    return out


def _print(summary):
    print("\n" + "=" * 64)
    print(f"{'condition':<16}" + "".join(f"{a[:11]:>12}" for a in AXES) + f"{'OVERALL':>12}")
    print("=" * 64)
    for name, s in summary.items():
        print(f"{name:<16}" + "".join(f"{s[a]:>12}" for a in AXES) + f"{s['overall_avg']:>12}")
    print("=" * 64)


if __name__ == "__main__":
    run()
