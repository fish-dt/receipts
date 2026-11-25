"""The gate: the only component that can produce a verdict. Fails closed on any error."""
from __future__ import annotations

import logging
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from .checks import REGISTRY
from .config import Settings
from .models import JOB_NAME, CheckResult, Receipt, Status, Translation, TranslationError, Verdict

log = logging.getLogger(__name__)


def _run_check(name: str, fn, source: str, t: Translation, cfg: Settings) -> CheckResult:
    try:
        return fn(source, t, cfg)
    except Exception as exc:  # noqa: BLE001 - a crashing check must block, not crash the gate
        log.error("check %s crashed: %s", name, type(exc).__name__)
        return CheckResult(name, Status.FAIL, f"check crashed ({type(exc).__name__}); failing closed")


def _verdict(checks: tuple[CheckResult, ...]) -> Verdict:
    statuses = {c.status for c in checks}
    if Status.FAIL in statuses:
        return Verdict.BLOCKED
    return Verdict.NEEDS_INFO if Status.NEEDS_INFO in statuses else Verdict.READY


def blocked(job: str, source: str, check: str, reason: str) -> Receipt:
    """A BLOCKED receipt for failures that happen before the checks can run."""
    return Receipt.build(job, Verdict.BLOCKED, (CheckResult(check, Status.FAIL, reason),), source, None)


def evaluate(job: str, source: str, translation: Translation | Mapping[str, Any] | str,
             cfg: Settings) -> Receipt:
    """Run all checks concurrently and issue a receipt. `job` is a caller-supplied label, never model output."""
    if not JOB_NAME.match(job):
        raise ValueError("invalid job name")
    try:
        if isinstance(translation, str):
            t = Translation.from_text(translation)
        elif isinstance(translation, Translation):
            t = translation
        else:
            t = Translation.from_dict(translation)
    except TranslationError as exc:
        return blocked(job, source, "schema", str(exc))
    with ThreadPoolExecutor(max_workers=len(REGISTRY)) as pool:
        futures = [pool.submit(_run_check, n, fn, source, t, cfg) for n, fn in REGISTRY]
        checks = tuple(f.result() for f in futures)
    receipt = Receipt.build(job, _verdict(checks), checks, source, t.to_dict())
    log.info("job=%s verdict=%s checks=%s", job, receipt.verdict.value,
             {c.name: c.status.value for c in checks})
    return receipt
