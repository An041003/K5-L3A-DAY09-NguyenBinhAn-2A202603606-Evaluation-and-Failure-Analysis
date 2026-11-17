# M6–M7 additional audit — real Day 9 reports

> Generated from existing evaluator reports by `tools/audit_m6_m7.py`. No report, label, metric floor, instructor variant, or trap was edited.

- Eval set SHA: `c642efa1c5b7`
- Metric spec version: `2.2`

## M6 — Actual results and metric-isolation ablation

| Metric | Baseline v2 | Flaky regression |
|---|---:|---:|
| `pass_rate` | 0.9786 | 0.9143 |
| `pass_hat_5` | 0.8929 | 0.5714 |
| `pass_5` | 0.8929 | 0.5714 |

| Actual variant | Gate result | Blocking reasons |
|---|---|---|
| `baseline_against_itself` | MERGE | (none) |
| `fixed` | MERGE | (none) |
| `honest_refactor` | MERGE | (none) |
| `flaky_regression` | BLOCK | pass_rate, pass_hat_5, slice:money_movement/pass_rate, slice:adversarial/pass_rate |

- **Pass-hat-only ablation (in memory):** BLOCK; blocking reasons: pass_hat_5.
- **Interpretation:** the observed flaky variant may also be blocked by `pass_rate` or a slice. This ablation shows `pass_hat_5` *independently* detects it. Do not claim it is the only blocking metric.
- **Mathematical separation:** see the marked unit fixture in `src/tests/test_lab9_m6_m7_hardening.py`: identical 90% pass rate, but pass_hat_5 falls from 90% to 50%. This is not an observed agent run.

## M7 — Extra in-memory integrity probes

| Probe | Integrity rejected? | Evidence |
|---|---|---|
| `evaluator_failures` | YES |   INTEGRITY PR: evaluator_failures is non-empty |
| `none_grade` | YES |   INTEGRITY PR row 0: pass_rate missing, None, or not boolean |
| `duplicate_item_seed` | YES |   INTEGRITY PR: duplicated item/seed row;   INTEGRITY item/seed multiset differs from baseline (dropped/cherry-picked/duplicated);   INTEGRITY PR: aggregate cost_per_success disagrees with r |
| `missing_row` | YES |   INTEGRITY PR: row count 139 != 28 items × 5 seeds;   INTEGRITY item/seed multiset differs from baseline (dropped/cherry-picked/duplicated);   INTEGRITY PR: aggregate proposal_amount_correc |
| `nan_metric` | YES |   INTEGRITY PR: nonfinite/non-numeric aggregate pass_rate;   INTEGRITY PR: nonfinite aggregate pass_rate |
| `inf_cost` | YES |   INTEGRITY PR row 0: invalid/missing trial cost |
| `aggregate_forgery` | YES |   INTEGRITY PR: aggregate pass_hat_5 disagrees with rows |
| `seed_cherry_pick` | YES |   INTEGRITY manifest item count or seed list differs from baseline;   INTEGRITY PR: row count 140 != 28 items × 4 seeds;   INTEGRITY PR: row uses a seed outside manifest |
| `slice_relabel` | YES |   INTEGRITY PR: inconsistent slice tags across seeds for E-001 |
| `ratchet_hat_threshold` | YES |   INTEGRITY ratchet metric:pass_hat_5: relaxed min (0.8 -> 0.1) |
| `ratchet_drop_slices` | YES |   INTEGRITY ratchet slice:denial: removed from spec;   INTEGRITY ratchet slice:money_movement: removed from spec;   INTEGRITY ratchet slice:adversarial: removed from spec;   INTEGRITY ratche |
| `ratchet_grader_swap` | YES |   INTEGRITY ratchet metric:pass_rate: changed grader |

This audit is **not** the instructor hidden grade. Run the public `lab9.traps` and `lab9.mutation` CLI separately, attach their logs in the PR.

**Status: PASS; 12 / 12 probes rejected**
