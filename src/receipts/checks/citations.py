"""Every migrated step must cite a real source line; no executable source line may be silently dropped."""
from __future__ import annotations

import re

from ..config import Settings
from ..models import CheckResult, Status, Translation

NAME = "citations"
_IGNORABLE = re.compile(r"^\s*(#.*)?$")  # blank lines, comments, shebang
_LINE_REF = re.compile(r"\bline\s+(\d+)", re.I)


def check(source: str, t: Translation, cfg: Settings) -> CheckResult:
    lines = source.splitlines()
    if not t.steps:
        return CheckResult(NAME, Status.FAIL, "translation cites no steps")
    bad = [s.src_line for s in t.steps
           if not 1 <= s.src_line <= len(lines) or lines[s.src_line - 1].strip() != s.text.strip()]
    if bad:
        return CheckResult(NAME, Status.FAIL, f"steps cite lines that do not match source: {sorted(set(bad))}")
    covered = {s.src_line for s in t.steps}
    covered |= {int(n) for u in t.unknown for n in _LINE_REF.findall(u)}
    missing = [i for i, ln in enumerate(lines, 1) if not _IGNORABLE.match(ln) and i not in covered]
    if missing:
        return CheckResult(NAME, Status.FAIL,
                           f"source lines neither migrated nor listed as unknown: {missing}")
    return CheckResult(NAME, Status.PASS, f"{len(t.steps)} steps cited; every executable line accounted for")
