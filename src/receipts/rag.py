"""Parallel retrieval over the three knowledge bases, with per-KB timeout and graceful degradation."""
from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass

from .config import PACKAGE_DIR, Settings
from .models import sha256_text

log = logging.getLogger(__name__)
KB_FILES = {"schedule": "schedule_traps.md", "security": "security_rules.md", "mapping": "aws_mapping.md"}


@dataclass(frozen=True)
class Passage:
    kb: str
    text: str
    score: float


@dataclass(frozen=True)
class Retrieval:
    passages: tuple[Passage, ...]
    degraded: tuple[str, ...]  # KBs that failed or timed out; callers must treat results as partial


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _search_local(kb: str, query: str, k: int) -> list[Passage]:
    text = (PACKAGE_DIR / "kb" / KB_FILES[kb]).read_text()
    chunks = [c.strip() for c in text.split("\n## ")[1:]]
    q = _words(query)
    ranked = sorted(((len(q & _words(c)), c) for c in chunks), reverse=True)
    return [Passage(kb, c, float(s)) for s, c in ranked[:k] if s > 0]


def _search_bedrock(kb: str, query: str, kb_id: str, cfg: Settings, k: int) -> list[Passage]:
    import boto3
    from botocore.config import Config

    client = boto3.client("bedrock-agent-runtime", region_name=cfg.region,
                          config=Config(read_timeout=cfg.kb_timeout_s, retries={"max_attempts": 2}))
    resp = client.retrieve(knowledgeBaseId=kb_id, retrievalQuery={"text": query[:1000]},
                           retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": k}})
    return [Passage(kb, r["content"]["text"], float(r.get("score", 0))) for r in resp["retrievalResults"]]


def _search(kb: str, query: str, cfg: Settings, k: int) -> list[Passage]:
    kb_id = cfg.kb_ids.get(kb)
    return _search_bedrock(kb, query, kb_id, cfg, k) if kb_id else _search_local(kb, query, k)


def retrieve_all(query: str, cfg: Settings, k: int = 2) -> Retrieval:
    """Query every KB concurrently, merge, drop duplicates, rank by score."""
    degraded: list[str] = []
    merged: list[Passage] = []
    with ThreadPoolExecutor(max_workers=len(KB_FILES)) as pool:
        futures = {kb: pool.submit(_search, kb, query, cfg, k) for kb in KB_FILES}
        for kb, fut in futures.items():
            try:
                merged += fut.result(timeout=cfg.kb_timeout_s)
            except (FutureTimeout, Exception) as exc:  # noqa: BLE001 - one KB must not fail the job
                log.warning("kb %s degraded: %s", kb, type(exc).__name__)
                degraded.append(kb)
    seen: set[str] = set()
    unique = []
    for p in sorted(merged, key=lambda p: -p.score):
        key = sha256_text(" ".join(p.text.split()).lower())
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return Retrieval(tuple(unique), tuple(degraded))
