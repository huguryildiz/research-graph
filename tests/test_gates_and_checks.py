import json
import hashlib
import pathlib
import subprocess

from rgraph.checks import CONTENT_CHECKS
from rgraph.campaigns import retire_current_campaign, reused_run_ids
from rgraph.config import load_kit
from rgraph.gates import evaluate_gate, record_from
from rgraph.hashing import document_hash
from rgraph.run import load_run
from rgraph.schemas import registry

ROOT = pathlib.Path(__file__).resolve().parents[1]
ALL_GATES = ("H1", "E1", "H2", "H3", "T1", "H4", "T2", "V1", "M1")


def _kit():
    return load_kit(ROOT, assignment="assignment.example.yaml")


def _edit(path: pathlib.Path, mutate) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    mutate(document["body"])
    document["content_hash"] = document_hash(document)
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")


def _upgrade_code_commit_v2(run_dir: pathlib.Path, tmp_path: pathlib.Path,
                            committed_bytes: bytes | None = None) -> pathlib.Path:
    source = run_dir / "code" / "estimator_bench.py"
    source_repo = tmp_path / "source-repo"
    source_repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=source_repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test Author"], cwd=source_repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=source_repo, check=True)
    (source_repo / "estimator_bench.py").write_bytes(
        source.read_bytes() if committed_bytes is None else committed_bytes
    )
    subprocess.run(["git", "add", "estimator_bench.py"], cwd=source_repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "Retain exact executed source"],
                   cwd=source_repo, check=True)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=source_repo, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    bundle = run_dir / "code" / "source.bundle"
    subprocess.run(["git", "bundle", "create", str(bundle), "--all"],
                   cwd=source_repo, check=True)
    document_path = run_dir / "code_commit.json"
    document = json.loads(document_path.read_text(encoding="utf-8"))
    document["version"] = 2
    document["body"].update({
        "repo": "retained-test-source",
        "commit": commit,
        "dirty": False,
        "bundle_path": "code/source.bundle",
        "bundle_sha256": "sha256:" + hashlib.sha256(bundle.read_bytes()).hexdigest(),
    })
    document["body"]["files"][0]["repo_path"] = "estimator_bench.py"
    document["content_hash"] = document_hash(document)
    document_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return bundle


# ── content checks ─────────────────────────────────────────────────────────

def test_clean_example_passes_every_content_check(example_run):
    kit = _kit()
    run = load_run(example_run, kit)
    for gate in kit.gates.values():
        for name in gate.checks:
            check = CONTENT_CHECKS.get(name)
            if check:
                assert check(run, kit, gate, online=False) == [], (gate.id, name)


def test_null_doi_fails_source_support(example_run):
    _edit(example_run / "corpus_snapshot.json",
          lambda body: body["sources"][0].__setitem__("doi", None))
    kit = _kit()
    findings = CONTENT_CHECKS["source_support"](
        load_run(example_run, kit), kit, kit.gates["E1"], online=False
    )
    assert any(f.code == "SOURCE NOT RESOLVED" for f in findings)


def test_retracted_source_fails_source_support(example_run):
    _edit(example_run / "corpus_snapshot.json",
          lambda body: body["sources"][0].__setitem__("retracted", True))
    kit = _kit()
    findings = CONTENT_CHECKS["source_support"](
        load_run(example_run, kit), kit, kit.gates["E1"], online=False
    )
    assert any(f.code == "SOURCE RETRACTED" for f in findings)


def test_missing_locator_fails_source_support(example_run):
    _edit(example_run / "evidence_matrix.json",
          lambda body: body["rows"][0].__setitem__("locator", {"kind": "page", "value": "x"})
          or body["rows"][0].pop("locator"))
    kit = _kit()
    findings = CONTENT_CHECKS["source_support"](
        load_run(example_run, kit), kit, kit.gates["E1"], online=False
    )
    assert any(f.code == "SUPPORT LOCATOR MISSING" for f in findings)


def test_seed_set_mismatch_fails_run_integrity(example_run):
    _edit(example_run / "run_manifest.json",
          lambda body: body.__setitem__("seeds", body["seeds"][:-1]))
    kit = _kit()
    findings = CONTENT_CHECKS["run_integrity"](
        load_run(example_run, kit), kit, kit.gates["T2"], online=False
    )
    assert any(f.code in ("SEED SET MISMATCH", "N MISMATCH") for f in findings)


def test_missing_dataset_fails_run_integrity(example_run):
    (example_run / "data" / "channels.jsonl").unlink()
    kit = _kit()
    findings = CONTENT_CHECKS["run_integrity"](
        load_run(example_run, kit), kit, kit.gates["T2"], online=False
    )
    assert any(f.code == "DATASET MISSING" for f in findings)


def test_dataset_path_cannot_escape_the_run(example_run):
    _edit(
        example_run / "data_manifest.json",
        lambda body: body["datasets"][0].__setitem__("path", "../outside.bin"),
    )
    kit = _kit()
    findings = CONTENT_CHECKS["run_integrity"](
        load_run(example_run, kit), kit, kit.gates["T2"], online=False
    )
    assert any(f.code == "DATASET PATH INVALID" for f in findings)


def test_unsupported_claim_fails_claim_support(example_run):
    _edit(example_run / "claim_evidence_map.json",
          lambda body: body["claims"][0].__setitem__(
              "supported_by", {"result_ids": [], "source_ids": []}))
    kit = _kit()
    findings = CONTENT_CHECKS["claim_support"](
        load_run(example_run, kit), kit, kit.gates["M1"], online=False
    )
    assert any(f.code == "CLAIM UNSUPPORTED" for f in findings)


# ── gate engine ────────────────────────────────────────────────────────────

def test_every_gate_passes_on_the_example_run(example_run):
    kit = _kit()
    run = load_run(example_run, kit)
    for gate_id in ALL_GATES:
        result = evaluate_gate(run, kit, gate_id)
        assert result.status in ("PASS", "CAVEAT"), (gate_id, result.findings)


def test_t2_rejects_a_code_file_changed_after_its_commit_record(example_run):
    source = example_run / "code" / "estimator_bench.py"
    source.write_text(source.read_text(encoding="utf-8") + "\n# changed\n")
    result = evaluate_gate(load_run(example_run, _kit()), _kit(), "T2")
    assert result.status == "FAIL"
    assert any(f.code == "DIGEST MISMATCH" for f in result.findings)


def test_replacement_campaign_archives_and_rejects_reused_run_ids(example_run):
    kit = _kit()
    run = load_run(example_run, kit)
    current_ids = {item["run_id"] for item in run.get("run_manifest").body["runs"]}
    archive = retire_current_campaign(run)

    assert archive is not None
    assert (archive / "run_manifest.json").is_file()
    assert (archive / "raw_results.jsonl").is_file()
    reloaded = load_run(example_run, kit)
    assert reused_run_ids(reloaded) == current_ids
    assert retire_current_campaign(reloaded) is None
    findings = CONTENT_CHECKS["run_integrity"](
        reloaded, kit, kit.gates["T2"], online=False
    )
    assert any(f.code == "RUN ID REUSED" for f in findings)


def test_t2_v2_verifies_source_against_retained_commit(example_run, tmp_path):
    _upgrade_code_commit_v2(example_run, tmp_path)
    findings = CONTENT_CHECKS["run_integrity"](
        load_run(example_run, _kit()), _kit(), _kit().gates["T2"], online=False
    )
    assert not [finding for finding in findings if finding.ref == "code_commit"]


def test_t2_v2_rejects_commit_with_different_source(example_run, tmp_path):
    _upgrade_code_commit_v2(example_run, tmp_path, b"print('different source')\n")
    findings = CONTENT_CHECKS["run_integrity"](
        load_run(example_run, _kit()), _kit(), _kit().gates["T2"], online=False
    )
    assert any(f.code == "COMMITTED DIGEST MISMATCH" for f in findings)


def test_t2_v2_rejects_a_changed_dependency_lock(example_run):
    lock = example_run / "environment" / "requirements.lock"
    lock.parent.mkdir()
    lock.write_text("numpy==2.5.1\n", encoding="utf-8")
    path = example_run / "environment_lock.json"
    document = json.loads(path.read_text())
    document["version"] = 2
    document["body"]["lock_path"] = "environment/requirements.lock"
    document["body"]["lock_sha256"] = hashlib.sha256(lock.read_bytes()).hexdigest()
    document["content_hash"] = document_hash(document)
    path.write_text(json.dumps(document, indent=2) + "\n")
    lock.write_text("numpy==2.5.2\n", encoding="utf-8")

    findings = CONTENT_CHECKS["run_integrity"](
        load_run(example_run, _kit()), _kit(), _kit().gates["T2"], online=False
    )
    assert any(f.code == "DIGEST MISMATCH" and f.ref == "environment_lock"
               for f in findings)


def test_t2_v2_rejects_an_unbound_run_configuration(example_run):
    config = example_run / "config" / "evaluation.json"
    config.parent.mkdir()
    config.write_text('{"block":"evaluation"}\n', encoding="utf-8")
    digest = hashlib.sha256(config.read_bytes()).hexdigest()
    path = example_run / "run_manifest.json"
    document = json.loads(path.read_text())
    document["version"] = 2
    document["body"]["configurations"] = [{
        "config_id": "evaluation",
        "path": "config/evaluation.json",
        "sha256": digest,
        "argv": ["python", "code/estimator_bench.py", "--config", "config/evaluation.json"],
    }]
    document["content_hash"] = document_hash(document)
    path.write_text(json.dumps(document, indent=2) + "\n")

    findings = CONTENT_CHECKS["run_integrity"](
        load_run(example_run, _kit()), _kit(), _kit().gates["T2"], online=False
    )
    assert any(f.code == "RUN CONFIG UNBOUND" for f in findings)


def test_t2_v2_rejects_incomplete_execution_input_provenance(example_run):
    path = example_run / "run_manifest.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["version"] = 2
    document["inputs"] = [document["inputs"][0]]
    document["body"]["configurations"] = [{
        "config_id": "evaluation",
        "path": "config/evaluation.json",
        "sha256": "3" * 64,
        "argv": ["python", "code/estimator_bench.py"],
    }]
    document["content_hash"] = document_hash(document)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    findings = CONTENT_CHECKS["run_integrity"](
        load_run(example_run, _kit()), _kit(), _kit().gates["T2"], online=False
    )
    assert any(f.code == "EXECUTION INPUT UNBOUND" for f in findings)


def test_missing_input_is_a_presence_failure(example_run):
    (example_run / "evidence_matrix.json").unlink()
    kit = _kit()
    result = evaluate_gate(load_run(example_run, kit), kit, "E1")
    assert result.status == "FAIL"
    assert any(c.name == "presence" and c.status == "FAIL" for c in result.checks)


def test_v1_rejects_inconsistent_reproduction_match_and_rate(example_run):
    _edit(
        example_run / "reproduction_report.json",
        lambda body: (
            body["reproduced"][0].__setitem__("reproduced_sha256", "6" * 64),
            body.__setitem__("reproduction_rate", 1.0),
        ),
    )
    findings = CONTENT_CHECKS["statistical_support"](
        load_run(example_run, _kit()), _kit(), _kit().gates["V1"], online=False
    )
    assert any(f.code == "REPRODUCTION MATCH INCONSISTENT" for f in findings)


def test_v1_v2_uses_selected_configuration_denominator(example_run):
    manifest_path = example_run / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["body"]["configurations"] = [
        {"config_id": "tuning", "path": "config/tuning.json", "sha256": "8" * 64,
         "argv": ["python", "code/estimator_bench.py", "--block", "tuning"]},
        {"config_id": "evaluation", "path": "config/evaluation.json", "sha256": "9" * 64,
         "argv": ["python", "code/estimator_bench.py", "--block", "evaluation"]},
    ]
    for index, item in enumerate(manifest["body"]["runs"]):
        item["config_sha256"] = "8" * 64 if index < 5 else "9" * 64
    manifest["content_hash"] = document_hash(manifest)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    stats_path = example_run / "statistical_report.json"
    stats = json.loads(stats_path.read_text())
    stats["version"] = 2
    for estimate in stats["body"]["estimates"]:
        estimate["config_ids"] = ["evaluation"]
        estimate["n"] = 15
    stats["content_hash"] = document_hash(stats)
    stats_path.write_text(json.dumps(stats, indent=2) + "\n")
    findings = CONTENT_CHECKS["statistical_support"](
        load_run(example_run, _kit()), _kit(), _kit().gates["V1"], online=False
    )
    assert not any(f.code == "N MISMATCH" for f in findings)


def test_stale_upstream_marks_the_gate_stale(example_run):
    kit = _kit()
    run = load_run(example_run, kit)
    for gate_id in ALL_GATES:
        run.write_gate_record(record_from(evaluate_gate(run, kit, gate_id), run, kit))
    _edit(example_run / "data_manifest.json",
          lambda body: body["datasets"][0].__setitem__("bytes", body["datasets"][0]["bytes"] + 1))
    assert evaluate_gate(load_run(example_run, kit), kit, "V1").status == "STALE"


def test_exhausted_budget_blocks(example_run):
    meta = json.loads((example_run / "meta.json").read_text())
    meta["revisions"]["E1"] = {"max": 3, "used": 3}
    (example_run / "meta.json").write_text(json.dumps(meta))
    kit = _kit()
    assert evaluate_gate(load_run(example_run, kit), kit, "E1").status == "BLOCKED"


def test_gate_record_validates_against_its_schema(example_run):
    kit = _kit()
    run = load_run(example_run, kit)
    result = evaluate_gate(run, kit, "M1")
    assert registry(ROOT).validate("gate_record", record_from(result, run, kit)) == []


def _single_provider_kit(tmp_path, provider="codex", model="gpt-5.6"):
    single = tmp_path / "kit"
    single.mkdir()
    for name in ("graph.yaml", "providers.yaml", "gates.yaml"):
        (single / name).write_text((ROOT / name).read_text(encoding="utf-8"), encoding="utf-8")
    (single / "schemas").symlink_to(ROOT / "schemas")
    (single / "assignment.yaml").write_text(
        "\n".join(
            f"{role}: {{provider: {provider}, model: {model}}}"
            for role in ("retrieval", "planning", "execution",
                         "verification", "synthesis", "reviewer")
        ) + "\n"
    )
    return load_kit(single)


def test_the_recorded_identity_beats_the_configured_one(example_run, tmp_path):
    """assignment.yaml says who was meant to run the role; the artifact says who did."""
    kit = _single_provider_kit(tmp_path)
    result = evaluate_gate(load_run(example_run, kit), kit, "M1")
    # config alone would say context_only; the manuscript records claude-code/fable-5
    assert result.producer_identity == "claude-code/fable-5"
    assert result.separation.level == "separate_provider"
    assert result.status == "PASS"


def test_reviewer_that_is_the_producer_fails_the_gate(example_run, tmp_path):
    kit = _single_provider_kit(tmp_path, provider="claude-code", model="fable-5")
    result = evaluate_gate(load_run(example_run, kit), kit, "M1", require_decision=False)
    assert result.status == "FAIL"
    assert result.separation.status == "FAIL"
    assert any(f.code == "REVIEWER IS THE PRODUCER" for f in result.findings)


def test_context_only_is_a_caveat_not_a_failure(example_run, tmp_path):
    """Same provider, different model: allowed, but the caveat must print."""
    kit = _single_provider_kit(tmp_path, provider="claude-code", model="sonnet-5")
    result = evaluate_gate(load_run(example_run, kit), kit, "T1", require_decision=False)
    assert result.separation.level == "separate_model"
    assert result.status in ("PASS", "CAVEAT")


def test_gate_record_carries_the_recorded_producer_identity(example_run):
    kit = _kit()
    run = load_run(example_run, kit)
    record = record_from(evaluate_gate(run, kit, "E1"), run, kit)
    assert record["producer_identity"] == run.get("evidence_matrix").identity


def test_a_manuscript_claim_id_with_no_entry_in_the_map_is_a_finding(example_run):
    """The manuscript may not cite a claim the evidence map has never heard of."""
    _edit(example_run / "manuscript.meta.json",
          lambda body: body["sections"][0]["claim_ids"].append("c-99"))
    kit = _kit()
    findings = CONTENT_CHECKS["claim_support"](
        load_run(example_run, kit), kit, kit.gates["M1"], online=False
    )
    assert any(f.code == "CLAIM NOT MAPPED" and f.ref == "c-99" for f in findings)


def test_a_mapped_claim_that_appears_in_no_section_is_a_finding(example_run):
    """A claim nobody makes in the manuscript is evidence bookkeeping, not support."""
    _edit(example_run / "manuscript.meta.json",
          lambda body: [s.__setitem__("claim_ids", []) for s in body["sections"]])
    kit = _kit()
    findings = CONTENT_CHECKS["claim_support"](
        load_run(example_run, kit), kit, kit.gates["M1"], online=False
    )
    assert any(f.code == "CLAIM UNSUPPORTED" and "no manuscript section" in f.detail
               for f in findings)
