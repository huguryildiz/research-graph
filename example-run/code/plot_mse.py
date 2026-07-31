#!/usr/bin/env python3
"""Render figure fig-01 as an ASCII chart from statistical_report.json.

Dependency-free on purpose: the figure registry has to name a script whose
digest can be verified on any machine, so the plot is text.
"""

from __future__ import annotations

import argparse
import json
import pathlib


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--report", default="statistical_report.json")
    args = parser.parse_args(argv)

    report = json.loads(pathlib.Path(args.report).read_text(encoding="utf-8"))
    estimates = report["body"]["estimates"]
    widest = max(e["ci_upper"] for e in estimates)

    print("Paired MSE gain, learned over scalar-Wiener LMMSE (dB)")
    print()
    for estimate in estimates:
        scale = 44 / widest
        lo = round(estimate["ci_lower"] * scale)
        hi = round(estimate["ci_upper"] * scale)
        mid = round(estimate["estimate"] * scale)
        bar = ["-"] * (hi + 1)
        for index in range(lo):
            bar[index] = " "
        bar[mid] = "+"
        print(f"  {estimate['metric']:<26}{''.join(bar)}")
        print(f"  {'':<26}{estimate['estimate']} dB "
              f"[{estimate['ci_lower']}, {estimate['ci_upper']}]  n={estimate['n']}")
    print()
    print("+ marks the mean; the bar spans the 95 percent interval.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
