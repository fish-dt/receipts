"""Differential execution: run the original and the migrated job on the same fixture and compare.

Both run in a throwaway directory with an empty environment, CPU/file/memory limits and a wall-clock
timeout. This is defense in depth, NOT isolation: run the gate itself in a network-less container or
microVM in production.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import signal
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ..config import Settings
from ..models import CheckResult, Status, Translation

NAME = "parity"
_ENV = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "TZ": "UTC"}
_WRAP = 'ulimit -t 5; ulimit -f 1024; ulimit -v 524288 2>/dev/null; exec "$@"'
_MAX_OUT = 65_536


@dataclass(frozen=True)
class Outcome:
    stdout: str
    exit_code: int
    files: dict[str, str]


def _run(argv: list[str], script_name: str, script: str, fixture_dir: Path, timeout: float) -> Outcome:
    with tempfile.TemporaryDirectory(prefix="receipts-") as tmp:
        work = Path(tmp)
        for f in fixture_dir.iterdir():
            if f.is_file():
                shutil.copy(f, work / f.name)
        (work / script_name).write_text(script)
        proc = subprocess.Popen(  # noqa: S603
            ["/bin/bash", "-c", _WRAP, "_", *argv, script_name], cwd=work, env=_ENV,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, errors="replace", start_new_session=True)
        try:
            out, _ = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
            raise
        files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in sorted(work.iterdir()) if p.is_file() and p.name != script_name}
    return Outcome(out[:_MAX_OUT], proc.returncode, files)


def check(source: str, t: Translation, cfg: Settings) -> CheckResult:
    if not cfg.fixture_dir.is_dir():
        return CheckResult(NAME, Status.NEEDS_INFO, "no fixture directory configured")
    try:
        old = _run(["/bin/bash"], "job.sh", source, cfg.fixture_dir, cfg.parity_timeout_s)
        new = _run([sys.executable, "-I"], "handler.py", t.handler, cfg.fixture_dir, cfg.parity_timeout_s)
    except subprocess.TimeoutExpired:
        return CheckResult(NAME, Status.FAIL, f"a run exceeded {cfg.parity_timeout_s}s and was killed")
    diffs = [n for n, same in (("exit code", old.exit_code == new.exit_code),
                               ("stdout", old.stdout == new.stdout),
                               ("files written", old.files == new.files)) if not same]
    if diffs:  # never echo outputs: they may contain secrets
        return CheckResult(NAME, Status.FAIL, "behavior differs on fixture: " + ", ".join(diffs))
    return CheckResult(NAME, Status.PASS, f"exit code, stdout and files match (exit {old.exit_code})")
