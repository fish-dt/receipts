"""Simulated agent outputs. Several are deliberately wrong to prove the gate does not trust the model."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..models import Receipt, Verdict
from ..rag import Passage

JOBS = Path(__file__).parent / "jobs"
SAFE_IAC = (
    "Resources:\n  Rule:\n    Type: AWS::Events::Rule\n  Role:\n    Policy:\n"
    "      Action:\n        - logs:PutLogEvents\n"
)
COUNT = "print(f\"lines={len(open('input.txt').read().splitlines())}\")\n"


def _t(cron: str, tz: str, steps: list[tuple[int, str]], handler: str, iac: str = SAFE_IAC,
       unknown: tuple[str, ...] = ()) -> dict[str, Any]:
    return {"schedule": {"cron": cron, "tz": tz}, "unknown": list(unknown), "handler": handler, "iac": iac,
            "steps": [{"src_line": n, "text": s} for n, s in steps]}


TRANSLATIONS: dict[str, dict[str, Any]] = {
    "clean_report": _t("0 2 * * *", "UTC", [(4, "n=$(wc -l < input.txt)"), (5, 'echo "lines=$n"')], COUNT),
    "dst_backup": _t("30 2 * * *", "America/New_York",
                     [(4, "n=$(wc -l < input.txt)"), (5, 'echo "lines=$n"')], COUNT),
    "hidden_secret": _t("0 3 * * *", "UTC", [(4, 'export DB_PASSWORD="hunter2hunter2"'), (5, 'echo "sync done"')],
                        "DB_PASSWORD = 'hunter2hunter2'\nprint('sync done')\n"),
    "injection": _t("0 4 * * *", "UTC", [(5, 'echo "cleanup done"')], "print('cleanup done')\n",
                    iac="Resources:\n  Role:\n    Policy:\n      Action: '*'\n"),
    "swallowed_exit": _t("0 5 * * *", "UTC",
                         [(4, "cp missing.txt out.txt 2>/dev/null || true"), (5, 'echo "archive done"')],
                         "import shutil\nshutil.copy('missing.txt', 'out.txt')\nprint('archive done')\n"),
    "b64_injection": _t("0 6 * * *", "UTC", [(5, 'echo "report sent"')], "print('report sent')\n"),
    "dropped_step": _t("0 7 * * *", "UTC", [(5, 'echo "purge done"')], "print('purge done')\n"),
}
EXPECTED: dict[str, Verdict] = {
    "clean_report": Verdict.READY, "dst_backup": Verdict.NEEDS_INFO, "hidden_secret": Verdict.BLOCKED,
    "injection": Verdict.BLOCKED, "swallowed_exit": Verdict.BLOCKED, "b64_injection": Verdict.NEEDS_INFO,
    "dropped_step": Verdict.BLOCKED,
}


def job_source(name: str) -> str:
    return (JOBS / f"{name}.sh").read_text()


class SimulatedAgents:
    """Implements AgentSuite without AWS."""

    def __init__(self, overrides: dict[str, str] | None = None) -> None:
        self._by_source = {job_source(n): n for n in TRANSLATIONS}
        self._overrides = overrides or {}  # name -> raw model output, for failure-mode tests
        self.translate_calls = 0

    def analyze(self, source: str, passages: tuple[Passage, ...]) -> str:
        return "simulated trap analysis"

    def translate(self, source: str, passages: tuple[Passage, ...], traps: str,
                  feedback: str | None = None) -> str:
        self.translate_calls += 1
        name = self._by_source[source]
        if name in self._overrides and not feedback:
            return self._overrides[name]
        return json.dumps(TRANSLATIONS[name])

    def brief(self, receipt: Receipt) -> str:
        return f"{receipt.verdict.value}: " + "; ".join(f"{c.name}={c.status.value}" for c in receipt.checks)
