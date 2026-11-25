"""Command line: `receipts demo`, `receipts verify`, `receipts migrate`."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .config import Settings
from .models import Receipt
from .pipeline import migrate
from .samples.simulated import EXPECTED, SimulatedAgents, job_source
from .state import DynamoStore, MemoryStore


def _print(result) -> None:
    r = result.receipt
    print(f"\n{r.job:15} -> {r.verdict.value}   receipt {r.receipt_sha256[:16]}")
    for c in r.checks:
        print(f"   {c.status.value:10} {c.name}: {c.detail}")
    for note in r.ledger:
        print(f"   refused    {note}")


def _demo(cfg: Settings) -> int:
    agents, store, bad = SimulatedAgents(), MemoryStore(), 0
    for name, expected in EXPECTED.items():
        res = migrate(name, job_source(name), agents, cfg, store)
        _print(res)
        bad += res.receipt.verdict != expected
    print(f"\n{len(EXPECTED) - bad}/{len(EXPECTED)} verdicts as expected")
    return 1 if bad else 0


def _verify(receipt_path: str, job_path: str) -> int:
    receipt = Receipt.from_dict(json.loads(Path(receipt_path).read_text()))
    ok = receipt.verify(Path(job_path).read_text())
    print("VALID: receipt matches this job and is unmodified" if ok else "INVALID: receipt or job was altered")
    return 0 if ok else 1


def _migrate(job_path: str, out: str | None) -> int:
    from .agents import StrandsAgents
    from .guardrail import make_screen
    cfg = Settings.from_env()
    store = DynamoStore(cfg.table_name, cfg.region) if cfg.table_name else MemoryStore()
    screen = make_screen(cfg.guardrail_id, cfg.guardrail_version, cfg.region) if cfg.guardrail_id else None
    path = Path(job_path)
    res = migrate(path.stem, path.read_text(), StrandsAgents(cfg), cfg, store, screen)
    _print(res)
    print("\nBrief (non-authoritative):", res.brief)
    if out:
        Path(out).write_text(json.dumps(res.receipt.to_dict(), indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="receipts")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo", help="run the 7 sample jobs with simulated agents (no AWS needed)")
    v = sub.add_parser("verify", help="check a receipt against a job file")
    v.add_argument("receipt"); v.add_argument("job")  # noqa: E702
    m = sub.add_parser("migrate", help="migrate a job file with the real agents (needs AWS)")
    m.add_argument("job"); m.add_argument("--out")  # noqa: E702
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s")
    if args.cmd == "demo":
        return _demo(Settings())
    if args.cmd == "verify":
        return _verify(args.receipt, args.job)
    return _migrate(args.job, args.out)


if __name__ == "__main__":
    sys.exit(main())
