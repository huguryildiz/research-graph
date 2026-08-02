#!/usr/bin/env python3
"""Generate architecture.html contract data from the executable kit.

Only the marked JavaScript data block is replaced. The SVG, CSS, geometry,
interaction code and prose remain byte-for-byte untouched.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rgraph.config import ARTIFACTS, Gate, Kit, load_kit  # noqa: E402

HTML = ROOT / "architecture.html"
BEGIN = "/* BEGIN GENERATED CONTRACT DATA */"
END = "/* END GENERATED CONTRACT DATA */"

VISUAL_OWNER_FOR_ROLE = {
    "retrieval": "sol",
    "planning": "opus",
    "execution": "sonnet",
    "verification": "terra",
    "synthesis": "fable",
}
VISUAL_GATE_OWNER = {"human": "human", "reviewer": "reviewer", "verification": "terra"}
CONTRACT_ENDPOINTS = {
    "H1": ("human", "sol"),
    "E1": ("reviewer", "c2"),
    "H2": ("c2", "opus"),
    "H3": ("c3", "c4"),
    "T1": ("reviewer", "c5"),
    "H4": ("c5", "sonnet"),
    "T2": ("c6", "terra"),
    "V1": ("c10", "fable"),
    "M1": ("reviewer", "c12"),
    "FINAL": ("c12", "human"),
}
VISUAL_TARGET = {
    "u01": "c1",
    "u03": "c3",
    "u04": "c4",
    "u05": "c5",
    "u06": "c6",
    "u08": "c8",
    "u11": "c11",
    "H2": "c2",
    "H4": "c5",
    "FINAL": "human",
}
ROUTE_TARGET_OVERRIDE = {
    ("H1", "pass"): "sol",
    ("H1", "revise"): "problem_spec",
    ("H2", "pass"): "opus",
    ("T1", "revise"): "opus",
    ("H4", "pass"): "sonnet",
    ("V1", "pass"): "fable",
}
DISPLAY_REQUIRED_FIELDS = {
    "run_manifest": ("replications", "seeds"),
    "release_manifest": ("revision_counts", "scope_changes", "outcome"),
}


def _js_key(value: str) -> str:
    return value if re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", value) else _js(value)


def _js(value) -> str:
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "null"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_js(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{" + ",".join(f"{_js_key(str(key))}:{_js(item)}" for key, item in value.items()) + "}"
    return str(value)


def _visual_artifact_owner(kit: Kit, artifact_id: str) -> str:
    producer = kit.graph.producer_of(artifact_id)
    if producer is None:
        raise ValueError(f"artifact has no producer: {artifact_id}")
    if producer.id == "human":
        return "human"
    try:
        return VISUAL_OWNER_FOR_ROLE[producer.role_name]
    except KeyError as exc:
        raise ValueError(f"artifact producer has no visual role: {producer.id}") from exc


def _schema_required_fields(artifact_id: str) -> set[str]:
    schema = json.loads((ROOT / "schemas" / f"{artifact_id}.schema.json").read_text())
    return set(schema.get("properties", {}).get("body", {}).get("required", []))


def _artifact(kit: Kit, artifact_id: str) -> dict:
    record = {
        "id": artifact_id,
        "owner": _visual_artifact_owner(kit, artifact_id),
        "immutable": True,
    }
    fields = DISPLAY_REQUIRED_FIELDS.get(artifact_id, ())
    missing = set(fields) - _schema_required_fields(artifact_id)
    if missing:
        raise ValueError(f"display-required fields absent from {artifact_id} schema: {sorted(missing)}")
    if fields:
        record["requiredFields"] = list(fields)
    return record


def _visual_route(gate: Gate, outcome: str, route):
    override = ROUTE_TARGET_OVERRIDE.get((gate.id, outcome))
    if isinstance(route, dict):
        return {key: override or _visual_route_target(target) for key, target in route.items()}
    return override or _visual_route_target(route)


def _visual_route_target(target: str) -> str:
    if target.startswith("terminal:"):
        return target
    try:
        return VISUAL_TARGET[target]
    except KeyError as exc:
        raise ValueError(f"route target has no visual node: {target}") from exc


def _visual_producer(kit: Kit, gate: Gate) -> str | None:
    if gate.producer is None:
        return None
    node = kit.graph.nodes[gate.producer]
    return VISUAL_OWNER_FOR_ROLE[node.role_name]


def _contract(kit: Kit, gate: Gate) -> dict:
    try:
        endpoint_from, endpoint_to = CONTRACT_ENDPOINTS[gate.id]
        owner = VISUAL_GATE_OWNER[gate.owner]
    except KeyError as exc:
        raise ValueError(f"gate has no visual adapter: {gate.id}") from exc
    record = {
        "id": gate.id,
        "kind": "agent_challenge" if gate.kind == "challenge" else "human_gate",
        "owner": owner,
        "from": endpoint_from,
        "to": endpoint_to,
        "short": gate.title,
        "criterion": gate.criterion,
        "inputs": list(gate.inputs),
        "requires": [f"{required}:pass" for required in gate.requires],
        "outcomes": list(gate.outcomes),
        "maxRevisions": gate.max_revisions,
    }
    if gate.kind == "challenge":
        policy = {
            "separateContext": True,
            "immutableInputs": True,
            "producer": _visual_producer(kit, gate),
            "requiredSeparation": gate.separation_required,
            "preferredSeparation": gate.separation_preferred,
        }
        if gate.distinct_actor_from:
            policy["distinctActorFrom"] = list(gate.distinct_actor_from)
        record["policy"] = policy
    if gate.freezes:
        record["freezes"] = gate.freezes
    if gate.checks:
        record["checks"] = list(gate.checks)
    if gate.proves:
        record["proves"] = list(gate.proves)
    if gate.produces:
        record["outputs"] = {
            outcome: gate.produces
            for outcome, target in gate.routes.items()
            if isinstance(target, str) and target.startswith("terminal:")
        }
    record["routes"] = {
        outcome: _visual_route(gate, outcome, route)
        for outcome, route in gate.routes.items()
    }
    return record


def generated_data() -> str:
    kit = load_kit(ROOT, assignment="assignment.example.yaml")
    artifacts = [_artifact(kit, artifact_id) for artifact_id in ARTIFACTS]
    contracts = [_contract(kit, gate) for gate in kit.gates.values()]
    artifact_lines = "\n".join(f" {_js(record)}," for record in artifacts).rstrip(",")
    contract_lines = "\n".join(f" {_js(record)}," for record in contracts).rstrip(",")
    return (
        "// Generated by scripts/generate_architecture_contracts.py; do not edit by hand.\n"
        f"const ARTIFACTS=[\n{artifact_lines}\n];\n\n"
        f"const CONTRACTS=[\n{contract_lines}\n];"
    )


def render_html(current: str) -> str:
    try:
        start = current.index(BEGIN) + len(BEGIN)
        end = current.index(END, start)
    except ValueError as exc:
        raise ValueError("architecture.html generated-data markers are missing") from exc
    return current[:start] + "\n" + generated_data() + "\n" + current[end:]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if architecture.html is stale")
    args = parser.parse_args(argv)
    current = HTML.read_text(encoding="utf-8")
    rendered = render_html(current)
    if args.check:
        if rendered != current:
            print("architecture.html contract data is stale; run this generator", file=sys.stderr)
            return 1
        return 0
    HTML.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
