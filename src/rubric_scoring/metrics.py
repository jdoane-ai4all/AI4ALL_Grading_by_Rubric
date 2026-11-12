"""Agreement metrics with project-group cluster bootstrap.

Conventions
* Unit of resampling = project group (duplicates/versions resampled together).
* Six criteria and repeated runs are NOT independent observations; they are never
  pooled to inflate N. Pooled-criterion summaries are descriptive only.
* Coverage (share of calls that produced a score) is always reported next to
  agreement among scored cases, so abstentions/failures cannot silently improve metrics.
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np

LEVELS = np.arange(1, 6)


def confusion(h, a, k: int = 5) -> np.ndarray:
    m = np.zeros((k, k), dtype=int)
    for x, y in zip(h, a):
        m[int(x) - 1, int(y) - 1] += 1
    return m


def weighted_kappa(h, a, weights: str = "quadratic", k: int = 5) -> float:
    """Cohen's weighted kappa on a fixed 1..k category set (empty categories kept)."""
    o = confusion(h, a, k).astype(float)
    n = o.sum()
    if n == 0:
        return float("nan")
    i, j = np.meshgrid(np.arange(k), np.arange(k), indexing="ij")
    w = (i - j) ** 2 / (k - 1) ** 2 if weights == "quadratic" else np.abs(i - j) / (k - 1)
    e = np.outer(o.sum(1), o.sum(0)) / n
    denom = (w * e).sum()
    return float("nan") if denom == 0 else float(1 - (w * o).sum() / denom)


def icc_a1(x, y) -> float:
    """ICC(A,1): two-way, absolute agreement, single rater (McGraw & Wong 1996, case A,1).

    Rows = projects, columns = 2 'raters' (historical score, AI score). The AI is a
    fixed rater here, so this is reported as an agreement index for these two score
    sources, not a generalisable rater-population reliability.
    """
    d = np.column_stack([x, y]).astype(float)
    n, k = d.shape
    if n < 3:
        return float("nan")
    gm = d.mean()
    ssr = k * ((d.mean(1) - gm) ** 2).sum()
    ssc = n * ((d.mean(0) - gm) ** 2).sum()
    sst = ((d - gm) ** 2).sum()
    sse = sst - ssr - ssc
    msr, msc, mse = ssr / (n - 1), ssc / (k - 1), sse / ((n - 1) * (k - 1))
    denom = msr + (k - 1) * mse + k * (msc - mse) / n
    return float("nan") if denom == 0 else float((msr - mse) / denom)


def criterion_point(h, a) -> dict:
    h, a = np.asarray(h, float), np.asarray(a, float)
    d = a - h
    return {
        "n": int(len(h)),
        "mae": float(np.abs(d).mean()) if len(d) else float("nan"),
        "signed_bias": float(d.mean()) if len(d) else float("nan"),
        "exact": float((d == 0).mean()) if len(d) else float("nan"),
        "within_one": float((np.abs(d) <= 1).mean()) if len(d) else float("nan"),
        "severe_rate": float((np.abs(d) >= 2).mean()) if len(d) else float("nan"),
        "qwk": weighted_kappa(h, a, "quadratic"),
        "lwk": weighted_kappa(h, a, "linear"),
        "over_on_low": float((d[h <= 3] > 0).mean()) if (h <= 3).any() else float("nan"),
        "n_human_low": int((h <= 3).sum()),
    }


def total_point(ht, at, threshold: int = 24, crit_abs_err_sum=None) -> dict:
    ht, at = np.asarray(ht, float), np.asarray(at, float)
    d = at - ht
    out = {
        "n": int(len(ht)),
        "mae": float(np.abs(d).mean()),
        "signed_bias": float(d.mean()),
        "icc_a1": icc_a1(ht, at),
        "bland_altman_mean_diff": float(d.mean()),
        "bland_altman_loa": [float(d.mean() - 1.96 * d.std(ddof=1)), float(d.mean() + 1.96 * d.std(ddof=1))]
        if len(d) > 2 else [float("nan")] * 2,
        "threshold_agreement": float(((ht >= threshold) == (at >= threshold)).mean()),
        "false_nominate_rate": float(((at >= threshold) & (ht < threshold)).sum() / max((ht < threshold).sum(), 1)),
        "false_exclude_rate": float(((at < threshold) & (ht >= threshold)).sum() / max((ht >= threshold).sum(), 1)),
        "pearson_r_descriptive_only": float(np.corrcoef(ht, at)[0, 1]) if np.std(at) > 0 and np.std(ht) > 0 else float("nan"),
    }
    if crit_abs_err_sum is not None:
        # Cancellation: how much criterion-level error disappears in the total.
        s = float(np.mean(crit_abs_err_sum))
        out["mean_sum_abs_criterion_error"] = s
        out["cancellation_ratio"] = float(1 - out["mae"] / s) if s > 0 else float("nan")
    return out


def cluster_bootstrap(units: list[dict], group_key: str, stat_fn, reps: int = 5000, seed: int = 0) -> dict:
    """Percentile CI for stat_fn(list_of_units) resampling whole groups with replacement."""
    rng = np.random.default_rng(seed)
    groups = defaultdict(list)
    for u in units:
        groups[u[group_key]].append(u)
    keys = list(groups)
    point = stat_fn(units)
    draws = []
    for _ in range(reps):
        pick = rng.integers(0, len(keys), len(keys))
        sample = [u for i in pick for u in groups[keys[i]]]
        v = stat_fn(sample)
        if v == v:  # drop NaN
            draws.append(v)
    if not draws:
        return {"point": point, "ci95": [float("nan")] * 2, "reps_used": 0}
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return {"point": point, "ci95": [float(lo), float(hi)], "reps_used": len(draws)}


def paired_difference(units: list[dict], group_key: str, fa, fb, reps: int = 5000, seed: int = 0) -> dict:
    """Bootstrap CI of stat(A) - stat(B) computed on the SAME resampled groups."""
    return cluster_bootstrap(units, group_key, lambda s: fa(s) - fb(s), reps, seed)


def stability(rep_scores: dict[tuple, list]) -> dict:
    """rep_scores[(project, criterion)] -> list of scores across replicates (None = abstain/fail)."""
    n = changed = abst_flip = 0
    ranges = []
    for vals in rep_scores.values():
        if len(vals) < 2:
            continue
        n += 1
        scored = [v for v in vals if v is not None]
        if len(scored) != len(vals) and scored:
            abst_flip += 1
        if len(set(vals)) > 1:
            changed += 1
        if len(scored) >= 2:
            ranges.append(max(scored) - min(scored))
    return {
        "n_project_criterion_pairs": n,
        "any_change_rate": changed / n if n else float("nan"),
        "abstain_flip_rate": abst_flip / n if n else float("nan"),
        "max_range": int(max(ranges)) if ranges else None,
        "range_ge2_rate": float(np.mean([r >= 2 for r in ranges])) if ranges else float("nan"),
    }
