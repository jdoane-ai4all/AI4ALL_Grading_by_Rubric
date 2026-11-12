"""Portable calibration layers: rubric-literal AI score -> local (organisation-specific) score.

Idea: keep one rubric-literal scorer that any organisation can use, and learn a
small, inspectable, per-criterion 'leniency layer' from a few locally graded
examples. Pre-registered methods (fitted on DEVELOPMENT data only):

  B1  additive shift   calibrated = clip(round(ai + delta_c), 1, 5),
                       delta_c = mean(human - ai) over development pairs.
  B2  monotone table   for each AI level k, the median human score among
                       development pairs with AI = k; made non-decreasing in k
                       (pool-adjacent-violators); unseen levels fall back to B1.

Abstentions stay abstentions: calibration never invents a score.
"""
from __future__ import annotations

import random
from statistics import median

from .rubric import CRITERIA


def _clip(x: float) -> int:
    return int(min(5, max(1, round(x))))


def fit_shift(pairs: dict[str, list[tuple[int, int]]]) -> dict[str, float]:
    """pairs[criterion] = [(ai, human), ...] -> delta per criterion."""
    return {c: (sum(h - a for a, h in ps) / len(ps) if ps else 0.0) for c, ps in pairs.items()}


def _pava(vals: list[float], weights: list[int]) -> list[float]:
    """Pool-adjacent-violators for a non-decreasing fit."""
    blocks = [[v, w, 1] for v, w in zip(vals, weights)]
    i = 0
    while i < len(blocks) - 1:
        if blocks[i][0] > blocks[i + 1][0]:
            v1, w1, n1 = blocks[i]
            v2, w2, n2 = blocks[i + 1]
            blocks[i] = [(v1 * w1 + v2 * w2) / (w1 + w2), w1 + w2, n1 + n2]
            del blocks[i + 1]
            i = max(i - 1, 0)
        else:
            i += 1
    out = []
    for v, _, n in blocks:
        out += [v] * n
    return out


def fit_table(pairs: dict[str, list[tuple[int, int]]]) -> dict[str, dict[int, int]]:
    shift = fit_shift(pairs)
    tables = {}
    for c, ps in pairs.items():
        seen = sorted({a for a, _ in ps})
        meds = [median([h for a, h in ps if a == k]) for k in seen]
        wts = [sum(1 for a, _ in ps if a == k) for k in seen]
        mono = _pava(meds, wts) if seen else []
        t = {k: _clip(m) for k, m in zip(seen, mono)}
        for k in range(1, 6):
            if k not in t:
                t[k] = _clip(k + shift[c])
        # enforce monotone after fallback fill
        for k in range(2, 6):
            t[k] = max(t[k], t[k - 1])
        tables[c] = t
    return tables


def apply(method: str, model, criterion: str, ai: int | None) -> int | None:
    if ai is None:
        return None
    if method == "B0_literal":
        return ai
    if method == "B1_shift":
        return _clip(ai + model[criterion])
    if method == "B2_table":
        return model[criterion][ai]
    raise ValueError(method)


def dev_pairs(preds: list[dict], labels: dict, split_of: dict, condition: str,
              groups: set | None = None) -> dict[str, list[tuple[int, int]]]:
    pairs = {c: [] for c in CRITERIA}
    for p in preds:
        pid = p["project_id"]
        lab = labels.get(pid)
        if (p["condition"] != condition or p["replicate"] != 1 or p["status"] != "scored"
                or not lab or not lab["eligible"] or split_of.get(pid) != "development"):
            continue
        if groups is not None and lab["group_id"] not in groups:
            continue
        pairs[p["criterion"]].append((p["score"], lab[p["criterion"]]))
    return pairs


def calibrated_preds(preds: list[dict], method: str, model, condition: str) -> list[dict]:
    out = []
    for p in preds:
        if p["condition"] != condition:
            continue
        q = dict(p)
        q["condition"] = f"{condition}+{method}"
        q["score"] = apply(method, model, p["criterion"], p["score"]) if p["status"] == "scored" else None
        out.append(q)
    return out


def learning_curve_groups(dev_groups: list[str], sizes=(5, 10, 20, 30), draws=200, seed=7):
    """Random subsets of development groups for the 'how many local examples?' curve."""
    rng = random.Random(seed)
    for k in sizes:
        if k > len(dev_groups):
            continue
        for d in range(draws):
            yield k, d, set(rng.sample(dev_groups, k))
