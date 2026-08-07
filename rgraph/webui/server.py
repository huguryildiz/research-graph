"""Loopback-only HTTP server for the offline research-graph UI.

Two modes, one server. Without a selected run it serves a launcher, so
`rgraph ui` in an ordinary directory opens something usable instead of an
error. With a run selected it serves the control room over that run.

The security posture is unchanged and deliberately narrow: it binds to loopback
only, refuses a non-loopback `Host`, requires a per-session token on every
material request and on every execution-log read, never reflects a token into a
log or a URL, and has no route that can record a human decision.
"""

from __future__ import annotations

import json
import mimetypes
import pathlib
import secrets
import shutil
import tempfile
import threading
import traceback
import urllib.parse
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from types import SimpleNamespace

from rgraph.commands.check import load, load_for_run
from rgraph.config import ConfigError, machine_assignment_path
from rgraph.gates import evaluate_gate
from rgraph.jobs import JobError, JobManager, Redactor
from rgraph.run import RunError
from rgraph.services import demo as demo_service
from rgraph.services import providers as provider_service
from rgraph.services import recent as recent_service
from rgraph.services import study as study_service
from rgraph.services.preflight import (
    findings_view, inspect_assignment, load_assigned_kit, probe_plan, run_probes,
)
from rgraph.webui.actions import (
    ActionError, ApprovalStore, execute_approved, execute_challenge, execute_revision,
    job_view, preview_challenge, preview_next, preview_revision, start_challenge_job,
    start_unit_job,
)
from rgraph.webui.views import (
    gate_result_view, launcher_view, state_view, trace_view, unit_detail_view,
)

MAX_BODY = 256 * 1024
LOOPBACKS = frozenset({"127.0.0.1", "localhost", "::1"})
STREAM_SECONDS = 90.0
STATIC_FILES = {
    "/": "index.html",
    "/index.html": "index.html",
    "/app.css": "app.css",
    "/app.js": "app.js",
    "/launcher.js": "launcher.js",
    "/workspace.js": "workspace.js",
    "/console.js": "console.js",
    "/icon.svg": "icon.svg",
}


class LocalUI:
    """Server-side state: which study is open, what was approved, what is running."""

    def __init__(
        self, root: pathlib.Path, run: pathlib.Path | None, csrf_token: str,
    ) -> None:
        self.root = root
        self.run = pathlib.Path(run) if run is not None else None
        self.csrf_token = csrf_token
        self.approvals = ApprovalStore()
        # The session token is added to the redaction list so it cannot appear
        # in a transcript even if a provider is handed it by mistake.
        self.jobs = JobManager(
            Redactor(Redactor.environment_literals() + (csrf_token,))
        )
        self.demo_root: pathlib.Path | None = None
        self._lock = threading.RLock()

    # ── which run ──────────────────────────────────────────────────────────

    @property
    def has_run(self) -> bool:
        return self.run is not None and (self.run / "meta.json").is_file()

    def load(self):
        if not self.has_run:
            raise ActionError(
                "No study is open. Choose one from the launcher first.", status=409,
            )
        kit, run = load_for_run(
            SimpleNamespace(root=str(self.root), run=str(self.run))
        )
        if self.demo_root is not None and run.root.resolve() == self.demo_root.resolve():
            # A demo is a throwaway copy of the fixture. It is opened read-only so
            # that no provider can be launched against teaching data.
            run.read_only = True
        return kit, run

    def kit(self):
        return load(SimpleNamespace(root=str(self.root), run=str(self.run or "run")))

    def open_run(self, raw: str) -> pathlib.Path:
        candidate = pathlib.Path(str(raw).strip()).expanduser()
        if not str(raw).strip():
            raise ActionError("Choose a study directory.")
        try:
            resolved = candidate.resolve()
        except OSError as exc:
            raise ActionError(f"That path cannot be resolved: {exc}") from exc
        if not resolved.is_dir():
            raise ActionError(f"{resolved} is not a directory.", status=404)
        if not (resolved / "meta.json").is_file():
            raise ActionError(
                f"{resolved} does not hold a research-graph run (no meta.json).",
                status=404,
            )
        previous = self.run
        self.run = resolved
        try:
            self.load()
        except (ActionError, ConfigError, RunError) as exc:
            self.run = previous
            raise ActionError(f"That study could not be opened: {exc}", status=409) from exc
        if self.demo_root is None or resolved != self.demo_root.resolve():
            recent_service.remember(resolved)
        return resolved

    def open_demo(self) -> pathlib.Path:
        with self._lock:
            self.discard_demo()
            temporary = pathlib.Path(
                tempfile.mkdtemp(prefix="rgraph-demo-")
            ) / "demo-study"
            demo_service.copy_fixture(self.kit(), temporary)
            self.demo_root = temporary
            self.run = temporary
            return temporary

    def discard_demo(self) -> None:
        if self.demo_root is not None:
            shutil.rmtree(self.demo_root.parent, ignore_errors=True)
            if self.run is not None and self.run == self.demo_root:
                self.run = None
            self.demo_root = None

    def default_destination(self) -> pathlib.Path:
        base = pathlib.Path.cwd() / "run"
        if not (base / "meta.json").exists() and not base.exists():
            return base
        for index in range(2, 100):
            candidate = pathlib.Path.cwd() / f"run-{index}"
            if not candidate.exists():
                return candidate
        return base


def _handler(app: LocalUI):
    static_root = files("rgraph.webui").joinpath("static")

    class Handler(BaseHTTPRequestHandler):
        server_version = "rgraph-local-ui"

        def log_message(self, format: str, *args) -> None:
            return

        def _headers(self, status: int, content_type: str, length: int | None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            if length is not None:
                self.send_header("Content-Length", str(length))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Cache-Control", "no-store")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
                "base-uri 'none'; form-action 'self'",
            )
            self.end_headers()

        def _json(self, body: dict, status: int = 200) -> None:
            payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self._headers(status, "application/json; charset=utf-8", len(payload))
            self.wfile.write(payload)

        def _error(self, message: str, status: int = 400) -> None:
            self._json({"error": message}, status)

        def _require_loopback_host(self) -> None:
            raw = self.headers.get("Host", "")
            try:
                hostname = urllib.parse.urlsplit("//" + raw).hostname
            except ValueError as exc:
                raise ActionError("Invalid Host header.", status=403) from exc
            if hostname not in LOOPBACKS:
                raise ActionError("The local UI rejects non-loopback Host headers.", status=403)

        def _require_token(self) -> None:
            if not secrets.compare_digest(
                self.headers.get("X-RGraph-Token", ""), app.csrf_token,
            ):
                raise ActionError("The local UI session token is missing or invalid.", status=403)

        def _read_json(self) -> dict:
            self._require_token()
            if self.headers.get_content_type() != "application/json":
                raise ActionError("Expected an application/json request.", status=415)
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError as exc:
                raise ActionError("Invalid request size.") from exc
            if length <= 0 or length > MAX_BODY:
                raise ActionError("Request body is empty or too large.", status=413)
            try:
                value = json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise ActionError("Request body is not valid JSON.") from exc
            if not isinstance(value, dict):
                raise ActionError("Request body must be a JSON object.")
            return value

        def _load(self):
            try:
                return app.load()
            except (ConfigError, RunError) as exc:
                raise ActionError(str(exc), status=409) from exc

        def _kit(self):
            try:
                return app.kit()
            except ConfigError as exc:
                raise ActionError(str(exc), status=409) from exc

        # ── job helpers ────────────────────────────────────────────────────

        def _job_records(self) -> list[dict]:
            if not app.has_run:
                return []
            live = [job_view(job) for job in app.jobs.for_run(app.run)]
            known = {item["id"] for item in live}
            adopted = [
                record for record in app.jobs.adopt_records(app.run)
                if record["id"] not in known
            ]
            return sorted(
                live + adopted, key=lambda item: item.get("created_at") or "", reverse=True,
            )[:20]

        def _jobs_by_unit(self, records: list[dict]) -> dict[str, dict]:
            latest: dict[str, dict] = {}
            for record in records:
                if record.get("kind") == "unit":
                    latest.setdefault(record["target"], record)
            return latest

        # ── GET ────────────────────────────────────────────────────────────

        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(parsed.query)
            try:
                self._require_loopback_host()
                if parsed.path == "/api/app":
                    self._json(launcher_view(
                        app.root, app.run if app.has_run else None,
                        recent_service.studies(), app.default_destination(),
                    ) | {"demo": app.demo_root is not None})
                    return
                if parsed.path == "/api/state":
                    kit, run = self._load()
                    records = self._job_records()
                    self._json(state_view(
                        run, kit, self._jobs_by_unit(records), records,
                    ) | {"demo": app.demo_root is not None})
                    return
                if parsed.path == "/api/unit":
                    unit_id = query.get("id", [""])[0]
                    kit, run = self._load()
                    records = self._job_records()
                    try:
                        self._json({"unit": unit_detail_view(
                            run, kit, unit_id, self._jobs_by_unit(records).get(unit_id),
                        )})
                    except KeyError as exc:
                        raise ActionError(f"Unknown work unit: {unit_id}") from exc
                    return
                if parsed.path == "/api/trace":
                    claim = query.get("claim", [""])[0]
                    if not claim:
                        raise ActionError("Choose a claim to trace.")
                    kit, run = self._load()
                    self._json(trace_view(run, kit, claim))
                    return
                if parsed.path == "/api/jobs":
                    self._require_token()
                    self._json({"jobs": self._job_records()})
                    return
                if parsed.path.startswith("/api/jobs/"):
                    self._job_route(parsed.path, query)
                    return
                self._serve_static(parsed.path)
            except ActionError as exc:
                self._error(str(exc), exc.status)
            except JobError as exc:
                self._error(str(exc), exc.status)
            except Exception:
                traceback.print_exc()
                self._error("The local UI could not complete this request.", 500)

        def _job_route(self, path: str, query: dict) -> None:
            # Every execution-log read is authenticated. The token travels in a
            # header, never in the URL, so it cannot reach a proxy log or history.
            self._require_token()
            parts = path.strip("/").split("/")
            if len(parts) < 3:
                raise ActionError("Not found.", status=404)
            job_id = parts[2]
            tail = parts[3] if len(parts) > 3 else ""
            if not app.has_run:
                raise ActionError("No study is open.", status=409)
            if tail == "":
                job = app.jobs.get(job_id)
                if job is not None:
                    self._json({"job": job_view(job)})
                    return
                stored = next(
                    (item for item in app.jobs.adopt_records(app.run) if item["id"] == job_id),
                    None,
                )
                if stored is None:
                    raise ActionError("No such execution on this server.", status=404)
                self._json({"job": stored})
                return
            if tail != "events":
                raise ActionError("Not found.", status=404)
            try:
                after = int(query.get("after", ["0"])[0])
            except ValueError as exc:
                raise ActionError("`after` must be an event sequence number.") from exc
            if query.get("stream", ["1"])[0] == "0":
                job = app.jobs.get(job_id)
                events = (
                    app.jobs.events(job_id, after) if job is not None
                    else app.jobs.stored_events(app.run, job_id, after)
                )
                self._json({"events": events, "job": job_view(job) if job else None})
                return
            self._stream_events(job_id, after)

        def _stream_events(self, job_id: str, after: int) -> None:
            """Newline-delimited JSON, flushed as it arrives.

            A dropped browser closes this response and nothing else: the child
            process keeps running, and a reconnect resumes from `after`.
            """
            job = app.jobs.get(job_id)
            if job is None:
                raise ActionError("No such execution on this server.", status=404)
            if job.run != str(pathlib.Path(app.run).resolve()):
                raise ActionError("That execution belongs to a different study.", status=403)
            self._headers(HTTPStatus.OK, "application/x-ndjson; charset=utf-8", None)
            remaining = STREAM_SECONDS
            try:
                for event in app.jobs.events(job_id, after):
                    after = event["seq"]
                    self.wfile.write((json.dumps(event) + "\n").encode("utf-8"))
                self.wfile.flush()
                while remaining > 0:
                    fresh = app.jobs.wait(job_id, after, timeout=min(remaining, 5.0))
                    remaining -= 5.0
                    for event in fresh:
                        after = event["seq"]
                        self.wfile.write((json.dumps(event) + "\n").encode("utf-8"))
                    if fresh:
                        self.wfile.flush()
                        remaining = STREAM_SECONDS
                    current = app.jobs.get(job_id)
                    if current is None or not current.as_dict()["active"]:
                        break
                final = app.jobs.get(job_id)
                if final is not None:
                    self.wfile.write((json.dumps({
                        "seq": final.last_seq, "at": final.last_event_at,
                        "channel": "job", "text": "", "job": job_view(final),
                    }) + "\n").encode("utf-8"))
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return

        def _serve_static(self, path: str) -> None:
            name = STATIC_FILES.get(path)
            if name is None:
                self._error("Not found.", 404)
                return
            resource = static_root.joinpath(name)
            payload = resource.read_bytes()
            if name == "index.html":
                payload = payload.replace(b"__RGRAPH_TOKEN__", app.csrf_token.encode("ascii"))
            content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
            if content_type.startswith("text/") or content_type == "application/javascript":
                content_type += "; charset=utf-8"
            self._headers(HTTPStatus.OK, content_type, len(payload))
            self.wfile.write(payload)

        # ── POST ───────────────────────────────────────────────────────────

        def do_POST(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            try:
                self._require_loopback_host()
                body = self._read_json()
                if self._launcher_post(parsed.path, body):
                    return
                if self._wizard_post(parsed.path, body):
                    return
                kit, run = self._load()
                if parsed.path == "/api/check":
                    gate_id = str(body.get("gate", ""))
                    if gate_id not in kit.gates:
                        raise ActionError(f"Unknown gate: {gate_id}")
                    result = evaluate_gate(run, kit, gate_id)
                    self._json({"gate": gate_result_view(result, kit, run)})
                    return
                if parsed.path == "/api/next/preview":
                    unit = body.get("unit")
                    self._json({"plan": preview_next(run, kit, app.approvals, unit)})
                    return
                if parsed.path == "/api/next/execute":
                    unit = str(body.get("unit", ""))
                    token = str(body.get("approval_token", ""))
                    self._json({"execution": execute_approved(run, kit, app.approvals, unit, token)})
                    return
                if parsed.path == "/api/challenge/preview":
                    gate = str(body.get("gate", ""))
                    self._json({"plan": preview_challenge(run, kit, app.approvals, gate)})
                    return
                if parsed.path == "/api/challenge/execute":
                    gate = str(body.get("gate", ""))
                    token = str(body.get("approval_token", ""))
                    self._json({"execution": execute_challenge(run, kit, app.approvals, gate, token)})
                    return
                if parsed.path == "/api/revise/preview":
                    gate = str(body.get("gate", ""))
                    self._json({"plan": preview_revision(run, kit, app.approvals, gate)})
                    return
                if parsed.path == "/api/revise/execute":
                    gate = str(body.get("gate", ""))
                    token = str(body.get("approval_token", ""))
                    self._json({"revision": execute_revision(run, kit, app.approvals, gate, token)})
                    return
                if parsed.path == "/api/jobs":
                    self._json({"job": self._create_job(run, kit, body)})
                    return
                if parsed.path.startswith("/api/jobs/") and parsed.path.endswith("/cancel"):
                    job_id = parsed.path.strip("/").split("/")[2]
                    job = app.jobs.cancel(
                        job_id, app.run, requested_by="local browser session",
                    )
                    self._json({"job": job_view(job)})
                    return
                raise ActionError("Not found.", status=404)
            except ActionError as exc:
                self._error(str(exc), exc.status)
            except JobError as exc:
                self._error(str(exc), exc.status)
            except Exception:
                traceback.print_exc()
                self._error("The local UI could not complete this request.", 500)

        def _create_job(self, run, kit, body: dict) -> dict:
            kind = str(body.get("kind", "unit"))
            token = str(body.get("approval_token", ""))
            target = str(body.get("target", ""))
            if kind == "unit":
                return start_unit_job(run, kit, app.approvals, app.jobs, target, token)
            if kind == "challenge":
                return start_challenge_job(run, kit, app.approvals, app.jobs, target, token)
            raise ActionError(f"Unknown execution kind: {kind}")

        # ── launcher routes ────────────────────────────────────────────────

        def _launcher_post(self, path: str, body: dict) -> bool:
            if path == "/api/run/open":
                app.discard_demo()
                app.open_run(str(body.get("path", "")))
                self._json({"opened": str(app.run)})
                return True
            if path == "/api/run/close":
                app.discard_demo()
                app.run = None
                self._json({"closed": True})
                return True
            if path == "/api/recent/forget":
                removed = recent_service.forget(str(body.get("path", "")))
                self._json({
                    "removed": removed,
                    "recent": recent_service.studies(),
                    "note": "Only the list entry was removed. The study was not touched.",
                })
                return True
            if path == "/api/demo/open":
                app.open_demo()
                self._json({
                    "opened": str(app.run),
                    "note": demo_service.SYNTHETIC_NOTE,
                })
                return True
            if path == "/api/demo/scenarios":
                self._json(demo_service.scenarios(self._kit()))
                return True
            return False

        # ── wizard routes ──────────────────────────────────────────────────

        def _wizard_post(self, path: str, body: dict) -> bool:
            if path == "/api/providers/detect":
                self._json(provider_service.detection_view(self._kit()))
                return True
            if path == "/api/providers/preview":
                kit = self._kit()
                try:
                    plan = provider_service.plan_from_selection(
                        kit, body.get("assignment", {})
                    )
                except ConfigError as exc:
                    raise ActionError(str(exc)) from exc
                self._json({"assignment": provider_service.assignment_view(kit, plan)})
                return True
            if path == "/api/providers/apply":
                self._json(self._apply_assignment(body))
                return True
            if path == "/api/preflight":
                self._json(self._preflight(body))
                return True
            if path == "/api/probe/preview":
                try:
                    kit, _ = load_assigned_kit(pathlib.Path(app.root))
                except ConfigError as exc:
                    raise ActionError(str(exc), status=409) from exc
                calls = probe_plan(kit)
                self._json({
                    "calls": calls,
                    "budget": len(calls),
                    "note": (
                        "Each line below is one real provider call, billed to your own "
                        "subscription. Nothing runs until you approve this exact list."
                    ),
                })
                return True
            if path == "/api/probe/run":
                self._json(self._run_probes(body))
                return True
            if path == "/api/study/validate":
                self._json({"study": self._validated_study(body)})
                return True
            if path == "/api/study/preview":
                details = self._validated_study(body)
                destination = self._validated_destination(body)
                self._json({"preview": study_service.write_preview(
                    destination, pathlib.Path(app.root), details,
                )})
                return True
            if path == "/api/study/create":
                self._json(self._create_study(body))
                return True
            return False

        def _validated_study(self, body: dict) -> dict:
            try:
                return study_service.normalise_details(
                    body.get("study", {}), study_service.now(),
                )
            except study_service.StudyError as exc:
                raise ActionError(str(exc)) from exc

        def _validated_destination(self, body: dict) -> pathlib.Path:
            raw = body.get("destination") or str(app.default_destination())
            try:
                return study_service.resolve_destination(raw)
            except study_service.StudyError as exc:
                raise ActionError(str(exc)) from exc

        def _create_study(self, body: dict) -> dict:
            """The wizard's only material write, and the last thing it does."""
            details = self._validated_study(body)
            destination = self._validated_destination(body)
            try:
                created = study_service.create_run(
                    pathlib.Path(app.root), destination, details, study_service.now(),
                )
            except study_service.StudyError as exc:
                raise ActionError(str(exc), status=409) from exc
            except OSError as exc:
                raise ActionError(f"The study could not be created: {exc}", status=409) from exc
            app.discard_demo()
            app.open_run(str(created))
            return {
                "run": str(created),
                "run_id": details["run_id"],
                "note": (
                    "The study was created and each human-authored file was sealed with "
                    "its own digest. The first checkpoint is now waiting for a human "
                    "decision, which is recorded at a terminal."
                ),
            }

        def _apply_assignment(self, body: dict) -> dict:
            kit = self._kit()
            try:
                plan = provider_service.plan_from_selection(kit, body.get("assignment", {}))
            except ConfigError as exc:
                raise ActionError(str(exc)) from exc
            scope = str(body.get("scope", "study"))
            if scope == "machine":
                target = machine_assignment_path()
            elif scope == "study":
                destination = body.get("destination")
                base = (
                    pathlib.Path(destination).expanduser().resolve().parent
                    if destination else pathlib.Path.cwd()
                )
                target = base / "assignment.yaml"
            else:
                raise ActionError("Choose either this study or this machine.")
            written = provider_service.write_assignment(target, plan)
            return {
                "written": str(written),
                "scope": scope,
                "assignment": provider_service.assignment_view(kit, plan),
            }

        def _preflight(self, body: dict) -> dict:
            try:
                findings = inspect_assignment(
                    pathlib.Path(app.root),
                    timeout=int(body.get("timeout", 60)),
                    probe_models=False,
                )
            except ConfigError as exc:
                raise ActionError(str(exc), status=409) from exc
            return findings_view(findings) | {
                "probed": False,
                "note": (
                    "No model was called. Model names stay UNVERIFIED until you "
                    "approve a probe."
                ),
            }

        def _run_probes(self, body: dict) -> dict:
            approved = body.get("approved_calls")
            if not isinstance(approved, int) or approved < 1:
                raise ActionError(
                    "Approve the exact number of provider calls before probing."
                )
            try:
                kit, _ = load_assigned_kit(pathlib.Path(app.root))
                calls = probe_plan(kit)
                if approved != len(calls):
                    raise ActionError(
                        f"The plan now needs {len(calls)} call(s); you approved "
                        f"{approved}. Review the plan again."
                    )
                findings = run_probes(kit, int(body.get("timeout", 60)), approved)
            except ConfigError as exc:
                raise ActionError(str(exc), status=409) from exc
            return findings_view(findings) | {"probed": True, "calls": len(calls)}

    return Handler


def create_server(
    root: pathlib.Path | str, run: pathlib.Path | str | None = None,
    host: str = "127.0.0.1", port: int = 8765,
) -> tuple[ThreadingHTTPServer, LocalUI]:
    if host not in LOOPBACKS:
        raise ValueError("the local UI may only bind to a loopback host: 127.0.0.1, localhost, or ::1")
    app = LocalUI(pathlib.Path(root), run, secrets.token_urlsafe(32))
    if app.has_run:
        # Load before binding so a broken study never leaves a half-working
        # server. A directory with no run is not broken; it opens the launcher.
        app.load()
        recent_service.remember(app.run)
    else:
        app.run = None
    server = ThreadingHTTPServer((host, port), _handler(app))
    server.daemon_threads = True
    return server, app


def serve(
    root: pathlib.Path | str, run: pathlib.Path | str | None = None, *,
    host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True,
) -> None:
    server, app = create_server(root, run, host, port)
    actual_host, actual_port = server.server_address[:2]
    display_host = "127.0.0.1" if actual_host in ("0.0.0.0", "::") else actual_host
    url = f"http://{display_host}:{actual_port}/"
    print(f"Local UI: {url}")
    if app.has_run:
        print(f"Study: {app.run}")
    else:
        print("No study selected yet — the browser opens the launcher.")
    print("Bound to this computer only. Press Ctrl-C to stop.")
    if open_browser:
        threading.Timer(0.15, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        print("\nLocal UI stopped.")
    finally:
        app.jobs.shutdown()
        app.discard_demo()
        server.server_close()
