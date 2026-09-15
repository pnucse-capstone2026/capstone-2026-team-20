"""
예시 풀 → Supabase pgvector 시딩 스크립트 (1회 실행)
====================================================
CSV/JSONL 예시 풀을 읽어 OpenAI로 임베딩한 뒤 Supabase `examples` 테이블에 넣는다.
서버는 더 이상 시작할 때 재임베딩하지 않고, 이 테이블을 RPC로 검색만 한다.

사용법:
  # 프로젝트 루트에서
  python scripts/seed_supabase.py            # 전체 재적재(기존 행 삭제 후 삽입)
  python scripts/seed_supabase.py --dry-run  # DB에 쓰지 않고 개수만 확인

필요 환경변수 (.env):
  OPENAI_API_KEY
  SUPABASE_URL
  SUPABASE_KEY   (service_role 키 권장 — 서버 사이드에서만 사용)
"""
import argparse
import csv
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from supabase import create_client

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

REAL_ANCHOR = ROOT / "out" / "coaching_fewshot_real.csv"
SEED = ROOT / "seed" / "synthetic_seed.jsonl"
SYNTHETIC = ROOT / "out" / "synthetic_dataset.jsonl"

EMBED_MODEL = "text-embedding-3-small"
BATCH = 100  # 임베딩·삽입 배치 크기


def load_pool() -> list[dict]:
    """main.py 와 동일한 소스에서 {input, output} 예시를 모은다."""
    pool: list[dict] = []
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
    if SYNTHETIC.exists():
        for line in SYNTHETIC.read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                pool.append({"input": d["diary"], "output": d["whale"]})
    return pool


def embed_batch(client: OpenAI, texts: list[str]) -> list[list[float]]:
    r = client.embeddings.create(model=EMBED_MODEL, input=texts)
    return [d.embedding for d in r.data]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="DB에 쓰지 않고 개수만 확인")
    args = ap.parse_args()

    pool = load_pool()
    print(f"예시 풀 {len(pool)}개 로드됨.")
    if not pool:
        sys.exit("예시 풀이 비어 있다. out/ · seed/ 경로를 확인하라.")

    if args.dry_run:
        print("[dry-run] 임베딩·삽입은 건너뛴다.")
        return

    for var in ("OPENAI_API_KEY", "SUPABASE_URL", "SUPABASE_KEY"):
        if not os.getenv(var):
            sys.exit(f"{var} 환경변수가 없다.")

    openai_client = OpenAI()
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

    # 전체 재적재: 기존 행 삭제 (id > 0 조건으로 전체 매치)
    sb.table("examples").delete().gt("id", 0).execute()
    print("기존 examples 행 삭제 완료.")

    inserted = 0
    for i in range(0, len(pool), BATCH):
        chunk = pool[i : i + BATCH]
        vecs = embed_batch(openai_client, [p["input"] for p in chunk])
        rows = [
            {"input": p["input"], "output": p["output"], "embedding": v}
            for p, v in zip(chunk, vecs)
        ]
        sb.table("examples").insert(rows).execute()
        inserted += len(rows)
        print(f"  {inserted}/{len(pool)} 삽입 완료")

    print(f"시딩 완료: examples {inserted}개.")


if __name__ == "__main__":
    main()
