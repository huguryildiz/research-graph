"""`architecture.html` is a hand-drawn plate, not a render of `graph.yaml`.

Two hands write the same graph, so the two can drift, and a repository whose
first static check is "delete the fake edge" does not get to leave its own
diagram unchecked. These tests diff the plate's contract table against the
configuration the CLI actually executes.

One divergence is deliberate and recorded in the README under "Deviations from
the design document": the plate's artifact registry predates `kg_snapshot`, so
it holds 20 entries where the kit holds 21. It is named here rather than
tolerated silently, and the test fails if it ever grows a second member.
"""

import pathlib
import re

from rgraph.config import ARTIFACTS, load_kit

ROOT = pathlib.Path(__file__).resolve().parents[1]
PLATE = (ROOT / "architecture.html").read_text(encoding="utf-8")

DECLARED_DEVIATION = {"kg_snapshot"}


def _block(start: str, end: str) -> str:
    return PLATE[PLATE.index(start):PLATE.index(end)]


def _contracts() -> str:
    return _block("const CONTRACTS=[", "/* ═════ geometry ═════ */")


def _contract_field(gate_id: str, field: str) -> set[str]:
    match = re.search(r'\{id:"%s".*?%s:\[(.*?)\]' % (gate_id, field), _contracts(), re.S)
    return set(re.findall(r'"([a-z_]+)"', match.group(1))) if match else set()


def test_the_plate_and_the_kit_name_the_same_gates():
    plate = set(re.findall(r'\{id:"([A-Z]+[0-9]*)",kind:', _contracts()))
    assert plate == set(load_kit(ROOT).gates)


def test_every_gate_reads_the_same_inputs_on_the_plate_as_in_gates_yaml():
    kit = load_kit(ROOT)
    for gate_id, gate in kit.gates.items():
        drift = _contract_field(gate_id, "inputs") ^ set(gate.inputs)
        assert drift <= DECLARED_DEVIATION, (gate_id, sorted(drift))


def test_the_plate_artifact_registry_matches_the_kit():
    registry = _block("const ARTIFACTS=[", "const CONTRACTS=[")
    plate = set(re.findall(r'\{id:"([a-z_]+)"', registry))
    assert set(ARTIFACTS) - plate == DECLARED_DEVIATION
    assert plate - set(ARTIFACTS) == set()


def test_the_mobile_audit_trail_lists_every_artifact_the_plate_registers():
    """The phone view states the registry in prose, and prose drifts on its own.

    It carried 19 of the plate's 20 entries: `design_protocol` was missing from
    the list while the same file's T1 contract read it as an input.
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
