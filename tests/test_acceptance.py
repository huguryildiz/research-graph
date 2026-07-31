"""The seven done-criteria of the design document, section 13."""

import json
import pathlib
import subprocess
import sys

from rgraph.cli import main
from rgraph.hashing import content_hash

ROOT = pathlib.Path(__file__).resolve().parents[1]
R = ["--root", str(ROOT), "--no-banner"]
ALL_GATES = ("H1", "E1", "H2", "H3", "T1", "H4", "T2", "V1", "M1")


def test_1_static_layer_is_clean_on_the_reference_graph():
    assert main([*R, "check", "--static"]) == 0


def test_2_all_nine_gates_are_green_on_the_example_run(example_run):
    for gate_id in ALL_GATES:
        assert main([*R, "--run", str(example_run), "check", gate_id]) == 0, gate_id


def test_3_a_broken_doi_makes_e1_red(example_run, capsys):
    path = example_run / "corpus_snapshot.json"
    document = json.loads(path.read_text())
    document["body"]["sources"][0]["doi"] = None
    document["content_hash"] = content_hash(document["body"])
    path.write_text(json.dumps(document))
    assert main([*R, "--run", str(example_run), "check", "E1"]) == 1
    assert "SOURCE NOT RESOLVED" in capsys.readouterr().out


def test_4_data_changed_after_the_freeze_invalidates_downstream_gates(example_run, capsys):
    for gate_id in ALL_GATES:
        main([*R, "--run", str(example_run), "check", gate_id])
    capsys.readouterr()
    path = example_run / "data_manifest.json"
    document = json.loads(path.read_text())
    document["body"]["datasets"][0]["bytes"] += 1
    document["content_hash"] = content_hash(document["body"])
    path.write_text(json.dumps(document))
    for gate_id in ("T2", "V1", "M1"):
        assert main([*R, "--run", str(example_run), "check", gate_id]) == 1, gate_id
    assert "STALE" in capsys.readouterr().out


def test_5_trace_prints_an_unbroken_chain(example_run, capsys):
    main([*R, "--run", str(example_run), "check", "M1"])
    capsys.readouterr()
    assert main([*R, "--run", str(example_run), "trace", "c-01"]) == 0
    assert "Provenance chain is complete." in capsys.readouterr().out


def test_6_a_clean_checkout_reaches_a_green_demo(tmp_path):
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "--depth", "1", str(ROOT), str(clone)],
                   check=True, capture_output=True)
    result = subprocess.run(
        [sys.executable, "-m", "rgraph", "--root", str(clone), "--no-banner",
         "demo", "--scenario", "1"],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_7_the_landing_page_and_the_diagram_are_self_contained():
    for name in ("index.html", "architecture.html"):
        text = (ROOT / name).read_text(encoding="utf-8")
        for needle in ("cdn.", "googleapis", "unpkg", "jsdelivr"):
            assert needle not in text, (name, needle)


def test_cli_output_is_english_only(example_run, capsys):
    main([*R, "--run", str(example_run), "status"])
    main([*R, "--run", str(example_run), "check", "E1"])
    main([*R, "--run", str(example_run), "trace", "c-01"])
    assert not (set("çğıöşüÇĞİÖŞÜ") & set(capsys.readouterr().out))


def test_every_gate_screen_repeats_the_claim_boundary(example_run, capsys):
    for gate_id in ALL_GATES:
        main([*R, "--run", str(example_run), "check", gate_id])
        out = capsys.readouterr().out
        assert "[----] Scientific correctness was not determined" in out, gate_id
