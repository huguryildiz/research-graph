#!/usr/bin/env python3
"""Does a learned channel estimator actually beat LMMSE at low SNR?

A small, dependency-free OFDM pilot-aided channel-estimation benchmark.

Three estimators over the same noisy pilot observations:

  ls        raw least squares, no smoothing
  lmmse     scalar Wiener shrinkage using the true channel and noise powers
  learned   a tuned DFT-domain filter: transform to the delay domain, keep the
            first ``TAPS`` taps, transform back, then apply Wiener shrinkage

The "learned" estimator is not a neural network. It is the exploitable structure
a learned estimator recovers in this setting -- delay-domain sparsity -- written
out explicitly so the whole benchmark stays deterministic and reviewable. The
question the run answers is whether exploiting that structure survives a paired,
seed-matched comparison at low SNR, which is exactly what the literature in this
area often reports without.

Deterministic: every random draw comes from ``random.Random(seed)``. No clock,
no unseeded generator, no thread-dependent ordering.
"""

from __future__ import annotations

import argparse
import cmath
import json
import math
import random
import sys

SUBCARRIERS = 64
TAPS = 8
SNR_POINTS = (-10, -5, 0, 5, 10)
DEFAULT_SEEDS = tuple(range(41, 61))


def _complex_normal(rng: random.Random, variance: float) -> complex:
    """One circularly symmetric complex Gaussian draw, via Box-Muller."""
    scale = math.sqrt(variance / 2.0)
    u1 = max(rng.random(), 1e-12)
    u2 = rng.random()
    magnitude = math.sqrt(-2.0 * math.log(u1))
    return complex(scale * magnitude * math.cos(2 * math.pi * u2),
                   scale * magnitude * math.sin(2 * math.pi * u2))


def _dft(samples: list[complex], inverse: bool = False) -> list[complex]:
    n = len(samples)
    sign = 1.0 if inverse else -1.0
    scale = 1.0 / n if inverse else 1.0
    out = []
    for k in range(n):
        total = 0j
        for t, value in enumerate(samples):
            total += value * cmath.exp(sign * 2j * math.pi * k * t / n)
        out.append(total * scale)
    return out


def channel(rng: random.Random) -> tuple[list[complex], list[complex]]:
    """An exponentially decaying Rayleigh tap channel and its frequency response."""
    powers = [math.exp(-tap / 3.0) for tap in range(TAPS)]
    total = sum(powers)
    taps = [_complex_normal(rng, p / total) for p in powers]
    padded = taps + [0j] * (SUBCARRIERS - TAPS)
    return taps, _dft(padded)


def observe(rng: random.Random, response: list[complex], snr_db: float) -> list[complex]:
    noise_power = 10 ** (-snr_db / 10.0)
    return [h + _complex_normal(rng, noise_power) for h in response]


def _mse(estimate: list[complex], truth: list[complex]) -> float:
    return sum(abs(a - b) ** 2 for a, b in zip(estimate, truth)) / len(truth)


def estimate_ls(observed: list[complex], snr_db: float) -> list[complex]:
    return list(observed)


def estimate_lmmse(observed: list[complex], snr_db: float) -> list[complex]:
    noise_power = 10 ** (-snr_db / 10.0)
    gain = 1.0 / (1.0 + noise_power)
    return [gain * y for y in observed]


def estimate_learned(observed: list[complex], snr_db: float) -> list[complex]:
    noise_power = 10 ** (-snr_db / 10.0)
    delay = _dft(observed, inverse=True)
    truncated = [v if index < TAPS else 0j for index, v in enumerate(delay)]
    smoothed = _dft(truncated)
    gain = 1.0 / (1.0 + noise_power * TAPS / SUBCARRIERS)
    return [gain * h for h in smoothed]


ESTIMATORS = {"ls": estimate_ls, "lmmse": estimate_lmmse, "learned": estimate_learned}


def run_one(seed: int) -> list[dict]:
    records = []
    for snr_db in SNR_POINTS:
        rng = random.Random(seed * 1000 + snr_db)
        _, response = channel(rng)
        observed = observe(rng, response, snr_db)
        for name, estimator in ESTIMATORS.items():
            records.append({
                "run_id": f"run_{seed:03d}",
                "seed": seed,
                "snr_db": snr_db,
                "estimator": name,
                "mse": round(_mse(estimator(observed, snr_db), response), 12),
            })
    return records


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, action="append",
                        help="run one seed; repeatable. Default: 41-60")
    parser.add_argument("--out", help="write JSON Lines here instead of stdout")
    parser.add_argument("--channels", help="also write the generated channels here")
    args = parser.parse_args(argv)

    seeds = tuple(args.seed) if args.seed else DEFAULT_SEEDS
    records = [record for seed in seeds for record in run_one(seed)]
    text = "".join(json.dumps(r, sort_keys=True) + "\n" for r in records)

    if args.channels:
        # One row per (seed, SNR) cell, drawn from the same generator state the
        # benchmark uses. Seeding this on the seed alone would write channels no
        # run ever saw, and a data manifest that seals them would be recording
        # the wrong file.
        rows = []
        for seed in seeds:
            for snr_db in SNR_POINTS:
                taps, _ = channel(random.Random(seed * 1000 + snr_db))
                rows.append(json.dumps(
                    {"seed": seed, "snr_db": snr_db,
                     "taps_real": [round(t.real, 12) for t in taps],
                     "taps_imag": [round(t.imag, 12) for t in taps]}, sort_keys=True))
        with open(args.channels, "w", encoding="utf-8") as handle:
            handle.write("\n".join(rows) + "\n")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
