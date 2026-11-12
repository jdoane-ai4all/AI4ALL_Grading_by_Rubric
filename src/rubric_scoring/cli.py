"""Command-line entry point. Run `python -m rubric_scoring.cli --help`."""
from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path

from . import analysis, data, scorer, simulate, split
from .inputs import read_manifest
from .prompts import PROMPT_VERSION, prompt_hash


def cmd_prepare(a, cfg):
    rows = data.load_labels(a.labels_csv, cfg, source=a.source)
    data.write_label_table(rows, "data/private/labels.csv")
    flow = data.eligibility_flow(rows)
    flow["score_distribution_eligible"] = data.score_distribution(rows)
    Path("outputs").mkdir(exist_ok=True)
    Path("outputs/eligibility_flow.json").write_text(json.dumps(flow, indent=2))
    print(json.dumps(flow, indent=2))


def cmd_split(a, cfg):
    rows = data.load_labels(a.labels_csv, cfg, source=a.source)
    reg = split.build_registry(rows, cfg)
    split.write_registry(reg, "registry/split_registry.json")
    print(json.dumps(reg["stratum_counts"], indent=2), "\nsha256", reg["assignment_sha256"])


def cmd_score(a, cfg):
    reg = json.loads(Path("registry/split_registry.json").read_text())
    arts = [x for x in read_manifest(a.manifest) if reg["project_split"].get(x.project_id) in a.splits]
    random.Random(a.order_seed).shuffle(arts)
    if a.limit:
        arts = arts[: a.limit]
    rid = scorer.run_condition(arts, a.condition, cfg, a.log, a.replicates, a.dry_run)
    print("run_id", rid, "artifacts", len(arts))


def cmd_predictions(a, cfg):
    rows = scorer.predictions_table(a.log)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=sorted({k for r in rows for k in r}))
        w.writeheader()
        w.writerows(rows)
    print(len(rows), "rows ->", a.out)


def _read_preds(path):
    out = []
    for r in csv.DictReader(open(path)):
        r["replicate"] = int(r["replicate"])
        r["score"] = int(r["score"]) if r["score"] not in ("", "None") else None
        out.append(r)
    return out


def cmd_analyse(a, cfg):
    labels = data.read_label_table("data/private/labels.csv")
    reg = json.loads(Path("registry/split_registry.json").read_text())
    res = analysis.analyse(_read_preds(a.predictions), labels, reg, cfg, a.split)
    Path("outputs").mkdir(exist_ok=True)
    Path(f"outputs/results_{a.split}.json").write_text(json.dumps(res, indent=2))
    analysis.write_markdown(res, f"outputs/results_{a.split}.md")
    print(f"wrote outputs/results_{a.split}.json/.md")


def cmd_unlock(a, cfg):
    frozen = {"prompt_version": PROMPT_VERSION,
              "prompt_hashes": {c: prompt_hash(v["prompt"], v["organisation"], "citations")
                                for c, v in cfg["scoring"]["conditions"].items()},
              "review_policy": cfg["review_policy"], "tolerances": cfg["metrics"]["tolerances_for_supporting_review"]}
    analysis.unlock_test(a.who, frozen)
    print("test split unlocked; frozen settings recorded in data/TEST_UNLOCKED")


def cmd_simulate(a, cfg):
    md = simulate.render_markdown(simulate.precision_table(reps=a.reps))
    Path("docs/SIMULATED_PRECISION.md").write_text(md)
    print(md)


def main(argv=None):
    p = argparse.ArgumentParser(prog="rubric_scoring")
    p.add_argument("--config", default="config/study_config.json")
    p.add_argument("--source", default="label_source", help="label_source or label_source_safe_index")
    sp = p.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("prepare"); s.add_argument("labels_csv"); s.set_defaults(f=cmd_prepare)
    s = sp.add_parser("split"); s.add_argument("labels_csv"); s.set_defaults(f=cmd_split)
    s = sp.add_parser("score"); s.add_argument("manifest"); s.add_argument("--condition", required=True)
    s.add_argument("--splits", nargs="+", default=["development"]); s.add_argument("--replicates", type=int, default=1)
    s.add_argument("--log", default="runs/run_log.jsonl"); s.add_argument("--limit", type=int)
    s.add_argument("--order-seed", type=int, default=1); s.add_argument("--dry-run", action="store_true")
    s.set_defaults(f=cmd_score)
    s = sp.add_parser("predictions"); s.add_argument("--log", default="runs/run_log.jsonl")
    s.add_argument("--out", default="runs/predictions.csv"); s.set_defaults(f=cmd_predictions)
    s = sp.add_parser("analyse"); s.add_argument("--predictions", default="runs/predictions.csv")
    s.add_argument("--split", default="development", choices=["development", "test"]); s.set_defaults(f=cmd_analyse)
    s = sp.add_parser("unlock-test"); s.add_argument("--who", required=True); s.set_defaults(f=cmd_unlock)
    s = sp.add_parser("simulate"); s.add_argument("--reps", type=int, default=2000); s.set_defaults(f=cmd_simulate)
    a = p.parse_args(argv)
    a.f(a, data.load_config(a.config))


if __name__ == "__main__":
    main()
