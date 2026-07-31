import pathlib

from rgraph.config import Edge, Graph, Kit, Node, load_kit
from rgraph.lint import CHECKS, run_static

ROOT = pathlib.Path(__file__).resolve().parents[1]


def failures(findings):
    return [f for f in findings if f.status == "FAIL"]


def _kit_with(graph: Graph) -> Kit:
    kit = load_kit(ROOT)
    return Kit(root=kit.root, graph=graph, providers=kit.providers,
               assignment=kit.assignment, gates=kit.gates)


def test_reference_graph_is_clean():
    findings = run_static(load_kit(ROOT))
    assert failures(findings) == []
    assert {f.check for f in findings} == set(CHECKS)


def test_type_match_catches_an_unproduced_artifact():
    kit = load_kit(ROOT)
    broken = Graph(
        nodes=kit.graph.nodes,
        edges=kit.graph.edges + (Edge("u03", "u04", "handoff", ("manuscript",)),),
    )
    found = failures(run_static(_kit_with(broken)))
    assert any(f.check == "type_match" and "manuscript" in f.detail for f in found)


def test_acyclic_catches_a_handoff_cycle():
    kit = load_kit(ROOT)
    broken = Graph(
        nodes=kit.graph.nodes,
        edges=kit.graph.edges + (Edge("u12", "u11", "handoff", ()),),
    )
    assert any(f.check == "acyclic" for f in failures(run_static(_kit_with(broken))))


def test_bounded_catches_a_budgetless_return():
    kit = load_kit(ROOT)
    edges = tuple(
        Edge(e.frm, e.to, e.kind, e.carries, None) if e.kind == "return" else e
        for e in kit.graph.edges
    )
    found = failures(run_static(_kit_with(Graph(kit.graph.nodes, edges))))
    assert any(f.check == "bounded" for f in found)


def test_dead_node_catches_an_artifact_nobody_reads():
    kit = load_kit(ROOT)
    nodes = dict(kit.graph.nodes)
    nodes["u09"] = Node(
        id="u09", kind="agent", stage="verify", role="roles/verification.md",
        title="Statistical verification", produces=("statistical_report", "figure_registry"),
    )
    nodes["u11"] = Node(
        id="u11", kind="agent", stage="write", role="roles/synthesis.md",
        title="Result synthesis & visualization", produces=(),
    )
    gates = {gid: g for gid, g in kit.gates.items()}
    edges = tuple(
        e for e in kit.graph.edges if not (e.frm == "u11" and e.to == "u12")
    )
    broken = Kit(root=kit.root, graph=Graph(nodes, edges), providers=kit.providers,
                 assignment=kit.assignment, gates=gates)
    found = failures(run_static(broken))
    assert any(f.check == "dead_node" for f in found)


def test_reachable_catches_a_gate_input_with_no_path():
    kit = load_kit(ROOT)
    edges = tuple(e for e in kit.graph.edges if not (e.frm == "u01" and e.to == "u02"))
    found = failures(run_static(_kit_with(Graph(kit.graph.nodes, edges))))
    assert any(f.check == "reachable" and f.subject.startswith("E1") for f in found)
