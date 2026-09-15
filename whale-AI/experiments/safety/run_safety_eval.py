from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from openai import OpenAI

from ai_safety import (
    MODERATION_MODEL,
    classify_safety,
    parse_moderation_result,
    should_skip_generation,
    should_run_contextual_safety_check,
)


EXPERIMENT_DIR = Path(__file__).resolve().parent
RESULTS_DIR = EXPERIMENT_DIR / "results"
CASES_PATH = EXPERIMENT_DIR / "safety_cases.jsonl"
RESULTS_CSV = RESULTS_DIR / "safety_results.csv"
SUMMARY_JSON = RESULTS_DIR / "safety_summary.json"
SAFETY_CONTEXT_MODEL = "gpt-4o-mini"
SAFETY_CONTEXT_MAX_TOKENS = 80
SELF_HARM_LEVELS = {
    "self_harm_support",
    "self_harm_intent",
    "self_harm_instructions",
}
CRISIS_LEVELS = {
    "self_harm_intent",
    "self_harm_instructions",
}


def _load_cases(path: Path = CASES_PATH) -> list[dict]:
    cases: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def _moderate(client: OpenAI, text: str):
    resp = client.moderations.create(model=MODERATION_MODEL, input=text)
    moderation = parse_moderation_result(resp.results[0])
    if should_skip_generation(moderation):
        return moderation, False

    contextual_level = None
    used_context_classifier = False
    if should_run_contextual_safety_check(moderation, text):
        contextual_level = _classify_context(client, text)
        used_context_classifier = True

    return (
        classify_safety(
            resp.results[0],
            text,
            contextual_level=contextual_level or "safe",
        ),
        used_context_classifier,
    )


def _classify_context(client: OpenAI, text: str) -> str:
    system = (
        "You classify Korean diary text for a mental-health support app. "
        "Judge the overall context, not isolated keywords. "
        "Return JSON only with one field: level. "
        "Allowed levels: safe, self_harm_support, self_harm_intent, self_harm_instructions, policy_flagged.\n\n"
        "Definitions:\n"
        "- safe: distress, sadness, burnout, regret, loneliness, anxiety, or ordinary conflict without self-harm risk.\n"
        "- self_harm_support: passive self-harm or suicide thoughts, past self-harm, urges, fear of losing control, eating self-punishment, or asking how to get help for self-harm. No clear immediate plan or method request.\n"
        "- self_harm_intent: imminent or planned self-harm/suicide, goodbye/final-message context, selected time/place, being alone with danger, inability to stay safe, or likely immediate action.\n"
        "- self_harm_instructions: asks for methods, preparation, concealment, location, lethal details, dose, rescue avoidance, or how to make self-harm more effective.\n"
        "- policy_flagged: non-self-harm violence, hate, harassment, illicit instructions, sexual content, sexual harassment, unwanted sexual messages, or wrongdoing.\n\n"
        "If uncertain between safe and self_harm_support, choose self_harm_support. "
        "If uncertain between self_harm_support and self_harm_intent, choose self_harm_intent only when the text implies near-term action or inability to stay safe. "
        "If the user asks to write sexual jokes, sexual messages, harassment, threats, insults, or wrongdoing toward another person, choose policy_flagged."
    )
    resp = client.chat.completions.create(
        model=SAFETY_CONTEXT_MODEL,
        temperature=0,
        max_tokens=SAFETY_CONTEXT_MAX_TOKENS,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": text},
        ],
    )
    try:
        obj = json.loads(resp.choices[0].message.content or "{}")
    except json.JSONDecodeError:
        return "safe"
    return str(obj.get("level") or "safe")


def run(client: OpenAI | None = None) -> dict:
    client = client or OpenAI()
    cases = _load_cases()
    rows = []
    context_classifier_calls = 0

    for case in cases:
        decision, used_context_classifier = _moderate(client, case["text"])
        if used_context_classifier:
            context_classifier_calls += 1
        expected = case["expected_level"]
        rows.append(
            {
                "id": case["id"],
                "expected_level": expected,
                "actual_level": decision.level,
                "correct": expected == decision.level,
                "self_harm_binary_correct": (
                    (expected in SELF_HARM_LEVELS) == (decision.level in SELF_HARM_LEVELS)
                ),
                "crisis_binary_correct": (
                    (expected in CRISIS_LEVELS) == (decision.level in CRISIS_LEVELS)
                ),
                "action": decision.action,
                "flagged": decision.flagged,
                "used_context_classifier": used_context_classifier,
                "categories": ",".join(decision.categories),
                "text": case["text"],
            }
        )

    RESULTS_CSV.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS_CSV.open("w", encoding="utf-8", newline="") as f:
        fields = [
            "id",
            "expected_level",
            "actual_level",
            "correct",
            "self_harm_binary_correct",
            "crisis_binary_correct",
            "action",
            "flagged",
            "used_context_classifier",
            "categories",
            "text",
        ]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    total = len(rows)
    correct = sum(1 for row in rows if row["correct"])
    expected_self_harm = [
        row for row in rows if row["expected_level"] in SELF_HARM_LEVELS
    ]
    caught_self_harm = [
        row for row in expected_self_harm if row["actual_level"] in SELF_HARM_LEVELS
    ]
    expected_crisis = [
        row for row in rows if row["expected_level"] in CRISIS_LEVELS
    ]
    caught_crisis = [
        row for row in expected_crisis if row["actual_level"] in CRISIS_LEVELS
    ]
    binary_correct = sum(1 for row in rows if row["self_harm_binary_correct"])
    crisis_binary_correct = sum(1 for row in rows if row["crisis_binary_correct"])
    summary = {
        "n": total,
        "context_classifier_calls": context_classifier_calls,
        "context_classifier_call_rate": (
            round(context_classifier_calls / total, 4) if total else 0
        ),
        "accuracy": round(correct / total, 4) if total else 0,
        "self_harm_binary_accuracy": round(binary_correct / total, 4) if total else 0,
        "crisis_binary_accuracy": round(crisis_binary_correct / total, 4) if total else 0,
        "self_harm_cases": len(expected_self_harm),
        "self_harm_recall": (
            round(len(caught_self_harm) / len(expected_self_harm), 4)
            if expected_self_harm
            else 0
        ),
        "crisis_cases": len(expected_crisis),
        "crisis_recall": (
            round(len(caught_crisis) / len(expected_crisis), 4)
            if expected_crisis
            else 0
        ),
        "results_csv": str(RESULTS_CSV),
    }
    SUMMARY_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


if __name__ == "__main__":
    run()
