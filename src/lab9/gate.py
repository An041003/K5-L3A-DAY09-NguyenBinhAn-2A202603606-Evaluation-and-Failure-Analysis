"""Evaluation gate with paired, slice-aware checks and audit-grade report integrity.

Exit 0 means eligible for merge; exit 1 means do not merge. This deliberately
fails closed on corrupted/missing evaluators and relaxed release thresholds.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item, aggregate
from lab9.graders import GRADERS


def _finite(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _spec_index(spec: dict, key: str) -> dict[str, dict]:
    return {str(x["id"] if key == "metrics" else x["name"]): x for x in spec.get(key, [])}


def _threshold_ratchet(new: dict, old: dict, label: str, problems: list[str]) -> None:
    nt, ot = new.get("threshold", {}), old.get("threshold", {})
    # Slices store thresholds at the top level.
    if label.startswith("slice:"):
        nt, ot = new, old
    for key in ("min", "max", "max_increase"):
        if key not in ot:
            continue
        if key not in nt:
            problems.append(f"ratchet {label}: dropped {key} threshold")
            continue
        if not _finite(nt[key]):
            problems.append(f"ratchet {label}: non-numeric {key}")
        elif (key == "min" and nt[key] < ot[key]) or (key != "min" and nt[key] > ot[key]):
            problems.append(f"ratchet {label}: relaxed {key} ({ot[key]} -> {nt[key]})")
    if ot.get("no_significant_drop") and not nt.get("no_significant_drop"):
        problems.append(f"ratchet {label}: removed no_significant_drop")
    if old.get("blocking") and not new.get("blocking"):
        problems.append(f"ratchet {label}: changed blocking to non-blocking")
    if label.startswith("slice:") and old.get("metric") != new.get("metric"):
        problems.append(f"ratchet {label}: changed graded metric")


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    problems: list[str] = []
    pm, bm = pr.get("manifest", {}), base.get("manifest", {})
    pr_rows, base_rows = pr.get("rows"), base.get("rows")
    if not isinstance(pr_rows, list) or not isinstance(base_rows, list):
        return ["rows missing or not lists"]
    if not isinstance(pr.get("metrics"), dict) or not isinstance(base.get("metrics"), dict):
        return ["metrics missing or not objects"]
    for name, report in (("PR", pr), ("baseline", base)):
        failures = report.get("evaluator_failures", [])
        if not isinstance(failures, list):
            problems.append(f"{name}: evaluator_failures must be a list")
        elif failures:
            problems.append(f"{name}: evaluator_failures is non-empty")
        sha = report.get("manifest", {}).get("eval_set_sha")
        if not isinstance(sha, str) or not sha.strip():
            problems.append(f"{name}: missing/invalid eval_set_sha")
    if pm.get("items") != bm.get("items") or pm.get("seeds") != bm.get("seeds"):
        problems.append("manifest item count or seed list differs from baseline")

    def pairs(rows: list, label: str, manifest: dict) -> Counter:
        seen: Counter = Counter()
        for r in rows:
            if not isinstance(r, dict) or not isinstance(r.get("item_id"), str) or type(r.get("seed")) is not int:
                problems.append(f"{label}: malformed row identifier")
                continue
            seen[(r["item_id"], r["seed"])] += 1
        if any(count != 1 for count in seen.values()):
            problems.append(f"{label}: duplicated item/seed row")
        items = manifest.get("items")
        seeds = manifest.get("seeds")
        if (type(items) is not int or items <= 0 or not isinstance(seeds, list)
                or not seeds or any(type(seed) is not int for seed in seeds)
                or len(set(seeds)) != len(seeds)):
            problems.append(f"{label}: invalid manifest items/seeds")
        else:
            if len(rows) != items * len(seeds):
                problems.append(f"{label}: row count {len(rows)} != {items} items × {len(seeds)} seeds")
            if len({key[0] for key in seen}) != items:
                problems.append(f"{label}: distinct item count disagrees with manifest")
            if any(seed not in seeds for _, seed in seen):
                problems.append(f"{label}: row uses a seed outside manifest")
        return seen

    pr_pairs = pairs(pr_rows, "PR", pm)
    base_pairs = pairs(base_rows, "baseline", bm)
    if pr_pairs != base_pairs:
        problems.append("item/seed multiset differs from baseline (dropped/cherry-picked/duplicated)")

    # Slice membership is determined by immutable labels, never relabelled from the output.
    def slice_map(rows: list, label: str) -> dict[str, tuple[str, ...]]:
        by_item: dict[str, tuple[str, ...]] = {}
        for r in rows:
            if not isinstance(r, dict) or not isinstance(r.get("item_id"), str):
                continue
            slices = r.get("slices", [])
            if not isinstance(slices, list) or any(not isinstance(s, str) for s in slices):
                problems.append(f"{label}: malformed slice tags")
                continue
            if len(slices) != len(set(slices)):
                problems.append(f"{label}: duplicate slice tags for {r['item_id']}")
            tags = tuple(sorted(set(slices)))
            if r["item_id"] in by_item and by_item[r["item_id"]] != tags:
                problems.append(f"{label}: inconsistent slice tags across seeds for {r['item_id']}")
            by_item[r["item_id"]] = tags
        return by_item

    if slice_map(pr_rows, "PR") != slice_map(base_rows, "baseline"):
        problems.append("PR item slice tags differ from baseline")

    metric_defs = spec.get("metrics", [])
    if not isinstance(metric_defs, list) or any(not isinstance(m, dict) or "id" not in m for m in metric_defs):
        return problems + ["malformed metric spec"]
    metric_ids = [str(m["id"]) for m in metric_defs]
    if len(set(metric_ids)) != len(metric_ids):
        problems.append("duplicate metric ids in spec")
    slices_spec = spec.get("slices", [])
    if not isinstance(slices_spec, list) or any(not isinstance(s, dict) or "name" not in s for s in slices_spec):
        return problems + ["malformed slice spec"]
    if len({s["name"] for s in slices_spec}) != len(slices_spec):
        problems.append("duplicate slice names in spec")

    # A report is fail-closed only if *all* claimed per-trial grade values are valid.
    # Check the baseline as well: a corrupt baseline must never become the comparator.
    for label, report, rows in (("PR", pr, pr_rows), ("baseline", base, base_rows)):
        for m in metric_defs:
            mid = m["id"]
            val = report["metrics"].get(mid)
            if mid not in report["metrics"] or val is None:
                if m.get("blocking"):
                    problems.append(f"{label}: missing/undefined blocking aggregate {mid}")
            elif not _finite(val):
                problems.append(f"{label}: nonfinite/non-numeric aggregate {mid}")
            if mid in GRADERS:
                for index, r in enumerate(rows):
                    if not isinstance(r, dict) or type(r.get(mid)) is not bool:
                        problems.append(f"{label} row {index}: {mid} missing, None, or not boolean")
                        break
        for mid, value in report["metrics"].items():
            if isinstance(value, float) and not math.isfinite(value):
                problems.append(f"{label}: nonfinite aggregate {mid}")
        # Official eval reports include cost on every row. Public unit fixtures may
        # omit cost entirely; a *partially* populated cost column is corruption.
        has_cost = any(isinstance(r, dict) and "cost" in r for r in rows)
        if has_cost:
            for index, r in enumerate(rows):
                if not isinstance(r, dict) or not _finite(r.get("cost")) or r["cost"] < 0:
                    problems.append(f"{label} row {index}: invalid/missing trial cost")
                    break
        # Recalculate report metrics from raw row booleans. Do not only verify pass_rate:
        # a poisoned report can otherwise submit a bogus pass_hat_5 or zero safety count.
        try:
            if all(isinstance(r, dict) for r in rows):
                if all(all(type(r.get(mid)) is bool for mid in metric_ids if mid in GRADERS) for r in rows):
                    graded_ids = [mid for mid in metric_ids if mid in GRADERS]
                    # aggregate() needs cost; use zero placeholders only when no cost
                    # column exists (synthetic public fixtures omit it).
                    recalc_rows = rows if has_cost else [dict(r, cost=0.0) for r in rows]
                    k_values = sorted({int(key.rsplit("_", 1)[-1])
                                       for key in report["metrics"]
                                       if key.startswith(("pass_at_", "pass_hat_"))
                                       and key.rsplit("_", 1)[-1].isdigit()})
                    expected = aggregate(recalc_rows, graded_ids, k_values=k_values)
                    for metric, actual in report["metrics"].items():
                        if metric not in expected:
                            continue
                        want = expected[metric]
                        # No cost information: cost/success is not verifiable.
                        if metric == "cost_per_success" and not has_cost:
                            continue
                        if want is None or not _finite(actual):
                            continue  # reported missing grades already flagged above
                        if _finite(want) and abs(want - actual) > 0.00011:
                            problems.append(f"{label}: aggregate {metric} disagrees with rows")
        except (ValueError, KeyError, TypeError, ZeroDivisionError, OverflowError):
            problems.append(f"{label}: cannot recompute aggregates from rows")

    # Each manifest's declared spec version should match the corresponding spec
    # when available. Compatibility with the minimal public test fixtures is kept.
    ps_ver = pm.get("metric_spec_version")
    if ps_ver is not None and str(ps_ver) != str(spec.get("metric_spec_version")):
        problems.append("PR report metric_spec_version does not match spec")
    if base_spec is not None:
        bs_ver = bm.get("metric_spec_version")
        if bs_ver is not None and str(bs_ver) != str(base_spec.get("metric_spec_version")):
            problems.append("baseline report metric_spec_version does not match base spec")

    if base_spec is not None and spec.get("eval_set_version") == base_spec.get("eval_set_version"):
        # Immutable run definition: changing data, seed sets, or grading mechanism
        # requires a new evaluation version and a freshly generated baseline.
        for key in ("eval_set", "labels", "adversarial_pack", "seeds", "pass_k"):
            if key in base_spec and spec.get(key) != base_spec.get(key):
                problems.append(f"ratchet: changed {key} without changing eval-set version")
        for key in ("metrics", "slices"):
            old = _spec_index(base_spec, key)
            new = _spec_index(spec, key)
            for name, old_entry in old.items():
                label = f"slice:{name}" if key == "slices" else f"metric:{name}"
                if name not in new:
                    problems.append(f"ratchet {label}: removed from spec")
                else:
                    _threshold_ratchet(new[name], old_entry, label, problems)
                    if key == "metrics":
                        for field in ("grader", "kind", "level"):
                            if field in old_entry and new[name].get(field) != old_entry[field]:
                                problems.append(f"ratchet {label}: changed {field}")
            if key == "slices" and old and not new:
                problems.append("ratchet: all slices removed")
    elif base_spec is not None:
        # New eval-set versions need fresh baselines, not comparisons to an old eval set.
        problems.append("ratchet: eval-set version differs from base spec; create a new baseline")
    return list(dict.fromkeys(problems))



def _per_item_metric(report: dict, metric: str, slice_name: str | None = None) -> dict[str, float]:
    """Support pass^k/pass@k metrics, which exist only in aggregate reports."""
    if not metric.startswith(("pass_hat_", "pass_at_")):
        return per_item(report, metric, slice_name=slice_name)
    try:
        k = int(metric.rsplit("_", 1)[-1])
    except ValueError:
        return {}
    by_item: dict[str, list[bool]] = defaultdict(list)
    for row in report["rows"]:
        if slice_name is not None and slice_name not in (row.get("slices") or []):
            continue
        if type(row.get("pass_rate")) is bool:
            by_item[row["item_id"]].append(row["pass_rate"])
    fn = stats.pass_hat_k if metric.startswith("pass_hat_") else stats.pass_at_k
    return {iid: fn(len(values), sum(values), k) for iid, values in by_item.items() if len(values) >= k}


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    blocked: list[str] = []
    lines: list[str] = []
    bs = spec.get("bootstrap", {})
    for entry in spec.get("slices", []):
        name, mid = entry["name"], entry["metric"]
        label = f"slice:{name}/{mid}"
        a, b = _per_item_metric(pr, mid, slice_name=name), _per_item_metric(base, mid, slice_name=name)
        keys = sorted(set(a) & set(b))
        verdict = "ok"
        note = ""
        if not keys or set(a) != set(b):
            verdict, note = "fail", "slice missing from PR/baseline or item sets differ"
            mean = None
        else:
            mean = sum(a[k] for k in keys) / len(keys)
            if "min" in entry and mean < entry["min"]:
                verdict = "fail"
            if "max" in entry and mean > entry["max"]:
                verdict = "fail"
            if entry.get("no_significant_drop") and len(keys) < 2:
                verdict, note = "fail", "insufficient slice items for paired CI"
            elif entry.get("no_significant_drop"):
                d, lo, hi = stats.paired_bootstrap(
                    [a[k] for k in keys], [b[k] for k in keys],
                    n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027),
                    confidence=bs.get("confidence", 0.95),
                )
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdict = "fail"
        if verdict == "fail" and entry.get("blocking"):
            blocked.append(label)
        lines.append(f"  {label:<34} {str(round(mean, 4)) if mean is not None else 'N/A':<8} "
                     f"floor={entry.get('min', '-')}, {note:<31} "
                     f"{'BLOCK' if verdict == 'fail' and entry.get('blocking') else ('warn' if verdict == 'fail' else 'ok')}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr.get("manifest", {}).get("eval_set_sha") != base.get("manifest", {}).get("eval_set_sha"):
        return ["eval_set_sha"], ["  EVAL SET differs from baseline: regenerate a baseline on this eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked: list[str] = []
    lines: list[str] = []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th = m["id"], m.get("threshold", {})
        val = pr["metrics"].get(mid)
        verdict, note = "ok", ""
        if val is None:
            verdict = "fail"
        elif ("min" in th and val < th["min"]) or ("max" in th and val > th["max"]):
            verdict = "fail"
        elif "max_increase" in th and _finite(base["metrics"].get(mid)):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = _per_item_metric(pr, mid), _per_item_metric(base, mid)
            keys = sorted(set(a) & set(b))
            if not keys or set(a) != set(b):
                verdict, note = "fail", "no paired rows"
            elif len(keys) < 2:
                verdict, note = "fail", "insufficient item pairs for bootstrap"
            else:
                d, lo, hi = stats.paired_bootstrap(
                    [a[k] for k in keys], [b[k] for k in keys],
                    n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027),
                    confidence=bs.get("confidence", 0.95),
                )
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdict = "fail"
        if verdict == "fail" and m.get("blocking"):
            blocked.append(mid)
        lines.append(f"  {mid:<23} {val!s:<8} {json.dumps(th):<45} {note:<28} "
                     f"{'BLOCK' if verdict == 'fail' and m.get('blocking') else ('warn' if verdict == 'fail' else 'ok')}")
    s_blocked, s_lines = slice_check(pr, base, spec)
    return blocked + s_blocked, lines + s_lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    spec = load_spec(Path(args.spec))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, spec, base_spec)
    print(f"gate: PR {pr.get('run_id')} vs main {base.get('run_id')} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
