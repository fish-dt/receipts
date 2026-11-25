from receipts.models import Verdict
from receipts.pipeline import migrate
from receipts.samples.simulated import EXPECTED, SimulatedAgents, job_source
from receipts.state import MemoryStore, verify_chain


def test_all_samples_end_to_end(cfg, agents):
    for name, verdict in EXPECTED.items():
        assert migrate(name, job_source(name), agents, cfg, MemoryStore()).receipt.verdict is verdict


def test_state_is_recorded_and_chained(cfg, agents):
    store = MemoryStore()
    res = migrate("clean_report", job_source("clean_report"), agents, cfg, store)
    item = next(iter(store._items.values()))
    assert [e["step"] for e in item["events"]][-1] == "gate" and verify_chain(item["events"])
    assert item["events"][-1]["receipt_sha256"] == res.receipt.receipt_sha256


def test_malformed_output_is_retried_once_then_recovers(cfg):
    a = SimulatedAgents(overrides={"clean_report": "sorry, no JSON"})
    res = migrate("clean_report", job_source("clean_report"), a, cfg)
    assert a.translate_calls == 2 and res.receipt.verdict is Verdict.READY


def test_persistently_malformed_output_is_blocked(cfg):
    class Bad(SimulatedAgents):
        def translate(self, *a, **k):
            return "nope"
    res = migrate("clean_report", job_source("clean_report"), Bad(), cfg)
    assert res.receipt.verdict is Verdict.BLOCKED


def test_guardrail_intervention_blocks_before_any_model_call(cfg, agents):
    res = migrate("injection", job_source("injection"), agents, cfg, screen=lambda text: False)
    assert res.receipt.verdict is Verdict.BLOCKED and agents.translate_calls == 0


def test_guardrail_outage_fails_closed(cfg, agents):
    def down(text):
        raise ConnectionError
    assert migrate("clean_report", job_source("clean_report"), agents, cfg, screen=down).receipt.verdict is Verdict.BLOCKED


def test_oversized_job_blocked(cfg, agents):
    res = migrate("big", "echo hi\n" * 20_000, agents, cfg)
    assert res.receipt.verdict is Verdict.BLOCKED and agents.translate_calls == 0
