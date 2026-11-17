"""Deterministic integration regressions; uses real Lab 8 MockLLM and ledger.

The team must run these after applying the overlay into its Day 8 repository.
"""
import pytest

pytestmark = pytest.mark.student


def test_ticket_override_detected():
    from lab9.trace_case import investigate
    from lab9.graders import DbFactKept
    from pydantic_evals.evaluators import EvaluatorContext

    broken = investigate("seeded_regression", "C-002", 11)["trial"]
    fixed = investigate("fixed", "C-002", 11)["trial"]
    assert any(e["kind"] == "model_override" for e in broken["events"])
    assert not any(e["kind"] == "model_override" for e in fixed["events"])

    def ctx(trial):
        return EvaluatorContext(name="override", inputs={}, metadata=None,
                                expected_output={}, output=trial, duration=0,
                                _span_tree=None, attributes={}, metrics={})

    assert DbFactKept().evaluate(ctx(broken)).value is False
    assert DbFactKept().evaluate(ctx(fixed)).value is True


def test_reply_amount_matches_committed_ledger():
    from lab8.shapes import SHAPES
    from lab9.variant_agent import make_shape
    from lab9.trace_case import investigate
    from lab9.graders import ReplyLedgerMatch
    from pydantic_evals.evaluators import EvaluatorContext

    SHAPES["lab9_misreport_demo"] = make_shape("lab9_misreport_demo", frozenset({"no_override", "misreport"}))
    good = investigate("fixed", "C-008", 11)["trial"]
    bad = investigate("lab9_misreport_demo", "C-008", 11)["trial"]
    assert good["snapshot"]["refund_vnd"] == bad["snapshot"]["refund_vnd"] == 20000

    def ctx(trial):
        return EvaluatorContext(name="reply_vs_ledger", inputs={}, metadata=None,
                                expected_output={"refund_vnd": 20000}, output=trial, duration=0,
                                _span_tree=None, attributes={}, metrics={})

    assert ReplyLedgerMatch().evaluate(ctx(good)).value is True
    assert ReplyLedgerMatch().evaluate(ctx(bad)).value is False
