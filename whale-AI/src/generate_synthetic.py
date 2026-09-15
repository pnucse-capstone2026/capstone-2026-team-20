"""Synthetic 코칭 데이터 생성기.

부스 데이터가 '자책 일기 → 코칭 한마디' 형태가 아니어서, 그 형태를 합성으로 채운다.
- 손으로 쓴 seed(synthetic_seed.jsonl)를 few-shot으로 사용해 모양·보이스를 고정
- 부스 tone_reference에서 실제 말투 조각을 주입해 'AI 티' 감소
- 생성물은 gpt-4o 심사로 거른 뒤(환각·톤·형식), 임베딩 중복 제거

실행: OPENAI_API_KEY 설정 후  `python -m src.generate_synthetic`
"""
import csv, hashlib, json, random, time
import numpy as np
from src import config


def get_client():
    from openai import OpenAI
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


def load_seed():
    rows = []
    with open(config.SEED_JSONL, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_tone_phrases():
    try:
        with open(config.TONE_CSV, encoding="utf-8") as f:
            return [r["text"] for r in csv.DictReader(f) if r.get("text")]
    except FileNotFoundError:
        return []


SYSTEM = """너는 '칭찬고래' 서비스의 학습용 데이터를 만드는 생성기다.
한 건은 (diary, whale) 한 쌍이다.

- diary: 사용자가 실제로 쓸 법한 일기. 자책·피로·불안·실패 같은 부정 감정이나 사소한 고민이 담긴 1~3문장. 너무 극적이지 않게, 평범한 하루의 톤.
- whale: 그 일기를 읽은 고래가 건네는 한마디. 글을 대신 써주지 않는다.
    1) diary의 구체적인 단어·행동·상황을 직접 가져와 감정을 짧게 인정한다. ('힘들었겠구나' 같은 형식적 공감 금지)
    2) 원문에 실제로 있는 행동 하나를 콕 짚어 칭찬한다. 원문의 표현을 그대로 사용할 것.
    3) 마지막 문장에서만 사용자가 직접 다시 써보도록 권한다. 질문은 딱 하나.
    엄수: 2~3문장. 다정한 반말. 한국 또래 구어체. 과장·훈계·오글거림 금지.
    엄수: 원문에 없는 사실·성취는 한 글자도 지어내지 않는다.
    금지: '정말 대단해', '멋져' 같은 빈 찬사를 원문 내용 없이 단독으로 쓰지 않는다.

반드시 JSON 한 줄로만 응답: {"diary": "...", "whale": "..."}"""


def build_gen_messages(seed, tone_phrases, topic, style_hint):
    shots = random.sample(seed, min(config.N_FEWSHOT, len(seed)))
    shot_text = "\n".join(
        json.dumps({"diary": s["diary"], "whale": s["whale"]}, ensure_ascii=False)
        for s in shots
    )
    flavor = ""
    if tone_phrases:
        picks = random.sample(tone_phrases, min(6, len(tone_phrases)))
        flavor = "\n참고할 실제 말투 조각(그대로 베끼지 말고 분위기만): " + " / ".join(picks)
    user = (
        f"아래는 형식 예시다:\n{shot_text}\n\n"
        f"이제 새로운 한 건을 만들어라.\n"
        f"- 상황 소재: {topic}\n"
        f"- whale 말투/방향: {style_hint}{flavor}\n\n"
        f"예시와 겹치지 않는 새로운 내용으로, JSON 한 줄만."
    )
    return [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": user}]


def parse_json(text):
    t = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(t)


JUDGE_SYSTEM = """너는 '칭찬고래' 학습 데이터의 품질 검수자다.
주어진 (diary, whale)를 보고 아래를 0/1로 판정해 JSON으로만 답한다.

- realistic: diary가 실제 사용자가 쓸 법한 자연스러운 일기인가
- grounded: whale이 diary에 없는 사실·성취를 한 건도 지어내지 않았는가. 조금이라도 있으면 0.
- specific: whale이 diary의 구체적인 단어·행동을 직접 언급해 칭찬하는가. generic 찬사('정말 대단해' 단독)만 있으면 0.
- coaching: whale이 글을 대신 완성하지 않고 질문 하나로만 재작성을 권하는가. 질문이 2개 이상이면 0.
- tone: 2~3문장 이내, 다정한 반말 구어체, 과장·훈계·오글거림 없는가

{"realistic": int, "grounded": int, "specific": int, "coaching": int, "tone": int}"""


def judge(client, diary, whale):
    msgs = [
        {"role": "system", "content": JUDGE_SYSTEM},
        {"role": "user", "content": f'diary: {diary}\nwhale: {whale}'},
    ]
    resp = _retry(lambda: client.chat.completions.create(
        model=config.JUDGE_MODEL, temperature=0, messages=msgs))
    try:
        d = parse_json(resp.choices[0].message.content)
        return all(int(d.get(k, 0)) == 1 for k in ("realistic", "grounded", "specific", "coaching", "tone"))
    except Exception:  # noqa: BLE001
        return False


# ---- 임베딩(중복 제거용) ----
def _key(t): return hashlib.sha1(f"{config.EMBED_MODEL}::{t}".encode()).hexdigest()

def embed(client, texts):
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


def is_dup(vec, accepted_vecs):
    if not accepted_vecs:
        return False
    q = np.array(vec); q /= np.linalg.norm(q) + 1e-9
    m = np.array(accepted_vecs); m /= np.linalg.norm(m, axis=1, keepdims=True) + 1e-9
    return float((m @ q).max()) >= config.DEDUP_THRESHOLD


def run(client=None):
    client = client or get_client()
    rng = random.Random(config.SEED)
    random.seed(config.SEED)
    seed = load_seed()
    tone = load_tone_phrases()
    print(f"seed {len(seed)}개 / tone {len(tone)}개 로드")

    accepted, accepted_vecs = [], []
    attempts = 0
    max_attempts = config.N_TARGET * 4
    while len(accepted) < config.N_TARGET and attempts < max_attempts:
        attempts += 1
        topic = rng.choice(config.TOPICS)
        style_hint = rng.choice(rng.choice(config.STYLE_AXES))
        msgs = build_gen_messages(seed, tone, topic, style_hint)
        resp = _retry(lambda: client.chat.completions.create(
            model=config.GEN_MODEL, temperature=config.GEN_TEMPERATURE, messages=msgs))
        try:
            obj = parse_json(resp.choices[0].message.content)
            diary, whale = obj["diary"].strip(), obj["whale"].strip()
        except Exception:
            continue
        if not diary or not whale:
            continue
        if not judge(client, diary, whale):
            continue
        vec = embed(client, [diary])[diary]
        if is_dup(vec, accepted_vecs):
            continue
        accepted.append({"diary": diary, "whale": whale, "topic": topic, "style": style_hint})
        accepted_vecs.append(vec)
        print(f"  [{len(accepted)}/{config.N_TARGET}] ({topic}) {diary[:30]}…")

    _write(accepted)
    print(f"\n완료: {len(accepted)}개 통과 / {attempts}회 시도 (통과율 {len(accepted)/max(attempts,1):.0%})")
    print(f"저장: {config.OUT_JSONL}\n      {config.OUT_CSV}")
    return accepted


def _write(rows):
    config.OUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with open(config.OUT_JSONL, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(config.OUT_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f); w.writerow(["diary", "whale", "topic", "style"])
        w.writerows([[r["diary"], r["whale"], r["topic"], r["style"]] for r in rows])


if __name__ == "__main__":
    run()
