import pathlib

import pytest

from rgraph.config import ARTIFACTS
from rgraph.hashing import content_hash
from rgraph.schemas import registry

ROOT = pathlib.Path(__file__).resolve().parents[1]


def envelope(artifact_id: str, body: dict, inputs=()) -> dict:
    return {
        "artifact_id": artifact_id,
        "version": 1,
        "produced_by": {"role": "retrieval", "identity": "codex/gpt-5.6",
                        "provider": "codex", "model": "gpt-5.6"},
        "produced_at": "2026-07-31T09:00:00Z",
        "inputs": list(inputs),
        "content_hash": content_hash(body),
        "body": body,
    }


BODIES = {
    "problem_spec": {
        "question": "Does a learned channel estimator beat LMMSE at low SNR?",
        "scope": {"in_scope": ["OFDM pilot-aided estimation"], "out_of_scope": ["mmWave"]},
        "constraints": ["one workstation"], "success_criteria": ["paired comparison"],
        "mode": "GUIDED",
    },
    "governance_record": {
        "ethics_applicable": False, "ethics_reference": None,
        "data_governance": ["synthetic channels only"], "legal_notes": [],
        "approvals": [{"name": "H. U. Yildiz", "date": "2026-07-31", "note": "scope approved"}],
    },
    "search_protocol": {
        "databases": ["Crossref", "arXiv"],
        "queries": [{"db": "Crossref", "query": "deep learning channel estimation OFDM",
                     "executed_at": "2026-07-31T08:00:00Z", "hits": 214}],
        "inclusion_criteria": ["reports SNR sweep"], "exclusion_criteria": ["no baseline"],
        "date_range": {"from": "2017-01-01", "to": "2026-07-31"},
    },
    "corpus_snapshot": {
        "count": 1,
        "sources": [{"source_id": "s-01", "doi": "10.1109/LWC.2017.2757490",
                     "title": "Power of Deep Learning for Channel Estimation",
                     "authors": ["H. Ye", "G. Y. Li", "B. Juang"], "year": 2018,
                     "venue": "IEEE Wireless Communications Letters", "url": None,
                     "retracted": False, "retrieved_at": "2026-07-31T08:05:00Z"}],
    },
    "kg_snapshot": {
        "entities": [{"entity_id": "e-01", "type": "method", "label": "LMMSE estimator"}],
        "claims": [{"claim_id": "kc-01", "text": "Deep estimators degrade less at low SNR",
                    "entity_ids": ["e-01"]}],
        "edges": [{"edge_id": "ke-01", "from_claim": "kc-01", "relation": "supports",
                   "source_id": "s-01", "locator": {"kind": "section", "value": "IV-B"}}],
        "contradictions": [],
    },
    "evidence_matrix": {
        "rows": [{"claim_id": "c-01", "source_id": "s-01",
                  "locator": {"kind": "figure", "value": "Fig. 3"},
                  "method": "simulation", "result": "2.1 dB MSE gain at 0 dB SNR",
                  "strength": "moderate", "contradiction_of": []}],
        "gaps": [{"description": "no paired seeds reported", "blocking": False}],
    },
    "hypothesis_registry": {
        "hypotheses": [{"hypothesis_id": "h-01",
                        "statement": "A learned estimator lowers MSE below LMMSE at SNR <= 0 dB",
                        "falsifiable_prediction": "paired MSE difference CI excludes zero",
                        "novelty_status": "replication", "feasibility": "high",
                        "discriminating_evidence": ["c-01"], "decision": "accepted"}],
    },
    "design_protocol": {
        "objectives": ["quantify the low-SNR gap"], "methods": ["Monte Carlo over a Rayleigh tap model"],
        "experiments": [{"experiment_id": "x-01", "hypothesis_id": "h-01",
                         "factors": ["snr_db", "estimator"], "metrics": ["mse"]}],
        "resources": {"compute": "1 CPU core", "data": "synthetic", "time": "10 minutes"},
        "risks": ["baseline mis-tuning"],
    },
    "frozen_protocol": {
        "frozen_at": "2026-07-31T11:00:00Z", "approved_by": "H. U. Yildiz",
        "hypotheses": ["h-01"],
        "outcomes": [{"metric": "mse", "direction": "lower_is_better", "threshold": None}],
        "exclusions": ["diverged runs"], "analysis_plan": "paired difference per seed",
        "multiplicity_plan": "Holm over 5 SNR points", "stopping_rule": "fixed 20 replications",
        "replications": 20, "seeds": list(range(41, 61)),
        "data_access": "generated locally", "compute_authorisation": "self",
    },
    "code_commit": {"repo": "https://github.com/huguryildiz/research-graph",
                    "commit": "9f2c1ab", "dirty": False,
                    "entrypoint": "code/estimator_bench.py",
                    "files": [{"path": "code/estimator_bench.py", "sha256": "0" * 64}]},
    "environment_lock": {"python": "3.11.9", "platform": "macOS-15.5-arm64",
                         "packages": [{"name": "numpy", "version": "2.1.0"}],
                         "lock_sha256": "1" * 64},
    "data_manifest": {"datasets": [{"dataset_id": "d-01", "path": "data/channels.jsonl",
                                    "sha256": "2" * 64, "bytes": 40960, "rows": 2000,
                                    "license": None, "generated": True}]},
    "run_manifest": {"replications": 2, "seeds": [41, 42],
                     "runs": [{"run_id": "run_20260731_041", "seed": 41, "config_sha256": "3" * 64,
                               "started_at": "2026-07-31T12:00:00Z",
                               "finished_at": "2026-07-31T12:00:04Z", "status": "ok"},
                              {"run_id": "run_20260731_042", "seed": 42, "config_sha256": "3" * 64,
                               "started_at": "2026-07-31T12:00:04Z",
                               "finished_at": "2026-07-31T12:00:08Z", "status": "ok"}],
                     "failures": 0},
    "raw_results": {"payload_path": "raw_results.jsonl", "payload_sha256": "4" * 64,
                    "records": 2, "run_ids": ["run_20260731_041", "run_20260731_042"],
                    "record_fields": [{"name": "run_id", "type": "string"},
                                      {"name": "mse", "type": "number"}]},
    "reproduction_report": {"reproduced": [{"run_id": "run_20260731_041",
                                            "original_sha256": "5" * 64,
                                            "reproduced_sha256": "5" * 64, "match": True}],
                            "environment_match": True, "reproduction_rate": 1.0, "notes": []},
    "statistical_report": {
        "estimates": [{"result_id": "r-01", "metric": "mse_delta_db", "estimate": 2.1,
                       "ci_lower": 1.4, "ci_upper": 2.8, "ci_level": 0.95, "n": 2,
                       "method": "paired bootstrap",
                       "assumptions_checked": [{"name": "pairing", "passed": True}]}],
        "multiplicity_correction": "Holm",
        "effect_sizes": [{"result_id": "r-01", "name": "cohen_d", "value": 1.2}]},
    "verification_report": {
        "findings": [{"finding_id": "f-01", "severity": "minor", "text": "narrow SNR grid"}],
        "uncertainty": ["seed variance dominates below -5 dB"],
        "failures": {"total": 0, "accounted": 0},
        "limitations": ["synthetic channels only"], "recommendations": ["widen the grid"],
        "denominators": [{"name": "converged runs", "numerator": 2, "denominator": 2}]},
    "claim_evidence_map": {"claims": [{"claim_id": "c-03",
                                       "text": "The learned estimator lowers MSE at 0 dB SNR.",
                                       "location": {"file": "manuscript.md", "section": "Results"},
                                       "supported_by": {"result_ids": ["r-01"], "source_ids": []},
                                       "scope": "within_evidence"}]},
    "figure_registry": {"figures": [{"figure_id": "fig-01", "caption": "MSE versus SNR",
                                     "source_data": {"artifact_id": "statistical_report",
                                                     "selector": "estimates[0]"},
                                     "script": {"path": "code/plot_mse.py", "sha256": "6" * 64},
                                     "result_ids": ["r-01"]}]},
    "manuscript": {"payload_path": "manuscript.md", "payload_sha256": "7" * 64,
                   "title": "Learned channel estimation at low SNR",
                   "sections": [{"id": "sec-results", "heading": "Results", "claim_ids": ["c-03"]}],
                   "word_count": 3200, "references": ["s-01"]},
    "release_manifest": {"outcome": "release", "decided_by": "H. U. Yildiz",
                         "decided_at": "2026-07-31T18:00:00Z",
                         "revision_counts": {"E1": 1}, "scope_changes": [],
                         "separation_levels": {"M1": "separate_provider"},
                         "caveats": ["V1 decided at CONTEXT ONLY"],
                         "not_established": ["Scientific correctness was not determined"]},
}


def test_envelope_accepts_a_well_formed_document():
    assert registry(ROOT).validate("problem_spec",
                                   envelope("problem_spec", BODIES["problem_spec"])) == []


def test_missing_provenance_field_is_reported_with_a_path():
    doc = envelope("problem_spec", BODIES["problem_spec"])
    del doc["inputs"]
    assert any("inputs" in e.message for e in registry(ROOT).validate("problem_spec", doc))


def test_wrong_artifact_id_is_rejected():
    doc = envelope("evidence_matrix", BODIES["problem_spec"])
    assert registry(ROOT).validate("problem_spec", doc) != []


def test_malformed_hash_is_rejected():
    doc = envelope("problem_spec", BODIES["problem_spec"])
    doc["content_hash"] = "md5:abc"
    assert registry(ROOT).validate("problem_spec", doc) != []


def test_gate_record_schema_round_trips():
    record = {
        "gate_id": "E1", "outcome": "pass", "decided_at": "2026-07-31T10:00:00Z",
        "decided_by": {"role": "reviewer", "identity": "grok/grok-5"},
        "producer_identity": "codex/gpt-5.6",
        "separation_level": "separate_provider", "separation_caveat": False,
        "inputs": [{"artifact_id": "evidence_matrix", "content_hash": content_hash({"x": 1})}],
        "checks": [{"name": "source_support", "status": "PASS", "detail": "14 of 14 claims"}],
        "reason": None, "findings": [],
        "revision_budget": {"max": 3, "used": 0},
    }
    assert registry(ROOT).validate("gate_record", record) == []


@pytest.mark.parametrize("artifact_id", sorted(BODIES))
def test_each_schema_accepts_its_reference_body(artifact_id):
    reg = registry(ROOT)
    assert reg.has(artifact_id)
    assert reg.validate(artifact_id, envelope(artifact_id, BODIES[artifact_id])) == []


def test_all_twenty_one_artifacts_have_a_schema():
    reg = registry(ROOT)
    assert len(ARTIFACTS) == 21
    assert [a for a in ARTIFACTS if not reg.has(a)] == []


def test_kg_edge_without_a_locator_is_rejected():
    body = dict(BODIES["kg_snapshot"])
    body["edges"] = [{"edge_id": "ke-01", "from_claim": "kc-01",
                      "relation": "supports", "source_id": "s-01"}]
    assert registry(ROOT).validate("kg_snapshot", envelope("kg_snapshot", body)) != []


def test_kg_edge_with_an_empty_locator_value_is_rejected():
    body = dict(BODIES["kg_snapshot"])
    body["edges"] = [{"edge_id": "ke-01", "from_claim": "kc-01", "relation": "supports",
                      "source_id": "s-01", "locator": {"kind": "page", "value": ""}}]
    assert registry(ROOT).validate("kg_snapshot", envelope("kg_snapshot", body)) != []


def test_frozen_protocol_needs_at_least_one_seed():
    body = {**BODIES["frozen_protocol"], "seeds": []}
    assert registry(ROOT).validate("frozen_protocol", envelope("frozen_protocol", body)) != []


def test_run_manifest_rejects_duplicate_seeds():
    body = {**BODIES["run_manifest"], "seeds": [41, 41]}
    assert registry(ROOT).validate("run_manifest", envelope("run_manifest", body)) != []


def test_statistical_report_requires_a_confidence_interval():
    estimate = {k: v for k, v in BODIES["statistical_report"]["estimates"][0].items()
                if k not in ("ci_lower", "ci_upper")}
    body = {**BODIES["statistical_report"], "estimates": [estimate]}
    assert registry(ROOT).validate("statistical_report", envelope("statistical_report", body)) != []


def test_claim_scope_is_a_closed_enum():
    claim = {**BODIES["claim_evidence_map"]["claims"][0], "scope": "obviously_true"}
    body = {"claims": [claim]}
    assert registry(ROOT).validate("claim_evidence_map", envelope("claim_evidence_map", body)) != []


def test_release_manifest_keeps_the_claim_boundary_sentence():
    body = {**BODIES["release_manifest"], "not_established": []}
    assert registry(ROOT).validate("release_manifest", envelope("release_manifest", body)) != []
