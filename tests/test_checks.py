import dataclasses

import pytest

from receipts.checks import citations, parity, refusals, schedule, secrets
from receipts.models import Status, Translation
from receipts.samples.simulated import TRANSLATIONS, job_source


def tr(name="clean_report", **over) -> Translation:
    return dataclasses.replace(Translation.from_dict(TRANSLATIONS[name]), **over)


# schedule ---------------------------------------------------------------
def test_dst_gap_and_overlap_detected():
    assert "skipped" in schedule.dst_issues(2, 30, "America/New_York", 2026)
    assert "repeated" in schedule.dst_issues(1, 30, "America/New_York", 2026)
    assert schedule.dst_issues(2, 30, "UTC", 2026) == set()
    assert schedule.dst_issues(2, 30, "Africa/Addis_Ababa", 2026) == set()


def test_model_cannot_dodge_dst_by_changing_timezone(cfg):
    r = schedule.check(job_source("dst_backup"), tr("dst_backup", tz="UTC"), cfg)
    assert r.status is Status.FAIL


def test_unknown_timezone_needs_info(cfg):
    src = "# schedule: 0 2 * * *\n# tz: Mars/Olympus\necho hi\n"
    assert schedule.check(src, tr(tz="Mars/Olympus"), cfg).status is Status.NEEDS_INFO


# parity -----------------------------------------------------------------
def test_parity_runs_with_scrubbed_environment(cfg, monkeypatch):
    monkeypatch.setenv("RECEIPTS_TEST_SECRET", "leak")
    handler = "import os\nprint(os.environ.get('RECEIPTS_TEST_SECRET', 'none'))\n"
    src = "#!/bin/bash\necho none\n"
    t = tr(handler=handler)
    assert parity.check(src, t, cfg).status is Status.PASS  # would FAIL if the env leaked


def test_parity_timeout_kills_runaway_handler(cfg):
    r = parity.check("#!/bin/bash\necho hi\n", tr(handler="while True: pass\n"), cfg)
    assert r.status is Status.FAIL and "killed" in r.detail


def test_parity_never_echoes_output(cfg):
    r = parity.check('#!/bin/bash\necho hunter2hunter2\n', tr(handler="print('x')\n"), cfg)
    assert r.status is Status.FAIL and "hunter2" not in r.detail


# secrets ----------------------------------------------------------------
@pytest.mark.parametrize("iac", [
    "Action: '*'", 'Action: ["*"]', "Action:\n  - '*'", '"Action": "s3:*"', "Resource: '*'",
])
def test_wildcard_variants_blocked(cfg, iac):
    assert secrets.check("echo hi\n", tr(iac=iac), cfg).status is Status.FAIL


def test_specific_actions_pass(cfg):
    assert secrets.check("echo hi\n", tr(iac="Action:\n  - logs:PutLogEvents\n"), cfg).status is Status.PASS


def test_secret_value_never_in_detail(cfg):
    r = secrets.check(job_source("hidden_secret"), tr("hidden_secret"), cfg)
    assert r.status is Status.FAIL and "hunter2" not in r.detail


def test_aws_key_detected(cfg):
    assert secrets.check("x=AKIAABCDEFGHIJKLMNOP\n", tr(), cfg).status is Status.FAIL


# citations / refusals ---------------------------------------------------
def test_dropped_source_line_fails(cfg):
    assert citations.check(job_source("dropped_step"), tr("dropped_step"), cfg).status is Status.FAIL


def test_unknown_step_listing_covers_a_line(cfg):
    t = tr("dropped_step", unknown=("line 4: rm -f old_output.txt not translated",))
    assert citations.check(job_source("dropped_step"), t, cfg).status is Status.PASS


def test_fabricated_citation_fails(cfg):
    t = tr(steps=(dataclasses.replace(tr().steps[0], text="rm -rf /"),) + tr().steps[1:])
    assert citations.check(job_source("clean_report"), t, cfg).status is Status.FAIL


@pytest.mark.parametrize("name", ["injection", "b64_injection"])
def test_injection_goes_to_ledger(cfg, name):
    r = refusals.check(job_source(name), tr(name), cfg)
    assert r.status is Status.NEEDS_INFO and r.notes


def test_unknown_steps_escalate(cfg):
    assert refusals.check("echo hi\n", tr(unknown=("poll for sentinel",)), cfg).status is Status.NEEDS_INFO
