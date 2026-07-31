"""Load and normalise graph.yaml, providers.yaml, assignment.yaml, gates.yaml."""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field

from rgraph.yamlmini import YamlError, load_file

ROLES = (
    "retrieval", "planning", "execution", "verification", "synthesis", "reviewer",
)
ROLE_REQUIRES = {
    "retrieval": frozenset({"filesystem"}),
    "planning": frozenset({"filesystem"}),
    "execution": frozenset({"filesystem", "shell"}),
    "verification": frozenset({"filesystem", "shell"}),
    "synthesis": frozenset({"filesystem"}),
    "reviewer": frozenset({"read_files"}),
}
ARTIFACTS = (
    "problem_spec", "governance_record", "search_protocol", "corpus_snapshot",
    "kg_snapshot", "evidence_matrix", "hypothesis_registry", "design_protocol",
    "frozen_protocol", "code_commit", "environment_lock", "data_manifest",
    "run_manifest", "raw_results", "reproduction_report", "statistical_report",
    "verification_report", "claim_evidence_map", "figure_registry", "manuscript",
    "release_manifest",
)
PAYLOAD_ARTIFACTS = {"manuscript": "manuscript.md", "raw_results": "raw_results.jsonl"}
RETURN_REASONS = (
    "evidence_gap", "hypothesis_defect", "scope_plan_defect", "assumption_violation",
    "code_run_defect", "claim_support_gap", "revision",
)
NODE_KINDS = ("agent", "store", "gate", "human")
EDGE_KINDS = ("handoff", "return", "read_only")
STAGES = ("retrieve", "plan", "execute", "verify", "write", "audit")
GATE_KINDS = ("human", "challenge", "release")


class ConfigError(Exception):
    pass


def assignability(provider, role: str) -> str:
    """How a provider can take a role: 'ok', 'manual' or 'blocked'.

    A provider that declares `manual` relays files through a human, so it can
    stand in for `filesystem` but never for `shell`. That is the difference
    between "you will be pasting a lot" and "this cannot work".
    """
    required = ROLE_REQUIRES[role]
    missing = required - provider.capabilities
    if not missing:
        return "ok"
    if "manual" in provider.capabilities and missing <= {"filesystem"}:
        return "manual"
    return "blocked"


@dataclass(frozen=True)
class Node:
    id: str
    kind: str
    stage: str | None = None
    role: str | None = None
    title: str = ""
    produces: tuple[str, ...] = ()
    gate: str | None = None
    reviewer: str | None = None

    @property
    def is_unit(self) -> bool:
        return self.kind == "agent" and self.stage != "audit"

    @property
    def role_name(self) -> str | None:
        return pathlib.PurePosixPath(self.role).stem if self.role else None


@dataclass(frozen=True)
class Edge:
    frm: str
    to: str
    kind: str
    carries: tuple[str, ...] = ()
    budget: int | None = None


@dataclass(frozen=True)
class Graph:
    nodes: dict[str, Node]
    edges: tuple[Edge, ...]

    def node(self, node_id: str) -> Node:
        try:
            return self.nodes[node_id]
        except KeyError:
            raise ConfigError(f"unknown node '{node_id}'") from None

    def units(self) -> list[Node]:
        return [n for n in self.nodes.values() if n.is_unit]

    def out_edges(self, node_id: str) -> list[Edge]:
        return [e for e in self.edges if e.frm == node_id]

    def in_edges(self, node_id: str) -> list[Edge]:
        return [e for e in self.edges if e.to == node_id]

    def producer_of(self, artifact: str) -> Node | None:
        for node in self.nodes.values():
            if artifact in node.produces:
                return node
        return None


@dataclass(frozen=True)
class Provider:
    id: str
    kind: str
    invoke: str | None = None
    url: str | None = None
    exec_argv: tuple[str, ...] = ()
    stdin: str | None = None
    identity: str = ""
    capabilities: frozenset[str] = frozenset()
    login_check: tuple[str, ...] = ()


@dataclass(frozen=True)
class Assignment:
    role: str
    provider: str
    model: str

    def identity(self, providers: dict[str, Provider]) -> str:
        try:
            template = providers[self.provider].identity
        except KeyError:
            raise ConfigError(
                f"role '{self.role}' is assigned to unknown provider '{self.provider}'"
            ) from None
        return template.replace("{model}", self.model)


@dataclass(frozen=True)
class Gate:
    id: str
    kind: str
    title: str
    owner: str
    producer: str | None = None
    inputs: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    outcomes: tuple[str, ...] = ()
    max_revisions: int = 3
    routes: dict = field(default_factory=dict)
    checks: tuple[str, ...] = ()
    proves: tuple[str, ...] = ()
    freezes: str | None = None
    produces: str | None = None
    distinct_actor_from: tuple[str, ...] = ()
    separation_required: str | None = None
    separation_preferred: str | None = None


@dataclass(frozen=True)
class Kit:
    root: pathlib.Path
    graph: Graph
    providers: dict[str, Provider]
    assignment: dict[str, Assignment] = field(default_factory=dict)
    gates: dict[str, Gate] = field(default_factory=dict)


def _as_tuple(value) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(value)


def _read(root: pathlib.Path, name: str, required: bool = True):
    path = root / name
    if not path.exists():
        if required:
            raise ConfigError(f"missing config file: {path}")
        return None
    try:
        return load_file(path)
    except YamlError as exc:
        raise ConfigError(str(exc)) from None


def _build_graph(raw) -> Graph:
    nodes: dict[str, Node] = {}
    for entry in raw.get("nodes") or []:
        kind = entry.get("kind")
        if kind not in NODE_KINDS:
            raise ConfigError(f"unknown node kind {kind!r} on node {entry.get('id')!r}")
        stage = entry.get("stage")
        if stage is not None and stage not in STAGES:
            raise ConfigError(f"unknown stage {stage!r} on node {entry.get('id')!r}")
        node = Node(
            id=entry["id"], kind=kind, stage=stage, role=entry.get("role"),
            title=entry.get("title", ""), produces=_as_tuple(entry.get("produces")),
            gate=entry.get("gate"), reviewer=entry.get("reviewer"),
        )
        if node.id in nodes:
            raise ConfigError(f"duplicate node id {node.id!r}")
        for artifact in node.produces:
            if artifact not in ARTIFACTS:
                raise ConfigError(f"node {node.id!r} produces unknown artifact {artifact!r}")
        nodes[node.id] = node

    edges: list[Edge] = []
    for entry in raw.get("edges") or []:
        frm, to = entry["from"], entry["to"]
        kind = entry.get("kind")
        if kind not in EDGE_KINDS:
            raise ConfigError(f"edge {frm} -> {to}: unknown edge kind {kind!r}")
        for endpoint in (frm, to):
            if endpoint not in nodes:
                raise ConfigError(f"edge {frm} -> {to}: unknown node {endpoint!r}")
        carries = _as_tuple(entry.get("carries"))
        if kind == "return":
            if len(carries) != 1 or carries[0] not in RETURN_REASONS:
                raise ConfigError(
                    f"edge {frm} -> {to}: a return edge must carry exactly one of "
                    f"{RETURN_REASONS}"
                )
        else:
            for artifact in carries:
                if artifact not in ARTIFACTS:
                    raise ConfigError(f"edge {frm} -> {to}: unknown artifact {artifact!r}")
        edges.append(Edge(frm=frm, to=to, kind=kind, carries=carries, budget=entry.get("budget")))
    return Graph(nodes=nodes, edges=tuple(edges))


def _build_providers(raw) -> dict[str, Provider]:
    providers: dict[str, Provider] = {}
    for provider_id, entry in (raw or {}).items():
        kind = entry.get("kind")
        if kind not in ("cli", "web"):
            raise ConfigError(f"provider {provider_id!r}: kind must be 'cli' or 'web'")
        providers[provider_id] = Provider(
            id=provider_id, kind=kind, invoke=entry.get("invoke"), url=entry.get("url"),
            exec_argv=_as_tuple(entry.get("exec_argv")), stdin=entry.get("stdin"),
            identity=entry.get("identity", f"{provider_id}/{{model}}"),
            capabilities=frozenset(_as_tuple(entry.get("capabilities"))),
            login_check=_as_tuple(entry.get("login_check")),
        )
    return providers


def _build_assignment(raw) -> dict[str, Assignment]:
    assignment: dict[str, Assignment] = {}
    for role, entry in (raw or {}).items():
        if role not in ROLES:
            raise ConfigError(f"unknown role {role!r}; expected one of {ROLES}")
        assignment[role] = Assignment(
            role=role, provider=entry["provider"], model=str(entry["model"])
        )
    return assignment


def _build_gates(raw, graph: Graph) -> dict[str, Gate]:
    gates: dict[str, Gate] = {}
    for gate_id, entry in (raw or {}).items():
        kind = entry.get("kind")
        if kind not in GATE_KINDS:
            raise ConfigError(f"gate {gate_id!r}: unknown kind {kind!r}")
        separation = entry.get("separation") or {}
        inputs = _as_tuple(entry.get("inputs"))
        for artifact in inputs:
            if artifact not in ARTIFACTS:
                raise ConfigError(f"gate {gate_id!r}: unknown input artifact {artifact!r}")
        gates[gate_id] = Gate(
            id=gate_id, kind=kind, title=entry.get("title", ""), owner=entry["owner"],
            producer=entry.get("producer"), inputs=inputs,
            requires=_as_tuple(entry.get("requires")),
            outcomes=_as_tuple(entry.get("outcomes")),
            max_revisions=int(entry.get("max_revisions", 3)),
            routes=entry.get("routes") or {},
            checks=_as_tuple(entry.get("checks")),
            proves=_as_tuple(entry.get("proves")),
            freezes=entry.get("freezes"), produces=entry.get("produces"),
            distinct_actor_from=_as_tuple(entry.get("distinct_actor_from")),
            separation_required=separation.get("required"),
            separation_preferred=separation.get("preferred"),
        )
    for gate in gates.values():
        for required in gate.requires:
            if required not in gates:
                raise ConfigError(f"gate {gate.id!r}: requires unknown gate {required!r}")
        if gate.id not in graph.nodes:
            raise ConfigError(f"gate {gate.id!r} has no node in graph.yaml")
    return gates


def load_kit(
    root: pathlib.Path | str,
    *,
    assignment: str = "assignment.yaml",
) -> Kit:
    root = pathlib.Path(root)
    graph = _build_graph(_read(root, "graph.yaml"))
    providers = _build_providers(_read(root, "providers.yaml"))
    raw_assignment = _read(root, assignment, required=False)
    gates_raw = _read(root, "gates.yaml", required=False)
    return Kit(
        root=root,
        graph=graph,
        providers=providers,
        assignment=_build_assignment(raw_assignment),
        gates=_build_gates(gates_raw, graph) if gates_raw else {},
    )
