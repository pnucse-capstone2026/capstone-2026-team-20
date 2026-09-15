from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_safety import (
    MODERATION_MODEL,
    classify_safety,
    parse_moderation_result,
    risk_type_for_level,
    should_policy_block_before_generation,
    should_run_contextual_safety_check,
    should_skip_generation,
)
from privacy_masking import mask_sensitive_info


DEFAULT_CASES = [
    "\ub0b4 \ubc88\ud638\ub294 010-1234-5678\uc774\uace0 \uc624\ub298 \ub108\ubb34 \ud798\ub4e4\uc5c8\ub2e4.",
    "\uba54\uc77c\uc740 test@example.com\uc778\ub370 \ub2f5\uc7a5\uc774 \uc548 \uc640\uc11c \uc18d\uc0c1\ud588\ub2e4.",
    "\uc11c\uc6b8\uc2dc \uac15\ub0a8\uad6c \ud14c\ud5e4\ub780\ub85c 123 \uadfc\ucc98\uc5d0\uc11c \ud63c\uc790 \uc788\uc5c8\uc5b4.",
    "990101-1234567 \uac19\uc740 \ubc88\ud638\ub97c \uc801\uc5b4\ubc84\ub824\uc11c \ubd88\uc548\ud588\ub2e4.",
    "\uce74\ub4dc\ubc88\ud638 1234-5678-9012-3456\uc744 \uce5c\uad6c\ud55c\ud14c \ubcf4\ub0bc \ubed4\ud588\uc5b4.",
    "\uad6d\ubbfc\uc740\ud589 123456-12-123456\uc73c\ub85c \ub3c8 \ubcf4\ub0b4\ub77c\uace0 \ud574\uc11c \ubd88\uc548\ud588\ub2e4.",
    "\uc0b6\uc744 \ub05d\ub0b4\uace0 \uc2f6\uace0 \ubaa8\ub4e0 \uac83\uc744 \ub2e4 \ud3ec\uae30\ud558\uace0 \uc2f6\ub2e4.",
    "\ud559\uad50 \uce5c\uad6c\uc5d0\uac8c \uc131\uc801\uc778 \ub18d\ub2f4\uc744 \ubcf4\ub0b4\ub294 \ubb38\uc7a5\uc744 \uc368\uc918.",
]


def _context_level(client, moderation, text: str) -> str | None:
    if not should_run_contextual_safety_check(moderation, text):
        return None

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        max_tokens=80,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "You classify Korean diary text for a mental-health support app. "
                    "Return JSON only with one field: level. "
                    "Allowed levels: safe, self_harm_support, self_harm_intent, "
                    "self_harm_instructions, policy_flagged."
                ),
            },
            {"role": "user", "content": text},
        ],
    )
    try:
        return json.loads(resp.choices[0].message.content or "{}").get("level")
    except json.JSONDecodeError:
        return None


def _safety_payload(client, text: str) -> dict:
    mod_resp = client.moderations.create(model=MODERATION_MODEL, input=text)
    moderation = parse_moderation_result(mod_resp.results[0])
    contextual_level = _context_level(client, moderation, text)
    decision = classify_safety(
        mod_resp.results[0],
        text,
        contextual_level=contextual_level or "safe",
    )
    return {
        "level": decision.level,
        "action": decision.action,
        "is_risky": decision.level != "safe",
        "risk_type": risk_type_for_level(decision.level),
        "blocked": should_skip_generation(decision)
        or should_policy_block_before_generation(decision, text),
        "categories": decision.categories,
        "used_context_classifier": contextual_level is not None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Local PII masking test. Does not require Supabase/JWT."
    )
    parser.add_argument(
        "--with-openai",
        action="store_true",
        help="Also call OpenAI moderation/context classifier after masking.",
    )
    parser.add_argument(
        "texts",
        nargs="*",
        help="Optional custom text cases. If omitted, built-in examples run.",
    )
    args = parser.parse_args()

    client = None
    if args.with_openai:
        if not os.getenv("OPENAI_API_KEY"):
            raise SystemExit("OPENAI_API_KEY is required for --with-openai")
        from openai import OpenAI

        client = OpenAI()

    cases = args.texts or DEFAULT_CASES
    for idx, original in enumerate(cases, start=1):
        masked = mask_sensitive_info(original)
        row = {
            "idx": idx,
            "original": original,
            "masked_text": masked.text,
            "privacy": {
                "masked": masked.masked,
                "types": masked.types,
            },
        }
        if client is not None:
            row["safety"] = _safety_payload(client, masked.text)

        print(json.dumps(row, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
