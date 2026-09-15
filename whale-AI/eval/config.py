"""코칭 한마디 평가 설정. 데이터가 채워져 있으면 `python -m eval.run_eval`로 실행."""
from pathlib import Path
ROOT = Path(__file__).parent.parent   # whale-data/

# ── 입력 데이터 (whale-data 폴더 기준) ─────────────────
SYNTHETIC = ROOT / "out" / "synthetic_dataset.jsonl"   # {diary, whale} ← 생성기 산출물(필수)
REAL_ANCHOR = ROOT / "out" / "coaching_fewshot_real.csv"  # input,reply ← 실제 칭찬 18개
SEED = ROOT / "seed" / "synthetic_seed.jsonl"          # {diary, whale} ← 손글씨 12개

# ── 산출물 ─────────────────────────────────────────────
RESULTS_CSV = ROOT / "eval" / "results.csv"
SUMMARY_JSON = ROOT / "eval" / "summary.json"
EMBED_CACHE = ROOT / ".cache" / "eval_embeddings.json"

# ── 모델 ──────────────────────────────────────────────
EMBED_MODEL = "text-embedding-3-small"
GEN_MODEL = "gpt-4o-mini"     # 평가 대상(고래 한마디 생성)
JUDGE_MODEL = "gpt-4o"        # 채점

# ── 파라미터 ──────────────────────────────────────────
N_EVAL = 30          # synthetic에서 떼어낼 테스트셋 크기(데이터 적으면 자동 축소)
K_EXAMPLES = 4       # few-shot ON일 때 주입 예시 수
TEMPERATURE = 0.7
SEED_RNG = 42

# 비교 조건 (핵심: few-shot off vs on)
CONDITIONS = [
    {"name": "fewshot_off", "few_shot": False, "k": 0},
    {"name": "fewshot_on_k2", "few_shot": True, "k": 2},
    {"name": "fewshot_on_k4", "few_shot": True, "k": 4},
]
