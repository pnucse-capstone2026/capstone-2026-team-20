"""Synthetic 코칭 데이터 생성 설정."""
from pathlib import Path
ROOT = Path(__file__).parent.parent

SEED_JSONL = ROOT / "seed" / "synthetic_seed.jsonl"     # 손으로 쓴 gold few-shot
TONE_CSV = ROOT / "out" / "tone_reference.csv"          # 부스 보이스 코퍼스(말투 주입용)
OUT_JSONL = ROOT / "out" / "synthetic_dataset.jsonl"
OUT_CSV = ROOT / "out" / "synthetic_dataset.csv"
EMBED_CACHE = ROOT / ".cache" / "syn_embeddings.json"

GEN_MODEL = "gpt-4o-mini"
JUDGE_MODEL = "gpt-4o"
EMBED_MODEL = "text-embedding-3-small"

N_TARGET = 100          # 만들고 싶은 '통과된' 샘플 수
N_FEWSHOT = 4           # 매 생성마다 시드에서 뽑아 보여줄 예시 수
DEDUP_THRESHOLD = 0.90  # diary 임베딩 코사인 이 이상이면 중복으로 버림
GEN_TEMPERATURE = 1.0   # 다양성 위해 높게
SEED = 42

# 자책/고민이 담길 만한 상황 풀 (다양성 확보용)
TOPICS = [
    "야근·과로", "공부 집중 안 됨", "운동 빼먹음", "다이어트·식습관",
    "약속 취소·관계 위축", "실수·실패", "무기력·우울감", "할 일 미루기",
    "거절·죄책감", "늦잠·시간 관리", "발표·긴장", "비교·자존감",
    "돈·절약 스트레스", "건강·컨디션 난조", "집안일·자취 생활", "진로·미래 불안",
]

# 취향 축 커버리지 — 생성 시 무작위로 한두 축을 강조해 다양한 user type을 흉내
STYLE_AXES = [
    ("정서적 공감 우선(조언 최소)", "가벼운 해결 방향 제시"),
    ("결과보다 과정·버틴 점 강조", "실제 해낸 성취를 구체적으로 언급"),
    ("지금의 자신을 받아들이는 자기수용 마무리", "내일의 작은 시도를 권하는 성장 마무리"),
    ("다정하고 따뜻한 말투", "담백하고 간결한 말투"),
]
