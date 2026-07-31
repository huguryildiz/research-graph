"""Layer 1: static checks over graph.yaml and gates.yaml. No run directory needed."""

from __future__ import annotations

from dataclasses import dataclass

from rgraph.config import Kit

CHECKS = ("type_match", "acyclic", "bounded", "reachable", "dead_node")

_CLEAN = {
    "type_match": "Every handoff carries an artifact its source declares.",
    "acyclic": "Handoff edges form a DAG; cycles occur only on return edges.",
    "bounded": "Every return edge has a revision budget.",
    "reachable": "Every gate input has a handoff path from its producer.",
    "dead_node": "No node produces an artifact nobody reads.",
}


@dataclass(frozen=True)
class Finding:
    check: str
    status: str
    subject: str
    detail: str
    fix: str = ""


def _type_match(kit: Kit) -> list[Finding]:
    out: list[Finding] = []
    for edge in kit.graph.edges:
        if edge.kind != "handoff":
            continue
        source = kit.graph.node(edge.frm)
        if source.kind not in ("agent", "human"):
            continue
        for artifact in edge.carries:
            if artifact not in source.produces:
                out.append(Finding(
                    "type_match", "FAIL", f"{edge.frm} -> {edge.to}",
                    f"edge carries '{artifact}', which '{edge.frm}' does not produce",
                    f"add '{artifact}' to the produces list of '{edge.frm}', "
                    f"or drop it from carries",
                ))
    return out


def _acyclic(kit: Kit) -> list[Finding]:
    adjacency: dict[str, list[str]] = {node: [] for node in kit.graph.nodes}
    for edge in kit.graph.edges:
        if edge.kind == "handoff":
            adjacency[edge.frm].append(edge.to)
    state: dict[str, int] = {}
    out: list[Finding] = []

    def visit(node: str, path: list[str]) -> None:
        state[node] = 1
        for nxt in adjacency[node]:
            if state.get(nxt) == 1:
                cycle = (
                    " -> ".join(path[path.index(nxt):] + [nxt])
                    if nxt in path else f"{node} -> {nxt}"
                )
                out.append(Finding(
                    "acyclic", "FAIL", nxt, f"handoff cycle: {cycle}",
                    "make the closing edge a 'return' edge with a budget",
                ))
            elif state.get(nxt) is None:
                visit(nxt, path + [nxt])
        state[node] = 2

    for node in kit.graph.nodes:
        if state.get(node) is None:
            visit(node, [node])
    return out


def _bounded(kit: Kit) -> list[Finding]:
    return [
        Finding(
            "bounded", "FAIL", f"{edge.frm} -> {edge.to}",
            "return edge has no budget (or a budget below 1)",
            "add 'budget: 3' to the edge",
        )
        for edge in kit.graph.edges
        if edge.kind == "return" and not (isinstance(edge.budget, int) and edge.budget >= 1)
    ]


def _handoff_ancestors(kit: Kit, target: str) -> set[str]:
    incoming: dict[str, list[str]] = {node: [] for node in kit.graph.nodes}
    for edge in kit.graph.edges:
        if edge.kind == "handoff":
            incoming[edge.to].append(edge.frm)
    seen: set[str] = set()
    stack = list(incoming.get(target, []))
    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        stack.extend(incoming.get(node, []))
    return seen


def _reachable(kit: Kit) -> list[Finding]:
    out: list[Finding] = []
    for gate in kit.gates.values():
        ancestors = _handoff_ancestors(kit, gate.id)
        for artifact in gate.inputs:
            producer = kit.graph.producer_of(artifact)
            if producer is None:
                out.append(Finding(
                    "reachable", "FAIL", f"{gate.id}/{artifact}",
                    f"no node produces '{artifact}'",
                    f"add '{artifact}' to some node's produces list",
                ))
            elif producer.id not in ancestors:
                out.append(Finding(
                    "reachable", "FAIL", f"{gate.id}/{artifact}",
                    f"'{artifact}' is produced by '{producer.id}', "
                    f"which has no handoff path to gate {gate.id}",
                    f"add a handoff edge chain from '{producer.id}' to '{gate.id}'",
                ))
    return out


def _dead_node(kit: Kit) -> list[Finding]:
    carried: set[str] = set()
    for edge in kit.graph.edges:
        if edge.kind == "handoff":
            carried.update(edge.carries)
    for gate in kit.gates.values():
        carried.update(gate.inputs)
    out: list[Finding] = []
    for node in kit.graph.nodes.values():
        if node.kind not in ("agent", "human"):
            continue
        if not kit.graph.out_edges(node.id):
            out.append(Finding(
                "dead_node", "FAIL", node.id, "node has no outgoing edge",
                "connect it with a handoff or read_only edge, or remove it",
            ))
        for artifact in node.produces:
            if artifact not in carried:
                out.append(Finding(
                    "dead_node", "FAIL", f"{node.id}/{artifact}",
                    f"'{artifact}' is produced but never carried on a handoff "
                    f"and never read by a gate",
                    f"carry '{artifact}' on an outgoing handoff, or stop producing it",
                ))
    return out


_CHECKS = {
    "type_match": _type_match,
    "acyclic": _acyclic,
    "bounded": _bounded,
    "reachable": _reachable,
    "dead_node": _dead_node,
}


def run_static(kit: Kit) -> list[Finding]:
    findings: list[Finding] = []
    for name in CHECKS:
        failures = _CHECKS[name](kit)
        findings.extend(failures or [Finding(name, "PASS", "graph.yaml", _CLEAN[name])])
    return findings
