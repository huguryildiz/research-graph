"""The example run's statistics must be derivable, not merely asserted.

`example-run/README.md` invites the reader to re-derive every number in
`statistical_report.json` from `raw_results.jsonl`. This is that invitation
accepted on every CI run: the report is regenerated from the raw records and
compared field by field.

The report previously named Holm as its multiplicity correction while no
p-value existed anywhere in the repository to correct. That is the class of
defect these tests close — a procedure claimed in an artifact must have a
computation behind it that anyone can run.
"""

import importlib.util
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
RUN = ROOT / "example-run"


@pytest.fixture(scope="module")
def analyze():
    spec = importlib.util.spec_from_file_location("analyze", RUN / "code" / "analyze.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def records():
    lines = (RUN / "raw_results.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line]


@pytest.fixture(scope="module")
def committed():
    return json.loads((RUN / "statistical_report.json").read_text(encoding="utf-8"))["body"]


def test_the_committed_report_is_what_the_script_derives(analyze, records, committed):
    assert analyze.build_body(records) == committed


def test_every_estimate_carries_the_p_value_its_correction_acts_on(committed):
    assert "holm" in committed["multiplicity_correction"].lower()
    for estimate in committed["estimates"]:
        assert 0.0 < estimate["p_value"] <= 1.0, estimate["result_id"]
        assert estimate["p_adjusted"] >= estimate["p_value"], estimate["result_id"]


def test_holm_is_step_down_and_monotone(analyze):
    raw = {-10: 0.04, -5: 0.001, 0: 0.02}
    adjusted = analyze.holm(raw)
    assert adjusted[-5] == pytest.approx(0.003)
    assert adjusted[0] == pytest.approx(0.04)
    assert adjusted[-10] == pytest.approx(0.04)
    ordered = sorted(raw, key=lambda point: raw[point])
    values = [adjusted[point] for point in ordered]
    assert values == sorted(values), "Holm must not decrease down the ordering"


def test_the_permutation_test_is_exact_not_sampled(analyze):
    """All-positive differences leave exactly two extreme sign assignments."""
    assert analyze.permutation_p([1.0, 2.0, 3.0]) == pytest.approx(2 / 8)
    assert analyze.permutation_p([1.0] * 10) == pytest.approx(2 / 1024)


def test_the_manuscript_quotes_the_intervals_the_report_holds(committed):
    text = (RUN / "manuscript.md").read_text(encoding="utf-8")
    for estimate in committed["estimates"]:
        interval = f"[{estimate['ci_lower']}, {estimate['ci_upper']}]"
        assert interval in text, (estimate["result_id"], interval)


def test_the_sealed_channels_are_the_channels_the_benchmark_drew():
    """The data manifest must seal the run's own inputs, not a parallel draw.

    `--channels` once seeded on the seed alone while `run_one` seeds on
    ``seed*1000 + snr_db``, so the committed file held twenty channels no run
    ever saw and the manifest sealed the wrong bytes. T2 passed it, because a
    digest check cannot tell a true hash of an irrelevant file from a true hash
    of the right one. This is the check that can.
    """
    import random

    spec = importlib.util.spec_from_file_location(
        "estimator_bench", RUN / "code" / "estimator_bench.py"
    )
    bench = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bench)

    rows = [json.loads(line) for line
            in (RUN / "data" / "channels.jsonl").read_text(encoding="utf-8").splitlines()
            if line]
    assert len(rows) == len(bench.DEFAULT_SEEDS) * len(bench.SNR_POINTS)
    for row in rows:
        taps, _ = bench.channel(random.Random(row["seed"] * 1000 + row["snr_db"]))
        assert [round(t.real, 12) for t in taps] == row["taps_real"], row["seed"]
        assert [round(t.imag, 12) for t in taps] == row["taps_imag"], row["seed"]


def test_the_data_manifest_seals_the_file_that_is_on_disk():
    import hashlib

    manifest = json.loads((RUN / "data_manifest.json").read_text(encoding="utf-8"))
    for dataset in manifest["body"]["datasets"]:
        blob = (RUN / dataset["path"]).read_bytes()
        assert dataset["sha256"] == hashlib.sha256(blob).hexdigest(), dataset["path"]
        assert dataset["bytes"] == len(blob), dataset["path"]
        assert dataset["rows"] == len(blob.decode("utf-8").splitlines()), dataset["path"]
