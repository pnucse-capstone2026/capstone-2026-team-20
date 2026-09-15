"""/ai/whale-message 지연 벤치.

같은 일기 샘플로 N번 호출해서 p50/p95/max 를 뽑는다. 앱에서 버튼을 몇 번 눌러 보는
것으로는 "느렸다/빨라졌다"까지밖에 못 말하는데, 수정 전후를 비교하려면 숫자가 필요하다.

구간 값은 CloudWatch 를 거치지 않고 응답의 X-Whale-Latency 헤더에서 바로 읽는다
(서버 미들웨어가 요청당 붙여 준다). 그래서 배포된 서버든 로컬이든 같은 방식으로 잰다.

--interval-sec 은 순차 요청의 '시작 시각 간' 최소 간격이다. 모델 호출이 이미 이 시간보다
오래 걸리면 추가로 쉬지 않는다. 실서비스 OpenAI TPM을 보수적으로 다룰 때 사용한다.

--out / --csv-out 은 일기 원문과 AI 답변을 저장하지 않는다. 요청별 성능·상태 숫자만
남기므로 결과 파일을 보고서 근거로 보관할 수 있다.

사용법
------
  # 운영 서버에서 24회 warm 요청을 6초 간격으로 측정한다.
  # JSONL은 재처리용, CSV는 보고서/스프레드시트용이다.
  python scripts/bench_whale_message.py --n 24 --interval-sec 6 \
      --url https://<your-host> --email you@example.com --password **** \
      --out out/latency-after.jsonl --csv-out out/latency-after.csv

  # 이미 토큰이 있으면 (앱 로그에서 복사하거나 supabase.auth.getSession())
  WHALE_BENCH_TOKEN=eyJ... python scripts/bench_whale_message.py --n 20 --url https://<your-host>

  # 동시 요청 4개로 부하 상황 확인 (워커가 모자라면 other_ms 가 커진다).
  # OpenAI TPM을 소진할 수 있으므로 운영 서버에서는 별도 시간대에 작은 n으로만 실행한다.
  python scripts/bench_whale_message.py --n 40 --concurrency 4 --url https://<your-host>

인증
----
--token / WHALE_BENCH_TOKEN 이 있으면 그걸 쓰고, 없으면 Supabase 비밀번호 로그인으로
토큰을 받는다. 로그인에는 .env 의 SUPABASE_URL 과 SUPABASE_ANON_KEY(없으면
SUPABASE_KEY)를 쓴다. 이메일·비밀번호는 --email/--password 또는 환경변수
BENCH_EMAIL/BENCH_PASSWORD.

CloudWatch 에서 같은 걸 보려면
------------------------------
  fields @timestamp, total_ms, gen_ms, gpt_calls, guard_attempts, guard_fallback
  | filter ep = "/ai/whale-message" and cold = 0 and ispresent(gen_ms)
  | stats count(*) as n,
          pct(total_ms, 50) as p50,
          pct(total_ms, 95) as p95,
          max(total_ms) as worst
          by guard_attempts

  # 어떤 검증 규칙이 재호출을 유발했는지
  fields guard_rules
  | filter ep = "/ai/whale-message" and guard_attempts > 1
  | stats count(*) by guard_rules
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import statistics
import sys
import time
import unicodedata
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

REQUEST_TIMEOUT_SEC = 60

# 안전 차단(위기·정책)에 걸리면 GPT 생성을 안 타서 훨씬 빨리 끝난다. 그런 요청이
# 섞이면 p50 이 실제보다 좋아 보이므로, 평범한 일기만 쓴다. 길이를 섞어 둔 건
# 프롬프트 토큰 수가 지연에 얼마나 영향을 주는지 같이 보기 위해서다.
SAMPLE_DIARIES = [
    "오늘 발표가 있었는데 목소리가 떨렸다. 그래도 끝까지 다 했다.",
    "아침에 늦잠을 자서 허둥지둥 나왔다. 지하철에서 사람들 사이에 껴 있는데 문득 내가 뭘 위해 이렇게까지 하나 싶었다. "
    "회사에 도착해서는 아무 일 없었던 것처럼 앉아서 일했다.",
    "친구랑 오랜만에 통화했다. 별 얘기 안 했는데도 기분이 좀 나아졌다.",
    "요즘 계속 피곤하다. 자도 자도 개운하지가 않고, 저녁만 되면 아무것도 하기 싫어진다. "
    "운동을 다시 시작해야 하나 싶다가도 막상 퇴근하면 눕기 바쁘다. 이런 내가 좀 한심하게 느껴진다.",
    "팀장님한테 피드백을 받았는데 맞는 말이라서 더 속상했다. 인정하기 싫었지만 내가 놓친 게 맞았다.",
    "저녁에 혼자 밥 먹으면서 예전 사진들을 봤다. 그때가 더 좋았나 싶기도 하고, 그냥 지금이 힘든 건가 싶기도 하다. "
    "정리가 잘 안 되는 하루였다.",
    "오늘은 그냥 무난했다. 특별히 좋지도 나쁘지도 않았다.",
    "미루던 일을 드디어 끝냈다. 생각보다 별거 아니었는데 왜 그렇게 미뤘는지 모르겠다.",
]


def _pct(values: list[float], p: int) -> float | None:
    """nearest-rank 백분위. n 이 20~50 인 벤치에선 보간법보다 해석이 명확하다."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(p / 100 * len(ordered)))
    return ordered[rank - 1]


def _login(email: str, password: str) -> str:
    """Supabase 비밀번호 로그인으로 access_token 을 받는다."""
    base = os.getenv("SUPABASE_URL")
    apikey = os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_KEY")
    if not base or not apikey:
        raise SystemExit("SUPABASE_URL 과 SUPABASE_ANON_KEY(또는 SUPABASE_KEY)가 .env 에 있어야 합니다.")

    req = urllib.request.Request(
        base.rstrip("/") + "/auth/v1/token?grant_type=password",
        data=json.dumps({"email": email, "password": password}).encode(),
        headers={"Content-Type": "application/json", "apikey": apikey},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SEC) as resp:
            token = json.loads(resp.read()).get("access_token")
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"로그인 실패 ({exc.code}): {exc.read().decode(errors='replace')[:200]}") from exc
    if not token:
        raise SystemExit("로그인 응답에 access_token 이 없습니다.")
    return token


def _call(url: str, token: str, diary: str, retry_count: int, user_agent: str) -> dict:
    """한 번 호출하고 왕복 시간과 서버가 붙여 준 구간 값을 함께 돌려준다."""
    body = json.dumps(
        {"diary": diary, "draft_id": str(uuid.uuid4()), "retry_count": retry_count},
        ensure_ascii=False,
    ).encode()
    req = urllib.request.Request(
        url.rstrip("/") + "/ai/whale-message",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": user_agent,
        },
        method="POST",
    )

    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SEC) as resp:
            payload = json.loads(resp.read())
            headers = resp.headers
            status = resp.status
    except urllib.error.HTTPError as exc:
        # HTTPError 도 응답이라 헤더를 들고 있다. 실패한 요청이 몇 초 걸렸는지도
        # 알아야 타임아웃을 어디에 걸지 정할 수 있다.
        return {
            "ok": False,
            "status": exc.code,
            "e2e_ms": round((time.perf_counter() - t0) * 1000),
            "error": exc.read().decode(errors="replace")[:200],
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": None,
            "e2e_ms": round((time.perf_counter() - t0) * 1000),
            "error": f"{type(exc).__name__}: {exc}",
        }
    e2e_ms = round((time.perf_counter() - t0) * 1000)

    result = {"ok": True, "status": status, "e2e_ms": e2e_ms, "diary_len": len(diary)}
    raw = headers.get("X-Whale-Latency")
    if raw:
        try:
            result.update(json.loads(raw))
        except json.JSONDecodeError:
            pass
    else:
        # 헤더가 없으면 계측이 안 들어간 서버(=main 브랜치)를 때리고 있는 것이다.
        result["no_timing_header"] = True
    result["whale_len"] = len(payload.get("whale") or "")
    return result


def _pad(label: str, width: int) -> str:
    """한글은 터미널에서 두 칸을 먹어서 f-string 의 :<n 으로는 열이 안 맞는다."""
    used = sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in label)
    return label + " " * max(1, width - used)


def _row(label: str, values: list[float]) -> str:
    if not values:
        return f"  {_pad(label, 16)} -"
    return (
        f"  {_pad(label, 16)} p50 {_pct(values, 50):>6.0f}ms   "
        f"p95 {_pct(values, 95):>6.0f}ms   "
        f"max {max(values):>6.0f}ms   "
        f"평균 {statistics.mean(values):>6.0f}ms"
    )


def _report(results: list[dict], warmup: list[dict]) -> None:
    ok = [r for r in results if r.get("ok")]
    failed = [r for r in results if not r.get("ok")]

    print()
    print(f"== /ai/whale-message  n={len(results)} (성공 {len(ok)}, 실패 {len(failed)}) ==")
    if warmup:
        first = warmup[0]
        print(f"  워밍업 1회 {first.get('e2e_ms')}ms (cold={first.get('cold')}) — 통계에서 제외")
    if not ok:
        for r in failed[:5]:
            print(f"  실패 status={r.get('status')} {r.get('error')}")
        return

    if any(r.get("no_timing_header") for r in ok):
        print("  ! X-Whale-Latency 헤더가 없다 — 계측이 안 들어간 서버를 때리고 있는지 확인할 것")

    def col(key: str) -> list[float]:
        return [r[key] for r in ok if isinstance(r.get(key), (int, float))]

    print()
    print(_row("체감(왕복)", col("e2e_ms")))
    print(_row("서버 전체", col("total_ms")))
    print(_row("  인증", col("auth_ms")))
    print(_row("  핸들러", col("handler_ms")))
    print(_row("  그 외", col("other_ms")))
    print()
    print(_row("moderation", col("mod_ms")))
    print(_row("  API", col("mod_api_ms")))
    print(_row("  문맥분류", col("mod_ctx_ms")))
    print(_row("임베딩", col("embed_ms")))
    print(_row("예시검색", col("examples_ms")))
    print(_row("기억검색", col("memories_ms")))
    print(_row("생성(guard)", col("gen_ms")))
    print(_row("  GPT 합", col("gpt_ms")))

    # 네트워크는 "체감 - 서버 전체". 서버를 더 깎아도 안 줄어드는 바닥값이라,
    # 목표 지연을 정할 때 이 값을 빼고 생각해야 한다.
    net = [
        r["e2e_ms"] - r["total_ms"]
        for r in ok
        if isinstance(r.get("total_ms"), (int, float))
    ]
    print(_row("네트워크", net))

    attempts = [r.get("guard_attempts") for r in ok if r.get("guard_attempts")]
    if attempts:
        print()
        hist = {n: attempts.count(n) for n in sorted(set(attempts))}
        summary = "  ".join(f"{n}회 {c}건" for n, c in hist.items())
        fallback = sum(1 for r in ok if r.get("guard_fallback"))
        print(f"  guard 호출 횟수  {summary}   폴백 {fallback}건")
        # 재호출이 곧 지연이었으므로, 1회로 끝난 요청과 2회 걸린 요청의 차이가
        # max_fix_attempts 를 더 손댔을 때 얻을 수 있는 상한이다.
        for n in hist:
            same = [r["total_ms"] for r in ok if r.get("guard_attempts") == n and r.get("total_ms")]
            if same:
                print(f"    {n}회일 때 서버 전체 p50 {_pct(same, 50):.0f}ms")

    early = [r.get("early_return") for r in ok if r.get("early_return")]
    if early:
        print(f"  안전 차단으로 조기 반환 {len(early)}건 — 생성 구간이 비어 있어 통계가 낙관적으로 보일 수 있음")

    if failed:
        print()
        for r in failed[:5]:
            print(f"  실패 status={r.get('status')} {r.get('e2e_ms')}ms {r.get('error')}")


def _write_csv(path: str, results: list[dict], warmup: list[dict]) -> None:
    """원문 일기 없이 요청별 계측값만 CSV로 남긴다.

    JSONL은 로그/재처리에 편하지만 보고서 표나 스프레드시트에는 불편하다. 응답 문장과
    입력 일기는 개인정보가 될 수 있으므로 저장하지 않고, 성능·상태 필드만 고정한다.
    """
    fields = [
        "run_id", "label", "measured_at_utc", "url", "concurrency", "interval_sec", "retry_count",
        "warmup", "ok", "status", "e2e_ms", "total_ms", "auth_ms", "handler_ms", "other_ms",
        "mod_ms", "mod_api_ms", "mod_ctx_ms", "embed_ms", "examples_ms", "memories_ms",
        "gen_ms", "gpt_ms", "gpt_calls", "guard_attempts", "guard_fallback", "cold",
        "early_return", "diary_len", "whale_len",
    ]
    rows = [({**row, "warmup": True}) for row in warmup]
    rows.extend({**row, "warmup": False} for row in results)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="/ai/whale-message 지연 벤치")
    parser.add_argument("--url", default=os.getenv("WHALE_API_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--n", type=int, default=20, help="측정 호출 수 (워밍업 제외)")
    parser.add_argument("--concurrency", type=int, default=1, help="동시 요청 수")
    parser.add_argument("--warmup", type=int, default=1, help="통계에서 뺄 예열 호출 수")
    parser.add_argument("--retry-count", type=int, default=0, help="'다른 한마디' 재요청 상황을 재현")
    parser.add_argument(
        "--user-agent",
        default="WhaleBench/1.0 (+capstone-performance-test)",
        help="벤치 요청 식별용 User-Agent (Cloudflare 보안 이벤트에서 확인할 값)",
    )
    parser.add_argument(
        "--interval-sec",
        type=float,
        default=0,
        help="순차 요청 사이의 최소 간격(초). TPM 한도를 피할 때 사용; 동시 요청에서는 무시",
    )
    parser.add_argument("--token", default=os.getenv("WHALE_BENCH_TOKEN"))
    parser.add_argument("--email", default=os.getenv("BENCH_EMAIL"))
    parser.add_argument("--password", default=os.getenv("BENCH_PASSWORD"))
    parser.add_argument("--diary-file", help="한 줄에 일기 하나. 없으면 내장 샘플을 돌려 쓴다")
    parser.add_argument("--out", help="요청별 원자료를 JSONL 로 저장할 경로")
    parser.add_argument("--csv-out", help="보고서/스프레드시트용 성능 원자료 CSV 저장 경로")
    parser.add_argument(
        "--label",
        default="",
        help="비교용 실행 이름 (예: before-guard, after-guard). CSV/JSONL에 함께 저장",
    )
    args = parser.parse_args()

    if args.interval_sec < 0:
        raise SystemExit("--interval-sec 은 0 이상이어야 합니다.")
    if args.interval_sec and args.concurrency > 1:
        print("! --interval-sec 은 동시 요청에서는 적용되지 않습니다.", file=sys.stderr)

    # --url 에 Supabase 주소를 넣기 쉽다(토큰을 거기서 받으니까). 그러면 Supabase 가
    # /ai/whale-message 를 404 로 돌려줘서 20번 다 실패한 뒤에야 알게 된다.
    if "supabase.co" in args.url:
        raise SystemExit(
            f"--url 은 AI 서버 주소여야 합니다 (예: https://api.whale-done.com). "
            f"Supabase 주소({args.url})는 토큰 받을 때 .env 의 SUPABASE_URL 로 알아서 씁니다."
        )

    token = args.token
    if not token:
        if not (args.email and args.password):
            raise SystemExit(
                "--token 이 없으면 --email/--password (또는 BENCH_EMAIL/BENCH_PASSWORD)가 필요합니다."
            )
        token = _login(args.email, args.password)

    diaries = SAMPLE_DIARIES
    if args.diary_file:
        lines = [l.strip() for l in Path(args.diary_file).read_text(encoding="utf-8").splitlines()]
        diaries = [l for l in lines if l] or SAMPLE_DIARIES

    def run(i: int) -> dict:
        return _call(args.url, token, diaries[i % len(diaries)], args.retry_count, args.user_agent)

    warmup: list[dict] = []
    if args.warmup > 0:
        print(f"워밍업 {args.warmup}회...", flush=True)
        warmup = [run(i) for i in range(args.warmup)]
        print(f"워밍업 완료: {warmup[0].get('status')} / {warmup[0].get('e2e_ms')}ms", flush=True)

    print(f"{args.url} 로 {args.n}회 (동시 {args.concurrency})...", flush=True)
    t0 = time.perf_counter()
    if args.concurrency <= 1:
        results = []
        for i in range(args.n):
            request_started = time.perf_counter()
            result = run(args.warmup + i)
            results.append(result)
            print(
                f"  [{i + 1}/{args.n}] status={result.get('status')} "
                f"e2e={result.get('e2e_ms')}ms",
                flush=True,
            )
            # 호출 시작 간격을 기준으로 쉬어야 느린 요청에 불필요한 대기가 붙지 않는다.
            remaining = args.interval_sec - (time.perf_counter() - request_started)
            if remaining > 0 and i < args.n - 1:
                time.sleep(remaining)
    else:
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            results = list(pool.map(run, range(args.warmup, args.warmup + args.n)))
    wall = time.perf_counter() - t0

    # 결과 파일 하나만 봐도 어떤 조건으로 잰 것인지 알 수 있어야 전후 비교가 가능하다.
    # URL에는 토큰이 없고, 일기 원문·AI 답변은 어느 결과에도 넣지 않는다.
    run_meta = {
        "run_id": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "label": args.label,
        "measured_at_utc": datetime.now(timezone.utc).isoformat(),
        "url": args.url.rstrip("/"),
        "concurrency": args.concurrency,
        "interval_sec": args.interval_sec,
        "retry_count": args.retry_count,
    }
    warmup = [{**run_meta, **result} for result in warmup]
    results = [{**run_meta, **result} for result in results]

    _report(results, warmup)
    print()
    print(f"  총 소요 {wall:.1f}s  처리량 {len(results) / wall:.2f} req/s")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            for r in warmup:
                f.write(json.dumps({**r, "warmup": True}, ensure_ascii=False) + "\n")
            for r in results:
                f.write(json.dumps({**r, "warmup": False}, ensure_ascii=False) + "\n")
        print(f"  원자료 → {args.out}")

    if args.csv_out:
        _write_csv(args.csv_out, results, warmup)
        print(f"  CSV 원자료 → {args.csv_out}")


if __name__ == "__main__":
    main()
