"""Domain types. Pure data: no I/O, no AWS."""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

SCHEMA_VERSION = 1
MAX_FIELD_CHARS = 100_000
JOB_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


class Status(str, Enum):
    PASS = "PASS"
    NEEDS_INFO = "NEEDS_INFO"
    FAIL = "FAIL"


class Verdict(str, Enum):
    READY = "READY FOR REVIEW"
    NEEDS_INFO = "NEEDS INFO"
    BLOCKED = "BLOCKED"


class TranslationError(ValueError):
    """Model output is not a valid translation. Always results in BLOCKED, never a crash."""


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class Step:
    src_line: int
    text: str


@dataclass(frozen=True)
class Translation:
    """What the model proposes. Untrusted until the gate has checked it."""

    cron: str
    tz: str
    steps: tuple[Step, ...]
    unknown: tuple[str, ...]
    handler: str  # Python source for the migrated job
    iac: str  # CloudFormation text

    @classmethod
    def from_dict(cls, data: Any) -> Translation:
        if not isinstance(data, Mapping):
            raise TranslationError("translation must be a JSON object")
        try:
            sched = data["schedule"]
            steps = tuple(Step(int(s["src_line"]), str(s["text"])) for s in data["steps"])
            unknown = tuple(str(u) for u in data["unknown"])
            cron, tz, handler, iac = sched["cron"], sched["tz"], data["handler"], data["iac"]
        except (KeyError, TypeError, ValueError) as exc:
            raise TranslationError(f"invalid translation: {exc!r}") from exc
        for name, val in (("cron", cron), ("tz", tz), ("handler", handler), ("iac", iac)):
            if not isinstance(val, str) or len(val) > MAX_FIELD_CHARS:
                raise TranslationError(f"field {name!r} must be a string under {MAX_FIELD_CHARS} chars")
        return cls(cron, tz, steps, unknown, handler, iac)

    @classmethod
    def from_text(cls, text: str) -> Translation:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise TranslationError("no JSON object in model output")
        try:
            return cls.from_dict(json.loads(text[start:end + 1]))
        except json.JSONDecodeError as exc:
            raise TranslationError(f"invalid JSON: {exc.msg}") from exc

    def to_dict(self) -> dict[str, Any]:
        return {"schedule": {"cron": self.cron, "tz": self.tz},
                "steps": [{"src_line": s.src_line, "text": s.text} for s in self.steps],
                "unknown": list(self.unknown), "handler": self.handler, "iac": self.iac}


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: Status
    detail: str
    notes: tuple[str, ...] = ()  # entries for the refusal ledger

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "status": self.status.value, "detail": self.detail,
                "notes": list(self.notes)}


@dataclass(frozen=True)
class Receipt:
    """Tamper-evident record of one gate decision."""

    job: str
    verdict: Verdict
    checks: tuple[CheckResult, ...]
    source_sha256: str
    translation: dict[str, Any] | None
    receipt_sha256: str
    schema_version: int = SCHEMA_VERSION

    @property
    def ledger(self) -> tuple[str, ...]:
        return tuple(n for c in self.checks for n in c.notes)

    @staticmethod
    def _digest(job: str, verdict: Verdict, checks: tuple[CheckResult, ...],
                source_sha: str, translation: dict[str, Any] | None) -> str:
        body = {"schema_version": SCHEMA_VERSION, "job": job, "verdict": verdict.value,
                "checks": [c.to_dict() for c in checks], "source_sha256": source_sha,
                "translation": translation}
        return sha256_text(canonical(body))

    @classmethod
    def build(cls, job: str, verdict: Verdict, checks: tuple[CheckResult, ...], source: str,
              translation: dict[str, Any] | None) -> Receipt:
        src = sha256_text(source)
        return cls(job, verdict, checks, src, translation,
                   cls._digest(job, verdict, checks, src, translation))

    def verify(self, source: str) -> bool:
        """True only if the receipt is unmodified and was issued for exactly this source."""
        return (self.source_sha256 == sha256_text(source) and self.receipt_sha256 ==
                self._digest(self.job, self.verdict, self.checks, self.source_sha256, self.translation))

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "job": self.job, "verdict": self.verdict.value,
                "checks": [c.to_dict() for c in self.checks], "source_sha256": self.source_sha256,
                "translation": self.translation, "receipt_sha256": self.receipt_sha256}

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Receipt:
        checks = tuple(CheckResult(c["name"], Status(c["status"]), c["detail"], tuple(c["notes"]))
                       for c in d["checks"])
        return cls(d["job"], Verdict(d["verdict"]), checks, d["source_sha256"], d["translation"],
                   d["receipt_sha256"], d.get("schema_version", SCHEMA_VERSION))
