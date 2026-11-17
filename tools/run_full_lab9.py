"""Run the entire public Lab 9 workflow after setup_lab9.py has been applied.

No code, labels, metrics or reports are edited to make a failing run green.
Reports are created by `python -m lab9.eval`; gate exit 1 is expected only for regressions.
Usage: python run_full_lab9.py --lab8 C:/path/to/LAB8-REPO
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--lab8", required=True)
    args = ap.parse_args()
    src = Path(args.lab8).expanduser().resolve() / "src"
    if not (src / "lab9/eval.py").exists():
        print("First run setup_lab9.py to add the official starter + patches")
        return 2
    env = dict(os.environ, PYTHONUTF8="1")
    stages = [
        ("smoke", ["-m", "lab9.smoke"], 0),
        ("eval set v1", ["-m", "lab9.evalset", "--build", "--check"], 0),
        ("judge tone", ["-m", "lab9.judge", "--csv", "data/eval/judge_tone_public.csv", "--audit", "5"], 0),
        ("judge helpful REJECT", ["-m", "lab9.judge", "--csv", "data/eval/judge_helpful_public.csv", "--audit", "5"], 1),
        ("unit tests (core + advanced)", ["-m", "pytest", "-q", "-m", "student", "-o", "addopts=", "-k", "lab9"], 0),
        ("baseline v1", ["-m", "lab9.eval", "--shape", "swarm", "--out", "reports/baseline_v1.json"], 0),
        ("fixed v1", ["-m", "lab9.eval", "--shape", "fixed"], 0),
        ("gate fixed v1", ["-m", "lab9.gate", "--pr", "reports/eval_fixed.json", "--baseline", "reports/baseline_v1.json"], 0),
        ("seeded regression v1", ["-m", "lab9.eval", "--shape", "seeded_regression"], 0),
        ("gate regression v1", ["-m", "lab9.gate", "--pr", "reports/eval_seeded_regression.json", "--baseline", "reports/baseline_v1.json"], 1),
        ("grader detection", ["-m", "lab9.mutation", "--detect"], 0),
        ("eval set v2", ["-m", "lab9.evalset", "--v2", "--build"], 0),
        ("baseline v2", ["-m", "lab9.eval", "--shape", "swarm", "--spec", "config/metric_spec_v2.yaml", "--out", "reports/baseline_v2.json"], 0),
        ("fixed v2", ["-m", "lab9.eval", "--shape", "fixed", "--spec", "config/metric_spec_v2.yaml", "--out", "reports/eval_fixed_v2.json"], 0),
        ("honest refactor v2", ["-m", "lab9.eval", "--shape", "honest_refactor", "--spec", "config/metric_spec_v2.yaml", "--out", "reports/eval_honest_refactor_v2.json"], 0),
        ("seeded regression v2", ["-m", "lab9.eval", "--shape", "seeded_regression", "--spec", "config/metric_spec_v2.yaml", "--out", "reports/eval_seeded_regression_v2.json"], 0),
        ("A/A", ["-m", "lab9.mutation", "--spec", "config/metric_spec_v2.yaml", "--aa", "66,77,88,99,110"], 0),
        ("mutation scorecard", ["-m", "lab9.mutation", "--spec", "config/metric_spec_v2.yaml", "--baseline", "reports/baseline_v2.json"], 0),
        ("slice regression v2", ["-m", "lab9.eval", "--shape", "slice_regression", "--spec", "config/metric_spec_v2.yaml"], 0),
        ("gate slice regression v2", ["-m", "lab9.gate", "--pr", "reports/eval_slice_regression.json", "--baseline", "reports/baseline_v2.json", "--spec", "config/metric_spec_v2.yaml"], 1),
        ("flaky regression v2", ["-m", "lab9.eval", "--shape", "flaky_regression", "--spec", "config/metric_spec_v2.yaml"], 0),
        ("gate flaky regression v2", ["-m", "lab9.gate", "--pr", "reports/eval_flaky_regression.json", "--baseline", "reports/baseline_v2.json", "--spec", "config/metric_spec_v2.yaml"], 1),
        ("trap scorecard", ["-m", "lab9.traps", "--pr", "reports/eval_slice_regression.json", "--baseline", "reports/baseline_v2.json", "--spec", "config/metric_spec_v2.yaml"], 0),
        ("write documented results", ["-m", "lab9.finalize", "--write"], 0),
    ]
    failures = []
    log = []
    for i, (title, argv, want) in enumerate(stages, 1):
        print(f"\n[{i}/{len(stages)}] {title}", flush=True)
        result = subprocess.run([sys.executable, *argv], cwd=src, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace")
        print(result.stdout[-13000:], flush=True)
        log.append(f"\n===== {title} | exit {result.returncode}, expected {want} =====\n{result.stdout}")
        if result.returncode != want:
            failures.append(f"{title}: got exit {result.returncode}, expected {want}")
        if title == "gate regression v1" and "pass_rate" not in result.stdout:
            failures.append("gate regression v1: pass_rate not in failure reasons")
    out = src / "reports/lab9_execution.log"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(log), encoding="utf-8")
    print(f"\nSaved observed console transcript: {out}")
    for failure in failures:
        print("FAILED:", failure)
    print("PUBLIC WORKFLOW:", "PASS" if not failures else f"INCOMPLETE ({len(failures)} stage errors)")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
