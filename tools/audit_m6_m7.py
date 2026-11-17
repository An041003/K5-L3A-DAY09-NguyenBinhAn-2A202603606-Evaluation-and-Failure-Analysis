#!/usr/bin/env python3
"""Independent M6–M7 audit over *actual* Day9 JSON reports (never edits reports).

Run after the official lab9.eval commands have produced baseline_v2.json and the
fixed/honest_refactor/flaky_regression reports. The controlled synthetic M6
unit fixture lives separately in tests/test_lab9_m6_m7_hardening.py.

    python tools/audit_m6_m7.py --repo . --write

The script never changes the official lab9.traps/variants files, any eval data,
metric thresholds, or source Lab8. `--write` writes a markdown commentary only.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, default=Path('.'), help='Path of personal Day9 repo')
    parser.add_argument('--write', action='store_true', help='Write docs/m6_m7_evidence.md')
    args = parser.parse_args()
    root = args.repo.expanduser().resolve()
    src = root / 'src'
    if not (src / 'lab9/gate.py').exists():
        print(f'ERROR: expected repo/src/lab9/gate.py under {root}', file=sys.stderr)
        return 2
    sys.path.insert(0, str(src))
    from lab9 import gate
    from lab9.eval import load_spec

    spec_path = src / 'config/metric_spec_v2.yaml'
    try:
        spec = load_spec(spec_path)
        def read(name: str):
            return json.loads((src / 'reports' / name).read_text(encoding='utf-8'))
        baseline = read('baseline_v2.json')
        flaky = read('eval_flaky_regression.json')
        fixed = read('eval_fixed_v2.json')
        honest = read('eval_honest_refactor_v2.json')
    except (OSError, ValueError, KeyError) as error:
        print(f'ERROR: missing real reports/spec: {error}', file=sys.stderr)
        print('Run the official baseline, fixed, honest_refactor and flaky eval commands first.', file=sys.stderr)
        return 2

    report_rows = [
        ('baseline_against_itself', baseline, False),
        ('fixed', fixed, False),
        ('honest_refactor', honest, False),
        ('flaky_regression', flaky, True),
    ]
    verdicts = []
    errors = []
    for name, report, should_block in report_rows:
        blocked, _ = gate.check(report, baseline, spec)
        verdicts.append((name, 'BLOCK' if blocked else 'MERGE', ', '.join(blocked) or '(none)'))
        if bool(blocked) != should_block:
            errors.append(f'{name}: incorrect release decision: {blocked}')

    # Pure per-metric ablation: leave every threshold unchanged; change only
    # *which* metric may block inside this temporary, in-memory spec copy.
    only_hat = copy.deepcopy(spec)
    for metric in only_hat.get('metrics', []):
        metric['blocking'] = metric['id'] == 'pass_hat_5'
    for slice_spec in only_hat.get('slices', []):
        slice_spec['blocking'] = False
    blocked_hat, _ = gate.check(flaky, baseline, only_hat)
    if 'pass_hat_5' not in blocked_hat:
        errors.append('M6: pass_hat_5 alone did not block actual flaky regression')
    # Do not mistake the isolated ablation for a legitimate release config.
    # It is never serialized and must never be committed as metric_spec_v2.

    m6_metrics = [(key, baseline['metrics'].get(key), flaky['metrics'].get(key))
                  for key in ('pass_rate', 'pass_hat_5', 'pass_5')]

    # M7: adversarial report-integrity probes based on the *actual* baseline.
    # Mutation is in-memory only; the saved baseline_v2.json remains untouched.
    tests = {}
    def probe(name, mutate_report=None, mutate_spec=None):
        rep = copy.deepcopy(baseline)
        altered = copy.deepcopy(spec)
        if mutate_report:
            mutate_report(rep)
        if mutate_spec:
            mutate_spec(altered)
        base_spec = spec if mutate_spec else None
        blocked, lines = gate.check(rep, baseline, altered, base_spec)
        detected = 'integrity' in blocked
        tests[name] = (detected, '; '.join(line for line in lines if 'INTEGRITY' in line)[:190])
        if not detected:
            errors.append(f'M7: {name} not stopped by INTEGRITY (blocked={blocked})')

    probe('evaluator_failures', lambda r: r.__setitem__('evaluator_failures', ['forced grader crash']))
    probe('none_grade', lambda r: r['rows'][0].__setitem__('pass_rate', None))
    probe('duplicate_item_seed', lambda r: r['rows'].__setitem__(-1, copy.deepcopy(r['rows'][0])))
    probe('missing_row', lambda r: r['rows'].pop())
    probe('nan_metric', lambda r: r['metrics'].__setitem__('pass_rate', float('nan')))
    probe('inf_cost', lambda r: r['rows'][0].__setitem__('cost', float('inf')))
    probe('aggregate_forgery', lambda r: r['metrics'].__setitem__('pass_hat_5', 0.01))
    probe('seed_cherry_pick', lambda r: r['manifest'].__setitem__('seeds', [11, 22, 33, 44]))
    probe('slice_relabel', lambda r: r['rows'][0].__setitem__('slices', ['tampered_tag']))
    def relax_hat(s):
        for m in s['metrics']:
            if m['id'] == 'pass_hat_5':
                m['threshold']['min'] = .10
                break
    probe('ratchet_hat_threshold', mutate_spec=relax_hat)
    probe('ratchet_drop_slices', mutate_spec=lambda s: s.__setitem__('slices', []))
    def swap_grader(s):
        for m in s['metrics']:
            if m['id'] == 'pass_rate':
                m['grader'] = 'untrusted_judge'
                break
    probe('ratchet_grader_swap', mutate_spec=swap_grader)

    markdown = [
        '# M6–M7 additional audit — real Day 9 reports',
        '',
        '> Generated from existing evaluator reports by `tools/audit_m6_m7.py`. '
        'No report, label, metric floor, instructor variant, or trap was edited.',
        '',
        f'- Eval set SHA: `{baseline["manifest"].get("eval_set_sha")}`',
        f'- Metric spec version: `{spec.get("metric_spec_version")}`',
        '',
        '## M6 — Actual results and metric-isolation ablation',
        '',
        '| Metric | Baseline v2 | Flaky regression |',
        '|---|---:|---:|',
    ]
    for key, a, b in m6_metrics:
        markdown.append(f'| `{key}` | {a} | {b} |')
    markdown += [
        '',
        '| Actual variant | Gate result | Blocking reasons |',
        '|---|---|---|',
    ]
    markdown += [f'| `{name}` | {decision} | {why} |' for name, decision, why in verdicts]
    markdown += [
        '',
        f'- **Pass-hat-only ablation (in memory):** {"BLOCK" if blocked_hat else "MERGE"}; '
        f'blocking reasons: {", ".join(blocked_hat) or "(none)"}.',
        '- **Interpretation:** the observed flaky variant may also be blocked by '
        '`pass_rate` or a slice. This ablation shows `pass_hat_5` *independently* '
        'detects it. Do not claim it is the only blocking metric.',
        '- **Mathematical separation:** see the marked unit fixture in '
        '`src/tests/test_lab9_m6_m7_hardening.py`: identical 90% pass rate, '
        'but pass_hat_5 falls from 90% to 50%. This is not an observed agent run.',
        '',
        '## M7 — Extra in-memory integrity probes',
        '',
        '| Probe | Integrity rejected? | Evidence |',
        '|---|---|---|',
    ]
    markdown += [f'| `{name}` | {"YES" if detected else "NO"} | {why} |'
                 for name, (detected, why) in tests.items()]
    markdown += [
        '',
        'This audit is **not** the instructor hidden grade. Run the public `lab9.traps` '
        'and `lab9.mutation` CLI separately, attach their logs in the PR.',
        '',
        f'**Status: {"PASS" if not errors else "NEEDS FIX"}; {len(tests)} / {len(tests)} '
        'probes rejected**' if not errors else f'**Status: NEEDS FIX ({len(errors)} errors)**',
    ]
    print('\n'.join(markdown))
    if errors:
        print('ISSUES:', '\n'.join(errors), file=sys.stderr)
        return 1
    if args.write:
        path = root / 'docs/m6_m7_evidence.md'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('\n'.join(markdown) + '\n', encoding='utf-8')
        print('WROTE', path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
