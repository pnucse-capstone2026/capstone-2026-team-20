"""
examples 테이블 v4 구조화 백필 (1회성, 중단·재시작 가능)
========================================================
프롬프트 v4 는 few-shot assistant 턴을
{anchor, appraisal, empathy, reframe, reply} JSON 으로 보여준다.
그런데 DB 의 예시 풀에는 input/output(plain text) 밖에 없어서 그대로는 쓸 수 없다.

이 스크립트는 기존 input/output 을 GPT 로 **분해**해서 빈 컬럼을 채운다.

  reply 는 새로 생성하지 않고 기존 output 을 그대로 넣는다.
  output 은 사람이 다듬어 둔 문장이라, 다시 만들면 예시 풀의 톤이 흔들린다.
  모델이 하는 일은 '이 답이 어느 문장(anchor)의 어떤 판단(appraisal)을 겨냥해
  어떻게 뒤집었는지(reframe)' 를 되짚는 것뿐이다.

선행 조건
  Supabase SQL Editor 에서 schema_v4_examples.sql 을 먼저 실행할 것.
  (anchor 등 컬럼이 없으면 이 스크립트는 아무것도 못 한다)

사용법
  python scripts/backfill_examples_v4.py --dry-run     # 3건만 변환해 눈으로 확인
  python scripts/backfill_examples_v4.py --limit 20    # 20건만 처리
  python scripts/backfill_examples_v4.py               # 남은 것 전부

  anchor 가 null 인 행만 처리하므로, 중간에 끊겨도 다시 돌리면 이어서 채운다.

필요 환경변수 (.env)
  OPENAI_API_KEY
  SUPABASE_URL
  SUPABASE_KEY   (service_role 키)
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from supabase import create_client

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

# main.py 의 GEN_MODEL 과 같은 모델. 분해는 생성보다 쉬운 작업이라 더 키울 이유가 없다.
MODEL = "gpt-4o-mini"
FETCH_PAGE = 200

SYSTEM = """너는 이미 작성된 '고래 한마디'를 구조 분해하는 도구다.
새로운 답변을 만들지 말고, 주어진 diary 와 reply 를 읽고 아래 네 값을 뽑아라.

anchor    : reply 가 근거로 삼은 diary 속 문장. diary 원문에 있는 그대로 복사한다.
            요약·의역·문장 합치기 금지. 감정이 드러난 문장을 우선으로 고른다.
appraisal : anchor 에서 화자가 자기·상황에 내리는 '부정적 판단' 한 줄.
            좋은 날이라 뒤집을 판단이 없으면 "긍정 - " 뒤에 원문에서 찾은 실제 칭찬
            포인트를 적는다. 예: "긍정 - 졸릴 텐데 수업을 끝까지 들은 것".
            괄호 안내문을 그대로 옮겨 적지 마라.
            죽음·이별처럼 재해석하지 않은 답이면 "none".
empathy   : reply 에서 감정을 그대로 받아주는 부분. reply 안의 문장을 그대로 쓴다.
reframe   : reply 에서 사건·감정을 다른 의미로 다시 이름 붙인 부분. reply 안의 문장을 그대로 쓴다.
            재해석이 없는 답이면 "none".

JSON 하나로만 답한다: {"anchor": "...", "appraisal": "...", "empathy": "...", "reframe": "..."}"""


def _norm(text: str) -> str:
    """공백·따옴표 차이를 무시하고 비교하기 위한 정규화."""
    return re.sub(r"[\s\"'’”]+", "", text)


def decompose(client: OpenAI, diary: str, reply: str) -> dict | None:
    """한 건을 분해한다. anchor 가 원문에 없으면 한 번 더 시도하고, 그래도 아니면 포기."""
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"[diary]\n{diary}\n\n[reply]\n{reply}"},
    ]

    for attempt in range(2):
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0,
        )

        try:
            parsed = json.loads(response.choices[0].message.content or "{}")
        except json.JSONDecodeError:
            continue

        anchor = (parsed.get("anchor") or "").strip()

        # anchor 는 diary 원문에 실제로 있어야 한다. 이게 깨지면 v4 few-shot 이
        # "원문에서 복사해라" 를 스스로 어기는 예시를 학습시키는 꼴이 된다.
        if anchor and _norm(anchor) in _norm(diary):
            return {
                "anchor": anchor,
                "appraisal": (parsed.get("appraisal") or "").strip(),
                "empathy": (parsed.get("empathy") or "").strip(),
                "reframe": (parsed.get("reframe") or "none").strip() or "none",
            }

        if attempt == 0:
            messages.append({"role": "assistant", "content": response.choices[0].message.content or ""})
            messages.append(
                {
                    "role": "user",
                    "content": "anchor 가 diary 원문에 없다. diary 에서 문장 하나를 글자 그대로 복사해서 다시 답해라.",
                }
            )

    return None


def fetch_pending(sb, limit: int | None) -> list[dict]:
    """anchor 가 비어 있는 행만 가져온다. 이미 채운 건 건드리지 않는다."""
    rows: list[dict] = []
    start = 0

    while True:
        page = (
            sb.table("examples")
            .select("id, input, output")
            .is_("anchor", "null")
            .order("id")
            .range(start, start + FETCH_PAGE - 1)
            .execute()
        )
        batch = page.data or []
        rows.extend(batch)

        if len(batch) < FETCH_PAGE or (limit and len(rows) >= limit):
            break
        start += FETCH_PAGE

    return rows[:limit] if limit else rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="3건만 변환해 출력하고 DB 는 건드리지 않는다")
    ap.add_argument("--limit", type=int, default=None, help="처리할 최대 건수")
    ap.add_argument(
        "--keep-none",
        action="store_true",
        help="reframe 이 none 으로 분해된 예시도 저장한다(기본은 건너뜀)",
    )
    args = ap.parse_args()

    for var in ("OPENAI_API_KEY", "SUPABASE_URL", "SUPABASE_KEY"):
        if not os.getenv(var):
            sys.exit(f"{var} 환경변수가 없다.")

    client = OpenAI()
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

    limit = 3 if args.dry_run else args.limit
    pending = fetch_pending(sb, limit)

    if not pending:
        print("백필할 행이 없다. (이미 전부 채워졌거나 examples 테이블이 비어 있다)")
        return

    print(f"대상 {len(pending)}건.")
    done = 0
    failed: list[int] = []
    no_reframe: list[int] = []

    for row in pending:
        result = decompose(client, row["input"], row["output"])

        if result is None:
            failed.append(row["id"])
            print(f"  [skip] id={row['id']} anchor 를 원문에서 찾지 못함")
            continue

        # v4 에서 reframe="none" 은 죽음·이별처럼 재해석하면 안 되는 경우에만 쓰는 값이다.
        # 재해석 구조가 없는 옛 예시(짧은 응원 댓글류)를 그대로 넣으면 few-shot 이
        # 모델에게 "재해석은 생략해도 된다" 를 가르치게 된다. 기본은 빼고 간다.
        if result["reframe"] == "none" and not args.keep_none:
            no_reframe.append(row["id"])
            print(f"  [skip] id={row['id']} reframe 없음 (재해석 구조가 없는 예시)")
            continue

        if args.dry_run:
            print(json.dumps({"id": row["id"], **result, "reply": row["output"]}, ensure_ascii=False, indent=2))
            done += 1
            continue

        # reply 는 생성물이 아니라 기존 output 그대로다.
        sb.table("examples").update({**result, "reply": row["output"]}).eq("id", row["id"]).execute()
        done += 1
        print(f"  {done}/{len(pending)} 완료 (id={row['id']})")

    print(f"\n백필 {done}건 완료, reframe 없어 건너뜀 {len(no_reframe)}건, 실패 {len(failed)}건.")
    if no_reframe:
        print(f"reframe 없는 id: {no_reframe}")
        print("이 예시들은 v4 재해석 구조가 없어 few-shot 재료로 적합하지 않다.")
        print("굳이 쓰려면 --keep-none 으로 다시 돌릴 수 있다.")
    if failed:
        print(f"실패한 id: {failed}")
        print("이 행들은 anchor 가 비어 있어 검색 대상에서 제외된다(서비스에는 영향 없음).")
        print("직접 채우거나, 그냥 두고 싶으면 delete 해도 된다.")


if __name__ == "__main__":
    main()
