"""
user_memories 컬럼 암호화 백필 (1회성, 중단·재시작 가능)
========================================================
main.py 가 content/edited_text/whale_message(+rejected_messages[].whale_message)를
AES-256-GCM 으로 암호화해서 저장하도록 바뀌었다(crypto_utils.py). 이 스크립트는
그 변경 이전에 평문으로 쌓인 기존 행을 같은 방식으로 제자리에서 재암호화한다.

이미 암호문인 값은 crypto_utils.looks_encrypted() 로 걸러 건너뛰므로 몇 번을
다시 돌려도 안전하다(idempotent). 별도 진행 표시 컬럼이 필요 없는 이유이기도 하다.

선행 조건
  1) 이 스크립트를 돌릴 때 쓸 MEMORY_ENC_KEY 가, 배포판(ECS)에 넣을 키와
     "동일한 값"이어야 한다 — 다른 키로 암호화하면 배포판이 그 값을 못 읽는다.
     로컬 .env 의 MEMORY_ENC_KEY 를 그대로 쓸지, 운영용으로 새로 만든 키를
     환경변수로 덮어써서 쓸지는 상황에 맞게 고를 것 (README 참고).
  2) SUPABASE_URL/SUPABASE_KEY 가 대상 프로젝트(운영이면 운영 프로젝트)를
     가리키는지 반드시 확인할 것 — service_role 키라 RLS 없이 전체 테이블에
     접근한다.

사용법
  python scripts/backfill_user_memories_encrypt.py --dry-run     # 3건만 보여주고 DB는 안 건드림
  python scripts/backfill_user_memories_encrypt.py --limit 20    # 20건만 처리
  python scripts/backfill_user_memories_encrypt.py               # 남은 것 전부

필요 환경변수 (.env 또는 셸 환경)
  SUPABASE_URL
  SUPABASE_KEY   (service_role 키)
  MEMORY_ENC_KEY (배포판과 동일한 값이어야 함 — 위 선행 조건 참고)
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
from supabase import create_client

from crypto_utils import encrypt_rejected_messages, encrypt_text, looks_encrypted

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

FETCH_PAGE = 200


def fetch_all(sb) -> list[dict]:
    """전체 행을 가져온다. 이미 암호화됐는지는 여기서 걸러내지 않고 호출부에서 판단한다.

    (content 는 not null 이라 examples 백필처럼 "빈 컬럼"으로 대상을 좁힐 수가
    없다 — looks_encrypted() 로 값 자체를 보고 판단해야 해서 전체를 훑는다.)
    """
    rows: list[dict] = []
    start = 0
    while True:
        page = (
            sb.table("user_memories")
            .select("id, user_id, content, edited_text, whale_message, rejected_messages")
            .order("id")
            .range(start, start + FETCH_PAGE - 1)
            .execute()
        )
        batch = page.data or []
        rows.extend(batch)
        if len(batch) < FETCH_PAGE:
            break
        start += FETCH_PAGE
    return rows


def needs_backfill(row: dict) -> bool:
    if not looks_encrypted(row.get("content")):
        return True
    if row.get("edited_text") and not looks_encrypted(row["edited_text"]):
        return True
    if row.get("whale_message") and not looks_encrypted(row["whale_message"]):
        return True
    for m in row.get("rejected_messages") or []:
        if m.get("whale_message") and not looks_encrypted(m["whale_message"]):
            return True
    return False


def build_update(row: dict) -> dict:
    """이미 암호문인 필드는 건드리지 않고, 평문인 필드만 골라 암호화한다."""
    user_id = row["user_id"]
    update: dict = {}

    if not looks_encrypted(row.get("content")):
        update["content"] = encrypt_text(row["content"], aad=user_id)

    if row.get("edited_text") and not looks_encrypted(row["edited_text"]):
        update["edited_text"] = encrypt_text(row["edited_text"], aad=user_id)

    if row.get("whale_message") and not looks_encrypted(row["whale_message"]):
        update["whale_message"] = encrypt_text(row["whale_message"], aad=user_id)

    rejected = row.get("rejected_messages") or []
    if any(m.get("whale_message") and not looks_encrypted(m["whale_message"]) for m in rejected):
        # 항목 단위로 이미 암호문인 건 그대로 두고, 평문인 것만 암호화한다.
        update["rejected_messages"] = [
            {**m, "whale_message": (m["whale_message"] if looks_encrypted(m.get("whale_message")) else encrypt_text(m["whale_message"], aad=user_id))}
            for m in rejected
        ]

    return update


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="3건만 확인하고 DB는 건드리지 않는다")
    ap.add_argument("--limit", type=int, default=None, help="처리할 최대 건수")
    args = ap.parse_args()

    for var in ("SUPABASE_URL", "SUPABASE_KEY", "MEMORY_ENC_KEY"):
        if not os.getenv(var):
            sys.exit(f"{var} 환경변수가 없다.")

    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

    print(f"대상 프로젝트: {os.environ['SUPABASE_URL']}")
    all_rows = fetch_all(sb)
    pending = [r for r in all_rows if needs_backfill(r)]
    total_pending = len(pending)

    if not pending:
        print(f"전체 {len(all_rows)}건 중 백필 대상 없음 (이미 다 암호화됐거나 테이블이 비어 있다).")
        return

    limit = 3 if args.dry_run else args.limit
    if limit:
        pending = pending[:limit]

    if args.dry_run and total_pending > len(pending):
        print(f"전체 {len(all_rows)}건 중 백필 대상 {total_pending}건 (dry-run이라 앞 {len(pending)}건만 미리보기).")
    else:
        print(f"전체 {len(all_rows)}건 중 백필 대상 {len(pending)}건.")
    done = 0
    failed: list[int] = []

    for row in pending:
        update = build_update(row)
        if args.dry_run:
            preview = {k: (v if k == "rejected_messages" else str(v)[:30] + "...") for k, v in update.items()}
            print(f"  [dry-run] id={row['id']} user_id={row['user_id']} -> {preview}")
            done += 1
            continue

        try:
            sb.table("user_memories").update(update).eq("id", row["id"]).execute()
            done += 1
            print(f"  {done}/{len(pending)} 완료 (id={row['id']})")
        except Exception as exc:
            failed.append(row["id"])
            print(f"  [fail] id={row['id']}: {exc}")

    print(f"\n백필 {done}건 완료, 실패 {len(failed)}건.")
    if failed:
        print(f"실패한 id: {failed}")
        print("다시 실행하면 이 행들만 남아서 재시도된다(이미 암호화된 행은 건너뜀).")


if __name__ == "__main__":
    main()
