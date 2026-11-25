import pytest

from receipts.gate import evaluate
from receipts.models import Translation, TranslationError, Verdict
from receipts.samples.simulated import TRANSLATIONS, job_source


def test_rejects_missing_fields():
    with pytest.raises(TranslationError):
        Translation.from_dict({"schedule": {}})


def test_rejects_non_object_and_bad_json():
    with pytest.raises(TranslationError):
        Translation.from_text("no json here")
    with pytest.raises(TranslationError):
        Translation.from_text("{not json}")


def test_job_name_cannot_traverse_paths(cfg):
    with pytest.raises(ValueError):
        evaluate("../../etc/passwd", "x", TRANSLATIONS["clean_report"], cfg)


def test_malformed_model_output_is_blocked_not_a_crash(cfg):
    r = evaluate("clean_report", job_source("clean_report"), "I'm sorry, I can't do that", cfg)
    assert r.verdict is Verdict.BLOCKED and r.checks[0].name == "schema"
