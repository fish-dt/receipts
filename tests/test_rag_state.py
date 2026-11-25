import threading

import pytest

from receipts import rag
from receipts.state import ConflictError, MemoryStore, verify_chain


def test_parallel_rag_finds_dst_rule(cfg):
    r = rag.retrieve_all("schedule 02:30 America/New_York daylight saving", cfg)
    assert any("ST-1" in p.text for p in r.passages) and not r.degraded


def test_rag_degrades_when_one_kb_fails(cfg, monkeypatch):
    real = rag._search_local

    def flaky(kb, query, k):
        if kb == "schedule":
            raise TimeoutError
        return real(kb, query, k)
    monkeypatch.setattr(rag, "_search_local", flaky)
    r = rag.retrieve_all("exit code swallowed failures", cfg)
    assert r.degraded == ("schedule",) and r.passages


def test_stale_write_conflicts():
    s = MemoryStore(); s.create("j")  # noqa: E702
    v = s.append("j", {"step": "a"}, 1)
    with pytest.raises(ConflictError):
        s.append("j", {"step": "stale"}, 1)
    assert s.append("j", {"step": "b"}, v) == 3


def test_concurrent_writers_exactly_one_wins():
    s = MemoryStore(); s.create("j")  # noqa: E702
    wins, errors = [], []

    def writer(i):
        try:
            wins.append(s.append("j", {"w": i}, 1))
        except ConflictError:
            errors.append(i)
    ts = [threading.Thread(target=writer, args=(i,)) for i in range(8)]
    [t.start() for t in ts]; [t.join() for t in ts]  # noqa: E702
    assert len(wins) == 1 and len(errors) == 7


def test_hash_chain_detects_edits():
    s = MemoryStore(); s.create("j")  # noqa: E702
    v = s.append("j", {"a": 1}, 1); s.append("j", {"b": 2}, v)  # noqa: E702
    events = s.get("j")["events"]
    assert verify_chain(events)
    events[0]["a"] = 99
    assert not verify_chain(events)
