"""The five deterministic checks. Every check has the same signature and returns a CheckResult."""
from __future__ import annotations

from collections.abc import Callable

from ..config import Settings
from ..models import CheckResult, Translation
from . import citations, parity, refusals, schedule, secrets

Check = Callable[[str, Translation, Settings], CheckResult]

REGISTRY: tuple[tuple[str, Check], ...] = (
    ("schedule", schedule.check),
    ("parity", parity.check),
    ("secrets", secrets.check),
    ("citations", citations.check),
    ("refusals", refusals.check),
)
