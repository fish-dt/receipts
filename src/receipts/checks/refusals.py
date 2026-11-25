"""Refusal ledger: instruction-like text in the job is data. Record it, ignore it, route to a human."""
from __future__ import annotations

import base64
import binascii
import re
from collections.abc import Iterator

from ..config import Settings
from ..models import CheckResult, Status, Translation

NAME = "refusals"
_INJECT = re.compile(
    r"(?i)(ignore\s+(all\s+|any\s+|the\s+)?(previous\s+|prior\s+|above\s+)?(rules|instructions)"
    r"|\bSYSTEM\s*:|grant\b.*\badmin|deploy\s+now|disregard\b.*\b(rules|policy)"
    r"|skip\s+(the\s+)?(checks?|parity|review))")
_B64 = re.compile(r"[A-Za-z0-9+/]{24,}={0,2}")


def _decoded(line: str) -> Iterator[str]:
    for m in _B64.finditer(line):
        try:
            yield base64.b64decode(m.group(), validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError, ValueError):
            continue


def check(source: str, t: Translation, cfg: Settings) -> CheckResult:
    notes: list[str] = []
    for no, line in enumerate(source.splitlines(), 1):
        if _INJECT.search(line):
            notes.append(f"line {no}: instruction-like text in source ignored")
        elif any(_INJECT.search(d) for d in _decoded(line)):
            notes.append(f"line {no}: encoded instruction-like text in source ignored")
    notes += [f"unknown step: {u[:200]}" for u in t.unknown]
    if notes:
        return CheckResult(NAME, Status.NEEDS_INFO, f"{len(notes)} item(s) need a human", tuple(notes))
    return CheckResult(NAME, Status.PASS, "nothing refused")
