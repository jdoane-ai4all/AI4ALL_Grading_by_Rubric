"""Human-review routing policy and coverage-risk evaluation.

The policy decides which AI-scored projects a person must review. It never
finalises a grade: under every policy, a human holds final authority. Thresholds
are tuned on development data only and frozen before the test set is unlocked.
"""
from __future__ import annotations

from dataclasses import dataclass

from .rubric import CRITERIA


@dataclass(frozen=True)
class Policy:
    threshold: int = 24
    band: int = 2               # route if |predicted total - threshold| <= band
    low_score_cut: int = 3      # route if any predicted criterion <= this
    route_on_instability: bool = True
    route_on_limiting_factor: bool = True


def route(project: dict, policy: Policy) -> tuple[bool, list[str]]:
    """project = {'scores': {crit: int|None}, 'unstable': {crit: bool}, 'flags': {crit: str}}"""
    reasons = []
    s = project["scores"]
    if any(s.get(c) is None for c in CRITERIA):
        reasons.append("abstain_or_failure")
    else:
        tot = sum(s[c] for c in CRITERIA)
        if abs(tot - policy.threshold) <= policy.band:
            reasons.append("near_threshold")
    if any(v is not None and v <= policy.low_score_cut for v in s.values()):
        reasons.append("low_predicted_score")
    if policy.route_on_instability and any(project.get("unstable", {}).values()):
        reasons.append("run_to_run_instability")
    if policy.route_on_limiting_factor and any(project.get("flags", {}).values()):
        reasons.append("limiting_factor_flag")
    return bool(reasons), reasons


def evaluate(projects: dict[str, dict], human: dict[str, dict], policy: Policy) -> dict:
    """Coverage = share auto-accepted. Risk = errors among auto-accepted only."""
    accepted, routed = [], []
    for pid, p in projects.items():
        (routed if route(p, policy)[0] else accepted).append(pid)
    n = len(projects)
    sev = crit_err = thr_err = 0
    for pid in accepted:
        a, h = projects[pid]["scores"], human[pid]
        diffs = [abs(a[c] - h[c]) for c in CRITERIA]
        sev += any(d >= 2 for d in diffs)
        crit_err += sum(d > 0 for d in diffs)
        thr_err += (sum(a.values()) >= policy.threshold) != (sum(h[c] for c in CRITERIA) >= policy.threshold)
    k = len(accepted)
    return {
        "n_projects": n,
        "coverage_auto_accepted": k / n if n else float("nan"),
        "review_workload_projects": len(routed),
        "accepted_with_any_severe_error": sev / k if k else float("nan"),
        "accepted_criterion_error_rate": crit_err / (6 * k) if k else float("nan"),
        "accepted_threshold_misclassification": thr_err / k if k else float("nan"),
        "policy": policy.__dict__,
    }


def coverage_risk_curve(projects, human, bands=(0, 1, 2, 3, 4), low_cuts=(2, 3, 4)) -> list[dict]:
    """Grid over policy knobs for the development-set coverage-risk plot."""
    return [evaluate(projects, human, Policy(band=b, low_score_cut=lc)) for b in bands for lc in low_cuts]
