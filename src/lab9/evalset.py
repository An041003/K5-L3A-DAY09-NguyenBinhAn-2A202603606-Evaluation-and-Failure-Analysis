"""Build labelled-but-separate, provenance-aware regression/adversarial eval sets."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

ITEMS = Path("data/eval/eval_set_v1.jsonl")
LABELS = Path("data/eval/labels_v1.json")
SOURCE = Path("data/public_claims.jsonl")
VERSION = "v1"
ITEMS_V2 = Path("data/eval/eval_set_v2.jsonl")
LABELS_V2 = Path("data/eval/labels_v2.json")
PACK = Path("data/eval/adversarial_v2.json")
FM_MAP = Path("config/fm_map.yaml")
MIN_PER_MODE_V2 = 3
REQUIRED = ("item_id", "claim_id", "failure_modes", "provenance", "split", "eval_set_version")
FM_CODE = re.compile(r"FM-\d{2}")

# Risk/exposure labels determined from the Lab 8 PUBLIC case matrix, never from a
# model prediction. A clean case still exercises an invariant and needs a tag.
# Raw labels remain exclusively in data/eval/labels_v1.json.
PUBLIC_RISK_MAP: dict[str, list[str]] = {
    "C-001": ["FM-04", "FM-08"],           # standard compensation/reply-amount invariant
    "C-002": ["FM-03"],                    # ticket differs from authoritative order state
    "C-003": ["FM-04"],                    # damage compensation calculation
    "C-004": ["FM-02"],                    # no order / no approved money movement
    "C-005": ["FM-09", "FM-01"],           # unauthorized order + protected PII
    "C-006": ["FM-06"],                    # superseded clause in ticket
    "C-007": ["FM-02"],                    # expired approval
    "C-008": ["FM-08"],                    # capped ledger amount vs quoted amount
    "C-009": ["FM-03"],                    # prompt injection attempting policy override
    "C-010": ["FM-01"],                    # parent/child PII boundary
    "C-011": ["FM-07"],                    # other claim for same order
    "C-012": ["FM-07"],                    # other claim for same order
    "C-013": ["FM-05", "FM-02"],           # already refunded / host policy denial
    "C-014": ["FM-05", "FM-04"],           # prior refund vs current compensation
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha12(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def _write(items: list[dict], labels: dict, path: Path, label_path: Path) -> tuple[int, int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    label_path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items), encoding="utf-8")
    label_path.write_text(json.dumps(labels, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(items), len(labels)


def build(source: Path = SOURCE) -> tuple[int, int]:
    claims = load_jsonl(source)
    items, labels = [], {}
    for n, claim in enumerate(claims, 1):
        claim_id = claim["claim_id"]
        items.append({
            "item_id": f"E-{n:03d}", "claim_id": claim_id,
            "failure_modes": list(PUBLIC_RISK_MAP.get(claim_id, [])),
            "provenance": {
                "source": "lab8_public", "matrix_id": claim.get("matrix_id"),
                "from_trace": None, "generator": None,
                "label_by": "lab8_matrix", "checked_by": "public_case_matrix_review",
            },
            "split": "regression", "eval_set_version": VERSION,
        })
        labels[claim_id] = claim["expected"]
    return _write(items, labels, ITEMS, LABELS)


def slices_for(expected: dict[str, Any], adversarial: bool) -> list[str]:
    tags: list[str] = []
    if (expected.get("refund_vnd") or 0) > 0:
        tags.append("money_movement")
    if expected.get("status") == "denied":
        tags.append("denial")
    if expected.get("status") == "escalated":
        tags.append("escalation")
    if adversarial:
        tags.append("adversarial")
    return tags


def build_v2(items_v1: Path = ITEMS, labels_v1: Path = LABELS, pack: Path = PACK,
             fm_map: Path = FM_MAP) -> tuple[int, int]:
    mapping = yaml.safe_load(fm_map.read_text(encoding="utf-8")) or {}
    base = load_jsonl(items_v1)
    labels = json.loads(labels_v1.read_text(encoding="utf-8"))
    pack_data = json.loads(pack.read_text(encoding="utf-8"))
    items = [{**it, "eval_set_version": "v2", "slices": slices_for(labels[it["claim_id"]], False)} for it in base]
    for claim in pack_data["claims"]:
        items.append({
            "item_id": f"E-{claim['claim_id'][2:]}", "claim_id": claim["claim_id"],
            "failure_modes": [mapping.get(m) or f"UNMAPPED:{m}" for m in claim["mechanisms"]],
            "provenance": {"source": "instructor_adversarial", "matrix_id": None,
                           "from_trace": None, "generator": f"attack:{claim['attack']}",
                           "label_by": "instructor", "checked_by": "fixed_shape_replay"},
            "split": "adversarial", "eval_set_version": "v2",
            "slices": slices_for(claim["expected"], True),
        })
        labels[claim["claim_id"]] = claim["expected"]
    return _write(items, labels, ITEMS_V2, LABELS_V2)


def check(items_path: Path = ITEMS, labels_path: Path = LABELS) -> list[str]:
    problems: list[str] = []
    items = load_jsonl(items_path)
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    for it in items:
        iid = it.get("item_id", "<missing>")
        missing = [k for k in REQUIRED if k not in it]
        if missing:
            problems.append(f"{iid}: missing {missing}")
        if "expected" in it or "label" in it:
            problems.append(f"{iid}: inline label")
        if it.get("claim_id") not in labels:
            problems.append(f"{iid}: no label for {it.get('claim_id')}")
        if not it.get("failure_modes"):
            problems.append(f"{iid}: failure_modes empty")
        for fm in it.get("failure_modes") or []:
            if not FM_CODE.fullmatch(str(fm)):
                problems.append(f"{iid}: invalid failure mode {fm!r}")
        p = it.get("provenance") or {}
        if not isinstance(p, dict) or not p.get("source") or not p.get("label_by"):
            problems.append(f"{iid}: missing provenance source/label_by")
    for key in ("item_id", "claim_id"):
        counts = Counter(i.get(key) for i in items)
        for k, n in counts.items():
            if n > 1:
                problems.append(f"duplicate {key} {k}")
    is_v2 = items_path == ITEMS_V2 or any(it.get("eval_set_version") == "v2" for it in items)
    if is_v2:
        pack_data = json.loads(PACK.read_text(encoding="utf-8"))
        pack_ids = {c["claim_id"] for c in pack_data["claims"]}
        v1_ids = {it["claim_id"] for it in load_jsonl(ITEMS)} if ITEMS.is_file() else set()
        have = {it.get("claim_id") for it in items}
        problems += [f"missing v1 claim {c}" for c in sorted(v1_ids - have)]
        problems += [f"missing adversarial claim {c}" for c in sorted(pack_ids - have)]
        attacked = set()
        counts = Counter()
        for it in items:
            if it.get("eval_set_version") != "v2":
                problems.append(f"{it.get('item_id')}: not v2")
            adv = it.get("claim_id") in pack_ids
            if (it.get("split") == "adversarial") != adv:
                problems.append(f"{it.get('item_id')}: adversarial split inconsistent")
            if not isinstance(it.get("slices"), list):
                problems.append(f"{it.get('item_id')}: missing slice tags")
            counts.update(it.get("failure_modes") or [])
            if adv:
                attacked.update(it.get("failure_modes") or [])
        problems += [f"{fm}: only {counts[fm]} item(s), need >= {MIN_PER_MODE_V2}"
                     for fm in sorted(attacked) if counts[fm] < MIN_PER_MODE_V2]
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lab9.evalset")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--v2", action="store_true")
    args = ap.parse_args(argv)
    if args.v2:
        if args.build:
            print(f"built v2: {build_v2()}")
        problems = check(ITEMS_V2, LABELS_V2)
        for p in problems:
            print("FAIL", p)
        print(f"eval set v2 {sha12(ITEMS_V2)}: {len(problems)} problem(s)")
        return int(bool(problems))
    if args.build:
        print(f"built v1: {build()}")
        if not args.check:
            return 0
    problems = check()
    for p in problems:
        print("FAIL", p)
    print(f"eval set {sha12(ITEMS)}: {len(problems)} problem(s)")
    return int(bool(problems))


if __name__ == "__main__":
    raise SystemExit(main())
