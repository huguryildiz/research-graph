"""Load and normalise graph.yaml, providers.yaml, assignment.yaml, gates.yaml."""

from __future__ import annotations

import os
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
# Production order, and `rgraph seal` walks it: an artifact must appear before
# anything that consumes it, or one pass seals the consumer against a digest its
# producer has not taken yet. u11 writes figure_registry, u12 reads it.
ARTIFACTS = (
    "problem_spec", "governance_record", "search_protocol", "corpus_snapshot",
    "kg_snapshot", "evidence_matrix", "hypothesis_registry", "design_protocol",
    "frozen_protocol", "code_commit", "environment_lock", "data_manifest",
    "run_manifest", "raw_results", "reproduction_report", "statistical_report",
    "verification_report", "figure_registry", "claim_evidence_map", "manuscript",
    "release_manifest",
)
PAYLOAD_ARTIFACTS = {"manuscript": "manuscript.md", "raw_results": "raw_results.jsonl"}
RETURN_REASONS = (
    "evidence_gap", "hypothesis_defect", "scope_plan_defect", "assumption_violation",
    "code_run_defect", "claim_support_gap", "revision",
)
EFFORT_SLOT = "{effort_argv}"
NODE_KINDS = ("agent", "store", "gate", "human")
EDGE_KINDS = ("handoff", "return", "read_only")
STAGES = ("retrieve", "plan", "execute", "verify", "write", "audit")
GATE_KINDS = ("human", "challenge", "release")
PROVIDER_SUPPORT_STATUSES = ("configured", "draft")


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
    aliases: tuple[str, ...] = ()
    models: tuple[str, ...] = ()
    default_model: str = "default"
    role_models: dict[str, str] = field(default_factory=dict)
    # A CLI that sells reasoning depth spends the token budget on it, so which
    # depth a role runs at is the subscriber's call, not ours. `{effort_argv}`
    # marks where in the command line the flags belong; it expands to nothing
    # when no effort is assigned, which is why adding this changes no existing
    # invocation. `efforts` is a typo guard, not a claim about any one model.
    effort_argv: tuple[str, ...] = ()
    efforts: tuple[str, ...] = ()
    # Registry maturity, not local availability or model acceptance.
    support_status: str = "configured"
    support_note: str = ""

    @property
    def takes_effort(self) -> bool:
        return bool(self.effort_argv) and EFFORT_SLOT in self.exec_argv


@dataclass(frozen=True)
class Assignment:
    role: str
    provider: str
    model: str
    effort: str | None = None

    def identity(self, providers: dict[str, Provider]) -> str:
        """Who produced this, for the gates that require two of them to differ.

        Effort stays out. A gate asking for separation is asking for a second
        opinion, and the same model thinking longer is not one.
        """
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
    criterion: str
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
    provider_candidates: tuple[str, ...] = ()
    assignment: dict[str, Assignment] = field(default_factory=dict)
    gates: dict[str, Gate] = field(default_factory=dict)


def _as_tuple(value) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(value)


def _read(root: pathlib.Path, name: str | pathlib.Path, required: bool = True):
    # An absolute path passed as `name` stands on its own: `root / "/x"` is `/x`.
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
    if not isinstance(raw, dict):
        raise ConfigError("graph.yaml must be a mapping")
    nodes: dict[str, Node] = {}
    for entry in raw.get("nodes") or []:
        if not isinstance(entry, dict):
            raise ConfigError("each graph node must be a mapping")
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
        if not isinstance(entry, dict):
            raise ConfigError("each graph edge must be a mapping")
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
    if raw is not None and not isinstance(raw, dict):
        raise ConfigError("providers.yaml must be a mapping")
    providers: dict[str, Provider] = {}
    for provider_id, entry in (raw or {}).items():
        if provider_id == "_unregistered_cli_candidates":
            continue
        if not isinstance(entry, dict):
            raise ConfigError(f"provider {provider_id!r} must be a mapping")
        kind = entry.get("kind")
        if kind not in ("cli", "web"):
            raise ConfigError(f"provider {provider_id!r}: kind must be 'cli' or 'web'")
        role_models = entry.get("role_models") or {}
        if not isinstance(role_models, dict):
            raise ConfigError(f"provider {provider_id!r}: role_models must be a mapping")
        unknown_roles = set(role_models) - set(ROLES)
        if unknown_roles:
            raise ConfigError(
                f"provider {provider_id!r}: role_models names unknown roles "
                f"{', '.join(sorted(unknown_roles))}"
            )
        support_status = entry.get("support_status", "configured")
        if support_status not in PROVIDER_SUPPORT_STATUSES:
            raise ConfigError(
                f"provider {provider_id!r}: support_status must be one of "
                f"{PROVIDER_SUPPORT_STATUSES}"
            )
        support_note = entry.get("support_note", "")
        if not isinstance(support_note, str):
            raise ConfigError(f"provider {provider_id!r}: support_note must be a string")
        if support_status == "draft" and not support_note.strip():
            raise ConfigError(
                f"provider {provider_id!r}: a draft provider needs a support_note"
            )
        providers[provider_id] = Provider(
            id=provider_id, kind=kind, invoke=entry.get("invoke"), url=entry.get("url"),
            exec_argv=_as_tuple(entry.get("exec_argv")), stdin=entry.get("stdin"),
            identity=entry.get("identity", f"{provider_id}/{{model}}"),
            capabilities=frozenset(_as_tuple(entry.get("capabilities"))),
            login_check=_as_tuple(entry.get("login_check")),
            aliases=_as_tuple(entry.get("aliases")),
            models=_as_tuple(entry.get("models")),
            default_model=str(entry.get("default_model", "default")),
            role_models={str(role): str(model) for role, model in role_models.items()},
            effort_argv=_as_tuple(entry.get("effort_argv")),
            efforts=_as_tuple(entry.get("efforts")),
            support_status=support_status,
            support_note=support_note.strip(),
        )
    return providers


def _provider_candidates(raw) -> tuple[str, ...]:
    if raw is None:
        return ()
    candidates = raw.get("_unregistered_cli_candidates") or ()
    if isinstance(candidates, str):
        candidates = (candidates,)
    if not isinstance(candidates, (list, tuple)):
        raise ConfigError("_unregistered_cli_candidates must be a list")
    return tuple(str(name) for name in candidates)


def _build_assignment(raw) -> dict[str, Assignment]:
    if raw is not None and not isinstance(raw, dict):
        raise ConfigError("assignment must be a mapping")
    assignment: dict[str, Assignment] = {}
    for role, entry in (raw or {}).items():
        if role not in ROLES:
            raise ConfigError(f"unknown role {role!r}; expected one of {ROLES}")
        if not isinstance(entry, dict):
            raise ConfigError(f"assignment for role {role!r} must be a mapping")
        effort = entry.get("effort")
        assignment[role] = Assignment(
            role=role, provider=entry["provider"], model=str(entry["model"]),
            effort=str(effort) if effort is not None else None,
        )
    return assignment


def _check_efforts(assignment: dict, providers: dict[str, Provider]) -> None:
    """Reject an effort the command line would silently swallow.

    An effort named for a provider that has nowhere to put it reads as
    configured and runs as ignored, so it is refused rather than dropped.
    """
    for role, entry in assignment.items():
        if entry.effort is None:
            continue
        provider = providers.get(entry.provider)
        if provider is None:
            continue  # `identity` reports the unknown provider, and better.
        if not provider.takes_effort:
            raise ConfigError(
                f"role {role!r}: provider '{entry.provider}' takes no effort setting; "
                f"give it an effort_argv in providers.yaml or drop the effort"
            )
        if provider.efforts and entry.effort not in provider.efforts:
            raise ConfigError(
                f"role {role!r}: '{entry.provider}' does not list effort "
                f"{entry.effort!r} (has {', '.join(provider.efforts)})"
            )


# The checks `evaluate_gate` runs from the gate's kind rather than from a lookup
# table. Everything else a gate names has to be a key in `CONTENT_CHECKS`.
GENERIC_CHECKS = ("presence", "schema", "provenance", "staleness", "separation", "budget")


def _build_gates(raw, graph: Graph) -> dict[str, Gate]:
    # Imported here rather than at module scope: `rgraph.checks` imports this
    # module for Gate and Kit, and by the time a kit is built both exist.
    from rgraph.checks import CONTENT_CHECKS

    if raw is not None and not isinstance(raw, dict):
        raise ConfigError("gates.yaml must be a mapping")
    gates: dict[str, Gate] = {}
    for gate_id, entry in (raw or {}).items():
        if not isinstance(entry, dict):
            raise ConfigError(f"gate {gate_id!r} must be a mapping")
        kind = entry.get("kind")
        if kind not in GATE_KINDS:
            raise ConfigError(f"gate {gate_id!r}: unknown kind {kind!r}")
        separation = entry.get("separation") or {}
        inputs = _as_tuple(entry.get("inputs"))
        for artifact in inputs:
            if artifact not in ARTIFACTS:
                raise ConfigError(f"gate {gate_id!r}: unknown input artifact {artifact!r}")
        for check in _as_tuple(entry.get("checks")):
            if check not in GENERIC_CHECKS and check not in CONTENT_CHECKS:
                raise ConfigError(
                    f"gate {gate_id!r}: unknown check {check!r} "
                    f"(known: {', '.join(sorted({*GENERIC_CHECKS, *CONTENT_CHECKS}))})"
                )
        gates[gate_id] = Gate(
            id=gate_id, kind=kind, title=entry.get("title", ""),
            criterion=entry.get("criterion", ""), owner=entry["owner"],
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


def machine_assignment_path() -> pathlib.Path:
    """Where `rgraph setup` keeps the assignment by default.

    `assignment.yaml` says which subscriptions you run. That is a property of
    the machine, not of the graph, so it cannot live inside the installed
    package — the next `uv tool upgrade` replaces that directory wholesale.
    """
    base = os.environ.get("XDG_CONFIG_HOME") or pathlib.Path.home() / ".config"
    return pathlib.Path(base) / "rgraph" / "assignment.yaml"


def resolve_assignment(root: pathlib.Path) -> pathlib.Path | None:
    """The assignment in force here, or None when nobody has written one.

    A copy beside the work wins, so a single study can run on a different
    combination of providers than the rest of the machine. `--root` comes last
    and only matters when you point it at a checkout from somewhere else.
    """
    for candidate in (
        pathlib.Path("assignment.yaml"),
        machine_assignment_path(),
        root / "assignment.yaml",
    ):
        if candidate.exists():
            # Absolute, or `load_kit` would join it onto the root all over again.
            return candidate.resolve()
    return None


def load_kit(
    root: pathlib.Path | str,
    *,
    assignment: str | pathlib.Path = "assignment.yaml",
) -> Kit:
    root = pathlib.Path(root)
    graph = _build_graph(_read(root, "graph.yaml"))
    providers_raw = _read(root, "providers.yaml")
    providers = _build_providers(providers_raw)
    raw_assignment = _read(root, assignment, required=False)
    gates_raw = _read(root, "gates.yaml", required=False)
    built_assignment = _build_assignment(raw_assignment)
    _check_efforts(built_assignment, providers)
    return Kit(
        root=root,
        graph=graph,
        providers=providers,
        provider_candidates=_provider_candidates(providers_raw),
        assignment=built_assignment,
        gates=_build_gates(gates_raw, graph) if gates_raw else {},
    )
