"""SIMULATED precision analysis. Nothing in this module is an empirical result.

Purpose: show what the locked test set can and cannot resolve at the actual
eligible sample size, so the dev/test split is chosen with its precision cost
visible.

Inputs that come from the real audit (supplied by the PI, not invented here):
  * the number of score-5 ratings per criterion among 128 eligible artifacts.
Inputs that are ASSUMPTIONS (stated and varied):
  * how the non-5 ratings divide among levels 1-4;
  * the AI error process (scenarios below).
"""
from __future__ import annotations

import numpy as np

from .metrics import weighted_kappa

N_ELIGIBLE = 128
FIVES = {"project_description": 87, "data_visualization": 99, "algorithm": 73,
         "essential_question": 62, "next_steps": 56, "citations": 81}
# ASSUMPTION: non-5 ratings split 4:3:2:1 = 60%:25%:10%:5%.
NON5_SPLIT = np.array([0.05, 0.10, 0.25, 0.60])  # levels 1,2,3,4

SCENARIOS = {
    # P(diff = 0, +/-1, +/-2) for the AI relative to the historical score, before clipping to 1..5.
    "strong_agreement": (0.75, 0.22, 0.03),
    "moderate_agreement": (0.60, 0.33, 0.07),
    "weak_agreement": (0.45, 0.40, 0.15),
}


def human_marginal(criterion: str) -> np.ndarray:
    p5 = FIVES[criterion] / N_ELIGIBLE
    return np.append(NON5_SPLIT * (1 - p5), p5)


def simulate_once(rng, n, marg, scen, upward_bias=0.0):
    h = rng.choice(np.arange(1, 6), size=n, p=marg)
    p0, p1, p2 = scen
    mag = rng.choice([0, 1, 2], size=n, p=[p0, p1, p2])
    sign = np.where(rng.random(n) < 0.5 + upward_bias, 1, -1)
    a = np.clip(h + sign * mag, 1, 5)
    return h, a


def precision_table(n_test_values=(45, 64, 82, 96), reps=2000, seed=7) -> list[dict]:
    rng = np.random.default_rng(seed)
    rows = []
    for crit in ["data_visualization", "next_steps"]:  # most and least ceilinged criteria
        marg = human_marginal(crit)
        for sname, scen in SCENARIOS.items():
            for n in n_test_values:
                maes, exacts, qwks, lows = [], [], [], []
                for _ in range(reps):
                    h, a = simulate_once(rng, n, marg, scen)
                    maes.append(np.abs(a - h).mean())
                    exacts.append((a == h).mean())
                    qwks.append(weighted_kappa(h, a))
                    lows.append((h <= 3).sum())
                q = lambda x: np.nanpercentile(x, [2.5, 97.5])  # noqa: E731
                rows.append({
                    "criterion": crit, "scenario": sname, "n_test": n,
                    "mae_mean": float(np.mean(maes)), "mae_95range_width": float(np.diff(q(maes))[0]),
                    "exact_95range_width": float(np.diff(q(exacts))[0]),
                    "qwk_mean": float(np.nanmean(qwks)), "qwk_95range_width": float(np.diff(q(qwks))[0]),
                    "expected_human_le3": float(np.mean(lows)),
                })
    return rows


def render_markdown(rows: list[dict]) -> str:
    L = ["# SIMULATED precision analysis (not empirical results)", "",
         "Every number below comes from simulation. Inputs taken from the real audit: score-5 counts per "
         "criterion among 128 eligible artifacts. Assumptions: how non-5 scores divide among levels 1-4 "
         "(60/25/10/5% for 4/3/2/1), and the AI error scenarios. Widths are the central 95% range of the "
         "metric across 2,000 simulated test sets. They approximate CI widths if projects were independent. "
         "Duplicate groups make the real intervals slightly wider.", "",
         "| criterion | AI scenario | n test | mean MAE | MAE 95% width | exact-agreement width | mean QWK | QWK width | expected n human<=3 |",
         "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['criterion']} | {r['scenario']} | {r['n_test']} | {r['mae_mean']:.2f} | "
                 f"{r['mae_95range_width']:.2f} | {r['exact_95range_width']:.2f} | {r['qwk_mean']:.2f} | "
                 f"{r['qwk_95range_width']:.2f} | {r['expected_human_le3']:.1f} |")
    L += ["", "Reading guide: QWK intervals are wide and unstable under strong ceiling effects, which is why "
          "MAE, within-one agreement and severe-discrepancy rate are primary and QWK is secondary. With roughly "
          "8-20 human scores of 3 or below per criterion in the test set, error rates on low-scoring work can be "
          "described but not estimated precisely. That limitation is reported, not hidden."]
    return "\n".join(L)
