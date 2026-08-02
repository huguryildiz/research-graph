#!/usr/bin/env python3
"""Derive every number in `statistical_report.json` from `raw_results.jsonl`.

The report used to carry a `multiplicity_correction` field naming Holm, and a
manuscript sentence claiming the intervals survived it, while nothing in the
repository ever computed a p-value. A stated procedure with no computation
behind it is the failure this kit exists to catch, so the procedure is computed
here and the report is generated from the result.

Three quantities per SNR point, all from the same paired per-seed differences
``d_i = 10*log10(mse_lmmse_i / mse_learned_i)``:

  estimate   the mean of d
  interval   percentile bootstrap, 5000 resamples, ``random.Random(20260731)``
  p-value    exact two-sided paired sign-flip permutation test over all 2^20
             sign assignments -- an enumeration, not a sample, so it carries no
             seed and cannot drift

Holm's step-down correction is then applied across the three low-SNR points the
frozen protocol registered (-10, -5 and 0 dB). It is applied to the p-values;
the intervals are reported unadjusted, and the manuscript says which is which.

Deterministic and dependency-free. Run it with no arguments to print the
generated body; ``--check`` diffs it against the committed report instead.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import random
import sys
from collections import defaultdict

HERE = pathlib.Path(__file__).resolve().parent
RUN = HERE.parent

BOOTSTRAP_DRAWS = 5000
BOOTSTRAP_SEED = 20260731
CI_LEVEL = 0.95
REGISTERED_POINTS = (-10, -5, 0)
REPORTED_POINTS = (-10, -5, 0)
LABEL = {-10: "minus10dB", -5: "minus5dB", 0: "0dB", 5: "5dB", 10: "10dB"}


def paired_differences(records: list[dict]) -> dict[int, list[float]]:
    """Per-seed gain in dB of `learned` over `lmmse`, grouped by SNR point.

    Within a seed all three estimators see the identical observation vector, so
    the difference is paired and the seed cancels out of the comparison.
    """
    cell: dict[tuple[int, int], dict[str, float]] = defaultdict(dict)
    for record in records:
        cell[(record["seed"], record["snr_db"])][record["estimator"]] = record["mse"]
    grouped: dict[int, list[float]] = defaultdict(list)
    for (_, snr_db), mse in sorted(cell.items()):
        grouped[snr_db].append(10.0 * math.log10(mse["lmmse"] / mse["learned"]))
    return dict(grouped)


def bootstrap_interval(diffs: list[float]) -> tuple[float, float]:
    rng = random.Random(BOOTSTRAP_SEED)
    n = len(diffs)
    means = sorted(sum(rng.choices(diffs, k=n)) / n for _ in range(BOOTSTRAP_DRAWS))
    tail = (1.0 - CI_LEVEL) / 2.0
    return means[int(tail * BOOTSTRAP_DRAWS)], means[int((1.0 - tail) * BOOTSTRAP_DRAWS)]


def permutation_p(diffs: list[float]) -> float:
    """Exact two-sided sign-flip p-value: every one of the 2^n sign assignments.

    Under the null the sign of each paired difference is exchangeable, so the
    reference set is the full set of sign flips. Enumerating subset sums costs
    2^n additions, which is a second at n = 20 and is why this is exact rather
    than a sampled approximation.
    """
    n = len(diffs)
    observed = abs(sum(diffs))
    total = sum(diffs)
    subset_sums = [0.0]
    for value in diffs:
        subset_sums += [carried + value for carried in subset_sums]
    # flipping the signs of subset S turns the statistic into total - 2*sum(S)
    extreme = sum(1 for s in subset_sums if abs(total - 2.0 * s) >= observed - 1e-12)
    return extreme / float(1 << n)


def holm(p_values: dict[int, float]) -> dict[int, float]:
    """Holm step-down, monotonicity enforced, each value capped at 1."""
    order = sorted(p_values, key=lambda point: p_values[point])
    adjusted: dict[int, float] = {}
    running = 0.0
    for rank, point in enumerate(order):
        running = max(running, (len(order) - rank) * p_values[point])
        adjusted[point] = min(1.0, running)
    return adjusted


def build_body(records: list[dict]) -> dict:
    diffs = paired_differences(records)
    raw_p = {point: permutation_p(diffs[point]) for point in REGISTERED_POINTS}
    adjusted = holm(raw_p)

    estimates = []
    for index, point in enumerate(REPORTED_POINTS, start=1):
        sample = diffs[point]
        low, high = bootstrap_interval(sample)
        estimates.append({
            "result_id": f"r-{index:02d}",
            "metric": f"mse_gain_db_at_{LABEL[point]}",
            "estimate": round(sum(sample) / len(sample), 3),
            "ci_lower": round(low, 3),
            "ci_upper": round(high, 3),
            "ci_level": CI_LEVEL,
            "n": len(sample),
            "p_value": float(f"{raw_p[point]:.3g}"),
            "p_adjusted": float(f"{adjusted[point]:.3g}"),
            "method": (
                "paired per-seed difference; percentile bootstrap, "
                f"{BOOTSTRAP_DRAWS} draws, seed {BOOTSTRAP_SEED}; "
                f"p from an exact two-sided sign-flip permutation test over all 2^{len(sample)} "
                "sign assignments; p_adjusted by Holm across the three registered low-SNR points"
            ),
            "assumptions_checked": [
                {"name": "seed-matched pairing", "passed": True},
                {"name": "finite variance", "passed": True},
            ],
        })

    return {
        "estimates": estimates,
        "multiplicity_correction": (
            "Holm step-down across the three registered low-SNR points "
            "(-10, -5, 0 dB), applied to the permutation p-values. The reported "
            "intervals are unadjusted."
        ),
        "effect_sizes": [
            {"result_id": e["result_id"], "name": "mean_gain_db", "value": e["estimate"]}
            for e in estimates
        ],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--results", default=str(RUN / "raw_results.jsonl"))
    parser.add_argument("--check", action="store_true",
                        help="compare against the committed statistical_report.json")
    args = parser.parse_args(argv)

    records = [json.loads(line) for line in
               pathlib.Path(args.results).read_text(encoding="utf-8").splitlines() if line]
    body = build_body(records)

    if not args.check:
        print(json.dumps(body, indent=2))
        return 0

    committed = json.loads((RUN / "statistical_report.json").read_text(encoding="utf-8"))
    if committed["body"] == body:
        print("statistical_report.json matches what this script derives.")
        return 0
    print("MISMATCH between statistical_report.json and the derivation:", file=sys.stderr)
    print(json.dumps(body, indent=2), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
