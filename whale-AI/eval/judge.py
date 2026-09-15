"""코칭 한마디 채점 — gpt-4o가 4축을 1~5로 평가."""
import json
from eval import config
from eval.prompts import _retry

AXES = ["emotion_ack", "grounded", "coaching", "naturalness"]

JUDGE_SYSTEM = """너는 '칭찬고래'가 생성한 코칭 한마디의 품질을 평가하는 엄격한 심사자다.
사용자의 일기(diary)와 고래의 한마디(whale)를 비교해 아래 4축을 각각 1~5점으로 채점한다.

1. emotion_ack (감정 인정)
   5=diary의 구체적 단어·상황을 직접 언급하며 감정 공감. 4=공감은 있으나 다소 일반적. 3=형식적("힘들었겠구나"만). 2=감정 인정이 피상적. 1=무시하거나 건너뜀.

2. grounded (원문 근거)
   5=100% diary 기반, 원문 표현을 직접 인용. 4=원문 기반이나 약간 모호. 3=원문 외 추론 1건 포함. 2=원문에 없는 사실 여럿. 1=명백한 허위 추가.
   ★ 원문에 없는 내용이 1건이라도 있으면 반드시 3점 이하.

3. coaching (코칭형)
   5=diary의 구체적 행동·단어를 직접 짚어 칭찬하고, 재작성을 자연스럽게 유도. 4=칭찬 포인트 있으나 약간 generic. 3=포인트가 모호하거나 재작성 유도가 억지스러움. 2=글을 대신 완성하거나 훈계. 1=코칭 기능 없음.

4. naturalness (자연스러움)
   5=신선하고 자연스러운 구어체, 군더더기 없음. 4=대체로 자연스러우나 약간 공식적. 3='정말 대단해/멋져' 남발 또는 질문 2개 이상. 2=어색하거나 오글거리는 표현 다수. 1=훈계·AI 말투 심함.

주의: 5점은 진짜 흠잡을 데 없는 경우만. 무난하면 3~4점이 정상.
반드시 JSON으로만: {"emotion_ack": int, "grounded": int, "coaching": int, "naturalness": int, "comment": "한 줄 근거"}"""


def _parse(text):
    t = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(t)


def score(client, diary, whale):
    resp = _retry(lambda: client.chat.completions.create(
        model=config.JUDGE_MODEL, temperature=0,
        messages=[{"role": "system", "content": JUDGE_SYSTEM},
                  {"role": "user", "content": f"diary: {diary}\nwhale: {whale}"}]))
    try:
        d = _parse(resp.choices[0].message.content)
    except Exception:  # noqa: BLE001
        return {a: 0 for a in AXES} | {"comment": "PARSE_FAIL"}
    for a in AXES:
        d[a] = int(d.get(a, 0))
    d.setdefault("comment", "")
    return d
