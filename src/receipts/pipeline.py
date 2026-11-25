"""Deterministic workflow. The path is fixed, so code (not an LLM) orchestrates; agents do bounded tasks."""
from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass

from .agents import AgentSuite
from .config import Settings
from .gate import blocked, evaluate
from .models import JOB_NAME, Receipt, Translation, TranslationError, sha256_text
from .rag import retrieve_all
from .state import ReceiptStore

log = logging.getLogger(__name__)
MAX_TRANSLATE_ATTEMPTS = 2


@dataclass(frozen=True)
class MigrationResult:
    receipt: Receipt
    brief: str  # LLM-written, non-authoritative summary


def migrate(job: str, source: str, agents: AgentSuite, cfg: Settings, store: ReceiptStore | None = None,
            screen: Callable[[str], bool] | None = None) -> MigrationResult:
    if not JOB_NAME.match(job):
        raise ValueError("invalid job name")
    if len(source.encode()) > cfg.max_source_bytes:
        return MigrationResult(blocked(job, source, "input", "job exceeds size limit"), "")
    job_id = f"{job}-{sha256_text(source)[:12]}"
    version = store.create(job_id) if store else 0

    def record(step: str, **data) -> None:
        nonlocal version
        if store:
            version = store.append(job_id, {"step": step, **data}, version)

    if screen is not None:
        try:
            allowed = screen(source)
        except Exception as exc:  # noqa: BLE001 - fail closed if screening is unavailable
            log.error("guardrail unavailable: %s", type(exc).__name__)
            allowed = False
        record("screen", allowed=allowed)
        if not allowed:
            return MigrationResult(blocked(job, source, "guardrail", "input screening blocked or unavailable"), "")

    query = " ".join(re.findall(r"[A-Za-z0-9_/:.-]+", source))[:500]
    retrieval = retrieve_all(query, cfg)
    record("retrieve", passages=len(retrieval.passages), degraded=list(retrieval.degraded))
    traps = agents.analyze(source, retrieval.passages)
    record("analyze")

    raw, feedback = "", None
    for attempt in range(1, MAX_TRANSLATE_ATTEMPTS + 1):
        raw = agents.translate(source, retrieval.passages, traps, feedback)
        try:
            Translation.from_text(raw)
            break
        except TranslationError as exc:
            feedback = str(exc)
            record("translate_retry", attempt=attempt)
    receipt = evaluate(job, source, raw, cfg)  # final authority; malformed output becomes BLOCKED
    record("gate", verdict=receipt.verdict.value, receipt_sha256=receipt.receipt_sha256)
    brief = agents.brief(receipt)
    return MigrationResult(receipt, brief)
