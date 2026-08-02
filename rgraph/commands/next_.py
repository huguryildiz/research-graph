"""`rgraph next` — show the inventory, then run exactly one approved command."""

from __future__ import annotations

import datetime as _dt
import pathlib

from rgraph.config import ConfigError
from rgraph.hashing import file_hash
from rgraph.provenance import body_mismatch, hash_mismatch, payload_mismatch
from rgraph.render import (
    body_text, console, key_value, muted, prompt_input, render_command,
    render_error, render_next, render_next_action, render_provenance_notice, section,
)
from rgraph.run import RunError, load_run
from rgraph.runner import build_plan, execute
from rgraph.schemas import registry
from rgraph.workflow import next_action, next_checkpoint, prerequisite_action


def _output_state(run, artifact_ids) -> dict[str, tuple[str | None, str | None]]:
    state = {}
    for artifact_id in artifact_ids:
        artifact = run.artifacts[artifact_id]
        envelope = file_hash(artifact.path) if artifact.path.is_file() else None
        payload = (
            file_hash(artifact.payload_path)
            if artifact.payload_path is not None and artifact.payload_path.is_file()
            else None
        )
        state[artifact_id] = (envelope, payload)
    return state


def _run_boundary_state(root) -> dict[str, str]:
    state = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if relative.parts and relative.parts[0] == "logs":
            continue
        state[relative.as_posix()] = file_hash(path)
    return state


def _allowed_output_paths(run, unit) -> set[str]:
    allowed = set()
    for artifact_id in unit.produces:
        artifact = run.artifacts[artifact_id]
        allowed.add(artifact.path.relative_to(run.root).as_posix())
        if artifact.payload_path is not None:
            allowed.add(artifact.payload_path.relative_to(run.root).as_posix())
    return allowed


def _manifest_sidecars(run, unit) -> tuple[set[str], list[str]]:
    """Safe, hash-bound files that are part of a declared data manifest."""
    allowed: set[str] = set()
    problems: list[str] = []
    if "data_manifest" not in unit.produces:
        return allowed, problems
    artifact = run.get("data_manifest")
    if not artifact.present or artifact.errors:
        return allowed, problems
    for dataset in artifact.body.get("datasets", []):
        value = dataset.get("path")
        relative = pathlib.PurePosixPath(value) if isinstance(value, str) else None
        if (
            relative is None or relative.is_absolute() or not relative.parts
            or relative.parts[0] != "data" or ".." in relative.parts
        ):
            problems.append(
                f"data_manifest: dataset path {value!r} must stay below run/data"
            )
            continue
        candidate = (run.root / relative).resolve()
        try:
            candidate.relative_to(run.root.resolve())
        except ValueError:
            problems.append(f"data_manifest: dataset path {value!r} escapes the run")
            continue
        allowed.add(relative.as_posix())
        if not candidate.is_file():
            problems.append(f"data_manifest: declared dataset is missing: {value}")
            continue
        actual_hash = file_hash(candidate).removeprefix("sha256:")
        if actual_hash != dataset.get("sha256"):
            problems.append(f"data_manifest: dataset digest does not match: {value}")
        if candidate.stat().st_size != dataset.get("bytes"):
            problems.append(f"data_manifest: dataset byte count does not match: {value}")
    return allowed, problems


def _output_problems(run, kit, unit, before, boundary_before) -> list[str]:
    problems: list[str] = []
    current = _output_state(run, unit.produces)
    if current == before:
        problems.append("provider exited 0 but changed none of the declared outputs")
    boundary_after = _run_boundary_state(run.root)
    changed = {
        name for name in boundary_before.keys() | boundary_after.keys()
        if boundary_before.get(name) != boundary_after.get(name)
    }
    sidecars, sidecar_problems = _manifest_sidecars(run, unit)
    problems.extend(sidecar_problems)
    unexpected = sorted(changed - _allowed_output_paths(run, unit) - sidecars)
    if unexpected:
        problems.append(
            "provider changed files outside the declared unit outputs: "
            + ", ".join(unexpected[:8])
        )
    expected_identity = kit.assignment[unit.role_name].identity(kit.providers)
    for artifact_id in unit.produces:
        artifact = run.get(artifact_id)
        if not artifact.present:
            problems.append(f"{artifact_id}: output is missing")
            continue
        if artifact.errors:
            problems.append(f"{artifact_id}: output does not match its schema")
            continue
        if artifact.identity != expected_identity:
            problems.append(
                f"{artifact_id}: produced_by.identity is {artifact.identity!r}; "
                f"expected {expected_identity!r}"
            )
        body = body_mismatch(artifact)
        if body:
            problems.append(f"{artifact_id}: {body}")
        payload = payload_mismatch(run, artifact)
        if payload:
            problems.append(f"{artifact_id}: {payload}")
        for upstream, _, _ in hash_mismatch(run, artifact):
            problems.append(f"{artifact_id}: input {upstream} does not match")
    return problems


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _artifact_refs(run, artifact_ids) -> list[dict]:
    return [
        {"artifact_id": artifact_id, "content_hash": run.get(artifact_id).content_hash}
        for artifact_id in artifact_ids
        if run.get(artifact_id).present and run.get(artifact_id).content_hash
    ]


def _write_execution_record(
    run, current, kit, unit, plan, *, started_at, finished_at, exit_code, problems,
):
    assignment = kit.assignment[unit.role_name]
    log_path = plan.log_path if plan.log_path and plan.log_path.is_file() else None
    record = {
        "unit_id": unit.id,
        "invocation_id": plan.invocation_id or "legacy-invocation",
        "outcome": "rejected" if problems or exit_code else "accepted",
        "started_at": started_at,
        "finished_at": finished_at,
        "assignment": {
            "provider": assignment.provider,
            "model": assignment.model,
            "identity": assignment.identity(kit.providers),
        },
        "argv": plan.argv,
        "exit_code": exit_code,
        "log": log_path.relative_to(run.root).as_posix() if log_path else None,
        "log_sha256": file_hash(log_path) if log_path else None,
        "inputs": _artifact_refs(run, [artifact_id for artifact_id, _ in plan.inputs]),
        "outputs": _artifact_refs(current, unit.produces),
        "problems": problems,
    }
    errors = registry(kit.root).validate("execution_record", record)
    if errors:
        first = errors[0]
        raise RunError(f"generated execution record is invalid: {first.path}: {first.message}")
    return run.write_execution_record(record)


def register(subparsers) -> None:
    parser = subparsers.add_parser(
        "next",
        help="the next unit of work",
        description=(
            "Inspect the next ready unit and its inputs before optionally running "
            "the assigned provider command."
        ),
        epilog=(
            "Examples:\n"
            "  rgraph next\n"
            "  rgraph next --unit u06 --dry-run\n"
            "  rgraph next --unit u06 --execute"
        ),
    )
    parser.add_argument("--unit", help="run a specific unit instead of the next one")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--execute", action="store_true",
                        help="run the displayed provider command without prompting")
    action.add_argument("--dry-run", action="store_true",
                        help="print the provider command without running it")
    parser.set_defaults(handler=handle)


def handle(args) -> int:
    from rgraph.commands.check import load_for_run

    try:
        kit, run = load_for_run(args)
    except (ConfigError, RunError) as exc:
        render_error(str(exc))
        return 2

    render_provenance_notice(run)
    if args.unit:
        unit = kit.graph.nodes.get(args.unit)
        if unit is None or not unit.is_unit:
            expected = ", ".join(sorted(node.id for node in kit.graph.units()))
            render_error(f"unknown unit '{args.unit}'; expected one of {expected}")
            return 2
        blocked_by = prerequisite_action(run, kit, unit)
        if blocked_by is not None:
            body_text(f"Cannot run {unit.id} yet: {blocked_by.detail}.")
            if blocked_by.command:
                console.print()
                render_next_action(blocked_by.command)
            return 1
    else:
        action = next_action(run, kit)
        if action.kind != "unit":
            body_text(f"No unit can run yet: {action.detail}.")
            if action.command:
                console.print()
                render_next_action(action.command)
            return 0 if action.kind in ("review", "complete") else 1
        unit = kit.graph.nodes[action.target]

    plan = build_plan(run, kit, unit.id)
    gate_id = next_checkpoint(kit, unit.id) or "none"
    render_next(plan, unit, gate_id, plan.manual)

    if args.execute:
        answer = "E"
    elif args.dry_run:
        answer = "D"
    else:
        while True:
            try:
                answer = prompt_input("Choose", suffix=" [1-3]", marker=": ").strip().upper()
            except (EOFError, KeyboardInterrupt):
                console.print()
                muted("No choice was made. Re-run with --execute or --dry-run.")
                return 2
            answer = {"1": "E", "2": "D", "3": "S", "EXECUTE": "E",
                      "DRY": "D", "DRY-RUN": "D", "STOP": "S", "": "S"}.get(
                          answer, answer
                      )
            if answer in ("E", "D", "S"):
                break
            muted("Choose 1 (execute), 2 (dry run), or 3 (stop).")

    if answer == "D":
        console.print()
        section("Would run")
        render_command(" ".join(plan.argv) + f" < {plan.role_path}")
        return 0
    if answer != "E":
        console.print()
        muted("Stopped. No command has been executed.")
        return 0
    if plan.manual:
        console.print()
        muted("This provider is web-only; there is nothing to execute.")
        return 0
    if run.read_only:
        render_error("the bundled example-run is read-only; copy it before executing a unit")
        return 2

    console.print()
    before = _output_state(run, unit.produces)
    boundary_before = _run_boundary_state(run.root)
    started_at = _now()
    code = execute(plan, verbose=args.verbose)
    finished_at = _now()
    console.print()
    section("Provider result")
    key_value("Exit code", code)
    key_value("Log", plan.log_path)
    problems = [] if code == 0 else [f"provider CLI exited {code}"]
    try:
        refreshed = load_run(run.root, kit)
    except RunError as exc:
        problems.append(f"provider left an unreadable run: {exc}")
        refreshed = run
    if code == 0:
        problems.extend(_output_problems(refreshed, kit, unit, before, boundary_before))
    if plan.log_path is None or not plan.log_path.is_file():
        problems.append("provider log is missing")
    try:
        receipt = _write_execution_record(
            run, refreshed, kit, unit, plan,
            started_at=started_at, finished_at=finished_at,
            exit_code=code, problems=problems,
        )
    except RunError as exc:
        render_error(str(exc))
        return 2
    key_value("Receipt", receipt)
    if problems:
        for problem in problems:
            render_error(problem)
        muted("The unit was not accepted. Inspect the provider log and retry explicitly.")
        return 1
    console.print()
    render_next_action("rgraph status")
    return 0 if code == 0 else 1
