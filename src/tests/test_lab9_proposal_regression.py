"""Diagnose the public C-013 pre-deduction failure even when no money is written."""
import pytest

pytestmark = pytest.mark.student


@pytest.mark.parametrize("seed", [11, 22, 33, 44, 55])
def test_pre_deduction_explained_without_false_alarm(seed):
    from lab9.eval import load_spec
    from lab9.graders import GRADERS
    from lab9.trace_case import investigate
    from pydantic_evals.evaluators import EvaluatorContext

    spec = load_spec()
    for shape, want_flag in (("seeded_regression", True), ("fixed", False)):
        case = investigate(shape, "C-013", seed)
        trial, label = case["trial"], case["label"]
        assert trial["snapshot"]["refund_vnd"] == label["refund_vnd"] == 0
        assert trial["lab8_pass"] is (not want_flag)
        assert (trial["result"]["proposal_amount"] != label["proposal_amount"]) is want_flag
        ctx = EvaluatorContext(name=f"C-013@{seed}", inputs={}, metadata=None,
                               expected_output=label, output=trial, duration=0,
                               _span_tree=None, attributes={}, metrics={})
        explained = False
        for metric in spec["metrics"]:
            mid = metric["id"]
            if mid == "pass_rate" or mid not in GRADERS:
                continue
            bad_value = "max" in metric.get("threshold", {})
            explained |= GRADERS[mid]().evaluate(ctx).value is bad_value
        assert explained is want_flag
