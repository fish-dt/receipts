"""Runtime settings, read once from the environment. No other module reads os.environ."""
from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

PACKAGE_DIR = Path(__file__).parent


@dataclass(frozen=True)
class Settings:
    region: str = "us-east-1"
    small_model: str = "amazon.nova-lite-v1:0"  # verify model ids / inference profiles for your region
    large_model: str = "amazon.nova-pro-v1:0"
    kb_ids: Mapping[str, str] = field(default_factory=dict)  # {"schedule": "KBID", ...}; empty = local files
    guardrail_id: str = ""
    guardrail_version: str = ""
    table_name: str = ""  # empty = in-memory state
    fixture_dir: Path = PACKAGE_DIR / "samples" / "fixture"
    parity_timeout_s: float = 5.0
    kb_timeout_s: float = 10.0
    max_source_bytes: int = 64_000

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        e = os.environ if env is None else env
        kb = {k: e[f"RECEIPTS_KB_{k.upper()}"] for k in ("schedule", "security", "mapping")
              if e.get(f"RECEIPTS_KB_{k.upper()}")}
        d = cls()
        return cls(
            region=e.get("AWS_REGION", d.region),
            small_model=e.get("RECEIPTS_SMALL_MODEL", d.small_model),
            large_model=e.get("RECEIPTS_LARGE_MODEL", d.large_model),
            kb_ids=kb,
            guardrail_id=e.get("RECEIPTS_GUARDRAIL_ID", ""),
            guardrail_version=e.get("RECEIPTS_GUARDRAIL_VERSION", ""),
            table_name=e.get("RECEIPTS_TABLE", ""),
            fixture_dir=Path(e.get("RECEIPTS_FIXTURE_DIR", str(d.fixture_dir))),
            parity_timeout_s=float(e.get("RECEIPTS_PARITY_TIMEOUT", d.parity_timeout_s)),
        )
