"""Derive the next allowed action from the graph and the current run."""

from __future__ import annotations

from dataclasses import dataclass

from rgraph.config import Kit, Node
from rgraph.gates import evaluate_gate
from rgraph.hashing import file_hash
from rgraph.provenance import stale_artifacts
from rgraph.run import Run

TERMINAL_FINAL_OUTCOMES = frozenset({"release", "null-result", "stop"})


@dataclass(frozen=True)
class WorkflowAction:
    kind: str
    target: str | None
    command: str | None
    detail: str


def _terminal_final_action(run: Run) -> WorkflowAction | None:
    """A recorded terminal human decision closes the run, even after `stop`."""
    record = run.gate_record("FINAL")
    outcome = record.get("outcome") if record else None
    if outcome in TERMINAL_FINAL_OUTCOMES and run.get("release_manifest").present:
        return WorkflowAction(
            "complete", "FINAL", None, f"none — run closed with {outcome}",
        )
    return None


def unit_state(run: Run, unit: Node, stale: dict | None = None) -> str:
    stale = stale if stale is not None else stale_artifacts(run)
    produced = list(unit.produces)
    if any(artifact in stale for artifact in produced):
        return "STALE"
    execution = run.execution_record(unit.id)
    if execution is not None:
        if execution.get("outcome") != "accepted":
            return "READY" if any(run.get(a).present for a in produced) else "WAIT"
        current_outputs = [
            {"artifact_id": artifact_id, "content_hash": run.get(artifact_id).content_hash}
            for artifact_id in produced if run.get(artifact_id).present
        ]
        if execution.get("outputs") != current_outputs:
            return "STALE"
        for reference in execution.get("inputs", []):
            artifact = run.artifacts.get(reference.get("artifact_id"))
            if artifact is None or artifact.content_hash != reference.get("content_hash"):
                return "STALE"
        log_ref = execution.get("log")
        log_path = run.root / log_ref if isinstance(log_ref, str) else None
        if (
            log_path is None or not log_path.is_file()
            or execution.get("log_sha256") != file_hash(log_path)
        ):
            return "STALE"
    if produced and all(
        run.get(artifact).present and not run.get(artifact).errors for artifact in produced
    ):
        return "PASS"
    if any(run.get(artifact).present for artifact in produced):
        return "READY"
    return "WAIT"


def _ordered_workflow(kit: Kit) -> list[str]:
    """Topologically order units and gates, ignoring return and support edges."""
    relevant = {
        node.id for node in kit.graph.nodes.values()
        if node.is_unit or node.id in kit.gates
    }
    incoming = {node_id: 0 for node_id in relevant}
    outgoing = {node_id: [] for node_id in relevant}
    for edge in kit.graph.edges:
        if edge.kind == "return" or edge.frm not in relevant or edge.to not in relevant:
            continue
        incoming[edge.to] += 1
        outgoing[edge.frm].append(edge.to)

    order: list[str] = []
    ready = [node_id for node_id in relevant if incoming[node_id] == 0]
    # Graph insertion order carries the intended order for parallel units.
    positions = {node_id: index for index, node_id in enumerate(kit.graph.nodes)}
    ready.sort(key=positions.get)
    while ready:
        node_id = ready.pop(0)
        order.append(node_id)
        for target in outgoing[node_id]:
            incoming[target] -= 1
            if incoming[target] == 0:
                ready.append(target)
                ready.sort(key=positions.get)
    return order


def gate_action(run: Run, kit: Kit, gate_id: str) -> WorkflowAction | None:
    gate = kit.gates[gate_id]
    if gate.kind == "release":
        terminal = _terminal_final_action(run)
        if terminal is not None:
            return terminal
        record = run.gate_record(gate_id)
        outcome = record.get("outcome") if record else None
        if outcome in ("revise", "narrow"):
            # Once revision work changes a FINAL input, the old routing decision
            # has done its job. Earlier gates re-evaluate first; after they pass,
            # the run returns here for a fresh human release decision.
            if evaluate_gate(run, kit, gate_id).status == "STALE":
                return WorkflowAction(
                    "review", gate_id, "rgraph review",
                    "revised release inputs need a new human decision",
                )
            latest = next((
                item for item in reversed(run.meta.get("history", []))
                if item.get("gate") == gate_id and item.get("outcome") == outcome
            ), None)
            route = gate.routes.get(outcome)
            target = latest.get("to") if latest else None
            if target is None:
                target = route.get("default") if isinstance(route, dict) else route
            return WorkflowAction(
                "unit", target, f"rgraph next --unit {target}",
                f"FINAL {outcome} routed work to {target}",
            )
        return WorkflowAction("review", gate_id, "rgraph review", "release decision")
    result = evaluate_gate(run, kit, gate_id)
    record = run.gate_record(gate_id)
    if gate.kind == "challenge" and record is None:
        return WorkflowAction(
            "challenge", gate_id, f"rgraph challenge {gate_id}",
            f"{gate_id} needs its assigned reviewer",
        )
    if result.status in ("PASS", "CAVEAT"):
        return None
    outcome = record.get("outcome") if record else None
    if outcome == "block" and (gate.kind != "challenge" or result.decision_valid):
        return WorkflowAction(
            "blocked", gate_id, None,
            f"{gate_id} is blocked; narrow the scope, escalate, or stop the run",
        )
    if outcome == "revise":
        if gate.kind == "challenge" and not result.decision_valid:
            return WorkflowAction(
                "challenge", gate_id, f"rgraph challenge {gate_id}",
                f"{gate_id} needs a valid reviewer decision",
            )
        if result.status == "STALE":
            verb = "decide" if gate.kind == "human" else "challenge"
            return WorkflowAction(
                verb, gate_id, f"rgraph {verb} {gate_id}",
                f"{gate_id} must be evaluated again after its inputs changed",
            )
        latest_revision = next((
            item for item in reversed(run.meta.get("history", []))
            if item.get("gate") == gate_id and item.get("outcome") == "revise"
        ), None)
        if latest_revision and latest_revision.get("at", "") >= record.get("decided_at", ""):
            target = latest_revision.get("to")
            if target in kit.graph.nodes and kit.graph.nodes[target].is_unit:
                return WorkflowAction(
                    "unit", target, f"rgraph next --unit {target}",
                    f"{gate_id} routed revision work to {target}",
                )
        return WorkflowAction(
            "revise", gate_id, f"rgraph revise {gate_id}", f"{gate_id} needs revision",
        )
    if gate.kind == "human" and result.status in ("AWAITING", "STALE"):
        return WorkflowAction(
            "decide", gate_id, f"rgraph decide {gate_id}", f"{gate_id} needs a human decision",
        )
    if gate.kind == "challenge":
        return WorkflowAction(
            "challenge", gate_id, f"rgraph challenge {gate_id}",
            f"{gate_id} needs a current reviewer decision",
        )
    return WorkflowAction("check", gate_id, f"rgraph check {gate_id}",
                          f"{gate_id} must pass first")


def next_action(run: Run, kit: Kit) -> WorkflowAction:
    terminal = _terminal_final_action(run)
    if terminal is not None:
        return terminal
    if run.meta.get("question", "").startswith("Replace this with"):
        command = f"rgraph --run {run.root} init --guided --edit"
        return WorkflowAction("setup", None, command, "study setup contains placeholders")

    stale = stale_artifacts(run)
    for node_id in _ordered_workflow(kit):
        node = kit.graph.nodes[node_id]
        if node.is_unit:
            if unit_state(run, node, stale) != "PASS":
                return WorkflowAction(
                    "unit", node.id, "rgraph next",
                    f"{node.id} {node.title}",
                )
            continue
        action = gate_action(run, kit, node_id)
        if action is not None:
            return action
    return WorkflowAction("review", "FINAL", "rgraph review", "release decision")


def prerequisite_action(run: Run, kit: Kit, unit: Node) -> WorkflowAction | None:
    """Return the first unfinished workflow step before an explicit unit."""
    terminal = _terminal_final_action(run)
    if terminal is not None:
        return terminal
    if run.meta.get("question", "").startswith("Replace this with"):
        return next_action(run, kit)
    stale = stale_artifacts(run)
    for node_id in _ordered_workflow(kit):
        if node_id == unit.id:
            return None
        node = kit.graph.nodes[node_id]
        if node.is_unit:
            if unit_state(run, node, stale) != "PASS":
                return WorkflowAction("unit", node.id, "rgraph next", f"{node.id} must run first")
            continue
        action = gate_action(run, kit, node_id)
        if action is not None:
            return action
    return None


def next_checkpoint(kit: Kit, unit_id: str) -> str | None:
    """Find the next gate reachable after a unit along forward handoffs."""
    queue = [unit_id]
    seen = {unit_id}
    while queue:
        current = queue.pop(0)
        for edge in kit.graph.out_edges(current):
            if edge.kind == "return" or edge.to in seen:
                continue
            if edge.to in kit.gates:
                return edge.to
            seen.add(edge.to)
            queue.append(edge.to)
    return None
