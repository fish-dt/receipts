"""Secrets and over-broad permissions. Findings are located by artifact and line, never echoed."""
from __future__ import annotations

import math
import re
from collections import Counter

from ..config import Settings
from ..models import CheckResult, Status, Translation

NAME = "secrets"
_PATTERNS = {
    "aws-access-key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "private-key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "credential-assignment": re.compile(
        r"(?i)(pass(word|wd)?|secret|token|api[_-]?key)\w*\s*[=:]\s*[\"']?(?![$!{])[^\s\"']{6,}"),
}
_TOKEN = re.compile(r"[A-Za-z0-9+/_=-]{24,}")
_WILDCARD_LINE = re.compile(r"""^\s*-?\s*["']?(\*|[\w-]+:\*)["']?\s*,?\s*$""")
_WILDCARD_KV = re.compile(r"""(?i)\b(Action|NotAction|Resource)\b["']?\s*:\s*\[?\s*["']?(\*|[\w-]+:\*)""")


def _entropy(s: str) -> float:
    n = len(s)
    return -sum(c / n * math.log2(c / n) for c in Counter(s).values())


def _scan(label: str, text: str, wildcards: bool) -> tuple[list[str], list[str]]:
    """Return (definite findings, heuristic findings)."""
    hard: list[str] = []
    soft: list[str] = []
    for no, line in enumerate(text.splitlines(), 1):
        hard += [f"{kind} in {label} line {no}" for kind, rx in _PATTERNS.items() if rx.search(line)]
        if wildcards and (_WILDCARD_LINE.match(line) or _WILDCARD_KV.search(line)):
            hard.append(f"wildcard permission in {label} line {no}")
        if any(_entropy(m) >= 4.2 for m in _TOKEN.findall(line)):
            soft.append(f"possible secret (high-entropy string) in {label} line {no}")
    return hard, soft


def check(source: str, t: Translation, cfg: Settings) -> CheckResult:
    scans = [_scan("source", source, False), _scan("handler", t.handler, False), _scan("iac", t.iac, True)]
    hard = [f for h, _ in scans for f in h]
    soft = [f for _, s in scans for f in s]
    if hard:
        return CheckResult(NAME, Status.FAIL, "; ".join(dict.fromkeys(hard)))
    if soft:
        return CheckResult(NAME, Status.NEEDS_INFO, "; ".join(dict.fromkeys(soft)))
    return CheckResult(NAME, Status.PASS, "no secrets or wildcard permissions found")
