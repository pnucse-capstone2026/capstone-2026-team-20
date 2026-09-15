from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Pattern


@dataclass
class MaskingResult:
    text: str
    masked: bool
    types: list[str] = field(default_factory=list)


PII_PATTERNS: list[tuple[str, Pattern[str]]] = [
    (
        "EMAIL",
        re.compile(
            r"(?<![A-Za-z0-9._%+-])"
            r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
            r"(?![A-Za-z0-9._%+-])"
        ),
    ),
    ("ID_NUMBER", re.compile(r"\b\d{6}[-\s]?[1-4]\d{6}\b")),
    ("CARD", re.compile(r"(?<!\d)(?:\d{4}[-\s]?){3}\d{4}(?!\d)")),
    (
        "PHONE",
        re.compile(
            r"(?<!\d)(?:01[016789][-\s.]?\d{3,4}[-\s.]?\d{4}|"
            r"02[-\s.]?\d{3,4}[-\s.]?\d{4}|"
            r"0[3-6][1-5][-\s.]?\d{3,4}[-\s.]?\d{4}|"
            r"070[-\s.]?\d{3,4}[-\s.]?\d{4})(?!\d)"
        ),
    ),
    (
        "ACCOUNT",
        re.compile(
            r"(?:(?:\uad6d\ubbfc|\uc2e0\ud55c|\uc6b0\ub9ac|\ud558\ub098|\ub18d\ud611|"
            r"\uce74\uce74\uc624|\ud1a0\uc2a4|\uae30\uc5c5|\uc0c8\ub9c8\uc744|"
            r"\uc218\ud611|\ubd80\uc0b0|\ub300\uad6c|\uad11\uc8fc|\uc804\ubd81|"
            r"\uacbd\ub0a8|\uc6b0\uccb4|SC|\uc528\ud2f0)\s*)?"
            r"(?:\uc740\ud589|\ubc45\ud06c)?\s*"
            r"(?<!\d)\d{2,6}[-\s]\d{2,6}[-\s]\d{2,8}(?!\d)"
        ),
    ),
    (
        "ADDRESS",
        re.compile(
            r"(?:\uc11c\uc6b8|\ubd80\uc0b0|\ub300\uad6c|\uc778\ucc9c|\uad11\uc8fc|"
            r"\ub300\uc804|\uc6b8\uc0b0|\uc138\uc885|\uacbd\uae30|\uac15\uc6d0|"
            r"\ucda9\ubd81|\ucda9\ub0a8|\uc804\ubd81|\uc804\ub0a8|\uacbd\ubd81|"
            r"\uacbd\ub0a8|\uc81c\uc8fc)"
            r"(?:\ud2b9\ubcc4\uc2dc|\uad11\uc5ed\uc2dc|\ud2b9\ubcc4\uc790\uce58\uc2dc|"
            r"\ud2b9\ubcc4\uc790\uce58\ub3c4|\ub3c4)?"
            r"[^\n,.;!?]{0,40}?(?:\uc2dc|\uad70|\uad6c)"
            r"[^\n,.;!?]{0,50}?(?:\ub3d9|\uba74|\uc74d|\ub85c|\uae38)"
            r"(?:\s?\d{1,5}(?:-\d{1,5})?)?"
        ),
    ),
]


def mask_sensitive_info(text: str) -> MaskingResult:
    masked_text = text
    found: list[str] = []

    for pii_type, pattern in PII_PATTERNS:
        if pattern.search(masked_text):
            masked_text = pattern.sub(f"[{pii_type}]", masked_text)
            found.append(pii_type)

    types = sorted(set(found))
    return MaskingResult(text=masked_text, masked=bool(types), types=types)
