"""Keep the hand-drawn architecture plate aligned with the executable kit.

Visual node names differ from the provider-neutral unit IDs, but duplicated
artifact ownership and gate semantics must agree after that naming layer is
normalised. No diagram/configuration divergence is accepted silently.
"""

import pathlib
import re

from rgraph.config import ARTIFACTS, load_kit

ROOT = pathlib.Path(__file__).resolve().parents[1]
PLATE = (ROOT / "architecture.html").read_text(encoding="utf-8")
GRAPH = (ROOT / "graph.yaml").read_text(encoding="utf-8")

VISUAL_OWNER_FOR_ROLE = {
    "retrieval": "sol",
    "planning": "opus",
    "execution": "sonnet",
    "verification": "terra",
    "synthesis": "fable",
}

PASS_ROUTES = {
    "H1": ("u01", "sol"),
    "E1": ("H2", "c2"),
    "H2": ("u03", "opus"),
    "H3": ("u04", "c4"),
    "T1": ("H4", "c5"),
    "H4": ("u06", "sonnet"),
    "T2": ("u08", "c8"),
    "V1": ("u11", "fable"),
    "M1": ("FINAL", "human"),
}

DEFAULT_REVISION_ROUTES = {
    "H1": ("human", "problem_spec"),
    "E1": ("u01", "c1"),
    "H2": ("u01", "c1"),
    "H3": ("u03", "c3"),
    "T1": ("u03", "opus"),
    "H4": ("u05", "c5"),
    "T2": ("u06", "c6"),
    "V1": ("u08", "c8"),
    "M1": ("u11", "c11"),
}


def _block(start: str, end: str) -> str:
    return PLATE[PLATE.index(start):PLATE.index(end)]


def _contracts() -> str:
    return _block("const CONTRACTS=[", "/* ═════ geometry ═════ */")


def _contract(gate_id: str) -> str:
    contracts = _contracts()
    start = contracts.index(f'{{id:"{gate_id}"')
    next_contract = contracts.find('\n {id:"', start + 1)
    end = next_contract if next_contract >= 0 else contracts.index("\n];", start)
    return contracts[start:end]


def _contract_field(gate_id: str, field: str) -> set[str]:
    match = re.search(r'%s:\[(.*?)\]' % field, _contract(gate_id), re.S)
    return set(re.findall(r'"([A-Za-z0-9_:-]+)"', match.group(1))) if match else set()


def _contract_scalar(gate_id: str, field: str) -> str:
    match = re.search(rf'{field}:"([a-z0-9_-]+)"', _contract(gate_id))
    assert match, (gate_id, field)
    return match.group(1)


def _default_target(route):
    return route.get("default") if isinstance(route, dict) else route


def test_the_plate_and_the_kit_name_the_same_gates():
    plate = set(re.findall(r'\{id:"([A-Z]+[0-9]*)",kind:', _contracts()))
    assert plate == set(load_kit(ROOT).gates)


def test_visible_embedded_and_graph_reference_versions_match():
    title = re.search(r"Reference Architecture (v[0-9.]+)", PLATE)
    mobile = re.search(r"reference architecture · (v[0-9.]+)", PLATE)
    embedded = re.search(r'__workflowSpec=\{version:"(v[0-9.]+)', PLATE)
    graph = re.search(r"architecture\.html (v[0-9.]+)", GRAPH)
    assert title and mobile and embedded and graph
    assert {title.group(1), mobile.group(1), embedded.group(1), graph.group(1)} == {"v5.2"}


def test_every_gate_reads_the_same_inputs_on_the_plate_as_in_gates_yaml():
    kit = load_kit(ROOT)
    for gate_id, gate in kit.gates.items():
        assert _contract_field(gate_id, "inputs") == set(gate.inputs), gate_id


def test_the_plate_artifact_registry_matches_the_kit():
    registry = _block("const ARTIFACTS=[", "const CONTRACTS=[")
    plate = set(re.findall(r'\{id:"([a-z_]+)"', registry))
    assert plate == set(ARTIFACTS)


def test_artifact_owners_match_the_executable_producer_roles():
    kit = load_kit(ROOT)
    registry = _block("const ARTIFACTS=[", "const CONTRACTS=[")
    plate = dict(re.findall(r'\{id:"([a-z_]+)",owner:"([a-z]+)"', registry))
    expected = {}
    for artifact_id in ARTIFACTS:
        producer = kit.graph.producer_of(artifact_id)
        assert producer is not None, artifact_id
        expected[artifact_id] = (
            "human" if producer.id == "human"
            else VISUAL_OWNER_FOR_ROLE[producer.role_name]
        )
    assert plate == expected


def test_gate_owners_prerequisites_outcomes_and_budgets_match():
    kit = load_kit(ROOT)
    visual_owner = {"human": "human", "reviewer": "reviewer", "terra": "verification"}
    for gate_id, gate in kit.gates.items():
        assert visual_owner[_contract_scalar(gate_id, "owner")] == gate.owner
        requires = {value.removesuffix(":pass") for value in _contract_field(gate_id, "requires")}
        assert requires == set(gate.requires), gate_id
        assert _contract_field(gate_id, "outcomes") == set(gate.outcomes), gate_id
        revisions = re.search(r"maxRevisions:(\d+)", _contract(gate_id))
        assert revisions and int(revisions.group(1)) == gate.max_revisions, gate_id


def test_pass_and_default_revision_routes_match_the_executable_graph():
    kit = load_kit(ROOT)
    assert set(PASS_ROUTES) == set(kit.gates) - {"FINAL"}
    assert set(DEFAULT_REVISION_ROUTES) == set(kit.gates) - {"FINAL"}
    for gate_id, (kit_target, plate_target) in PASS_ROUTES.items():
        assert kit.gates[gate_id].routes["pass"] == kit_target
        assert f'pass:"{plate_target}"' in _contract(gate_id)
    for gate_id, (kit_target, plate_target) in DEFAULT_REVISION_ROUTES.items():
        assert _default_target(kit.gates[gate_id].routes["revise"]) == kit_target
        contract = _contract(gate_id)
        assert (
            f'revise:"{plate_target}"' in contract
            or f'default:"{plate_target}"' in contract
        ), gate_id


def test_final_routes_match_the_executable_graph():
    final = load_kit(ROOT).gates["FINAL"]
    contract = _contract("FINAL")
    expected = {
        "release": ("terminal:release", "terminal:release"),
        "revise": ("u11", "c11"),
        "narrow": ("u04", "c4"),
        "null-result": ("terminal:null-result", "terminal:null-result"),
        "stop": ("terminal:stop", "terminal:stop"),
    }
    for outcome, (kit_target, plate_target) in expected.items():
        assert _default_target(final.routes[outcome]) == kit_target
        key = f'"{outcome}"' if "-" in outcome else outcome
        assert (
            f'{key}:"{plate_target}"' in contract
            or f'{key}:' in contract and f'default:"{plate_target}"' in contract
        ), outcome


def test_the_mobile_audit_trail_lists_every_artifact_the_plate_registers():
    """The phone view states the registry in prose, and prose drifts on its own.

    This once omitted `design_protocol`; the assertion keeps prose and the
    executable registry synchronized.
    """
    opening = PLATE.index('<div class="artifact-list">')
    listed = PLATE[opening:PLATE.index("</div>", opening)]
    mobile = {name.strip() for line in re.findall(r"<code>(.*?)</code>", listed, re.S)
              for name in line.split("·")}
    registry = _block("const ARTIFACTS=[", "const CONTRACTS=[")
    assert mobile == set(re.findall(r'\{id:"([a-z_]+)"', registry))


def test_every_typed_revision_reason_on_the_plate_is_one_the_graph_can_issue():
    """A plate return the machine cannot emit is exactly the fake edge."""
    kit = load_kit(ROOT)
    drawn = re.findall(r'\{reason:"([a-z_]+)",gate:"([A-Z]+[0-9]*)"', PLATE)
    assert drawn, "the plate draws no typed returns at all"
    for reason, gate_id in drawn:
        assert gate_id in kit.gates, reason
        returns = {
            carried
            for edge in kit.graph.out_edges(gate_id) if edge.kind == "return"
            for carried in edge.carries
        }
        assert reason in returns, (gate_id, reason, sorted(returns))
