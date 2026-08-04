"""Loopback-only HTTP server for the offline research-graph UI."""

from __future__ import annotations

import json
import mimetypes
import pathlib
import secrets
import threading
import traceback
import urllib.parse
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from types import SimpleNamespace

from rgraph.commands.check import load_for_run
from rgraph.config import ConfigError
from rgraph.gates import evaluate_gate
from rgraph.run import RunError
from rgraph.webui.actions import (
    ActionError, ApprovalStore, execute_approved, execute_challenge, execute_revision,
    preview_challenge, preview_next, preview_revision,
)
from rgraph.webui.views import gate_result_view, state_view, trace_view

MAX_BODY = 256 * 1024
LOOPBACKS = frozenset({"127.0.0.1", "localhost", "::1"})


class LocalUI:
    def __init__(self, root: pathlib.Path, run: pathlib.Path, csrf_token: str) -> None:
        self.root = root
        self.run = run
        self.csrf_token = csrf_token
        self.approvals = ApprovalStore()

    def load(self):
        return load_for_run(SimpleNamespace(root=str(self.root), run=str(self.run)))


def _handler(app: LocalUI):
    static_root = files("rgraph.webui").joinpath("static")

    class Handler(BaseHTTPRequestHandler):
        server_version = "rgraph-local-ui"

        def log_message(self, format: str, *args) -> None:
            return

        def _headers(self, status: int, content_type: str, length: int) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
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

        def _read_json(self) -> dict:
            if not secrets.compare_digest(
                self.headers.get("X-RGraph-Token", ""), app.csrf_token,
            ):
                raise ActionError("The local UI session token is missing or invalid.", status=403)
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

        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            try:
                self._require_loopback_host()
                if parsed.path == "/api/state":
                    kit, run = self._load()
                    self._json(state_view(run, kit))
                    return
                if parsed.path == "/api/trace":
                    claim = urllib.parse.parse_qs(parsed.query).get("claim", [""])[0]
                    if not claim:
                        raise ActionError("Choose a claim to trace.")
                    kit, run = self._load()
                    self._json(trace_view(run, kit, claim))
                    return
                self._serve_static(parsed.path)
            except ActionError as exc:
                self._error(str(exc), exc.status)
            except Exception:
                traceback.print_exc()
                self._error("The local UI could not complete this request.", 500)

        def _serve_static(self, path: str) -> None:
            names = {
                "/": "index.html", "/index.html": "index.html",
                "/app.css": "app.css", "/app.js": "app.js",
            }
            name = names.get(path)
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

        def do_POST(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            try:
                self._require_loopback_host()
                body = self._read_json()
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
                raise ActionError("Not found.", status=404)
            except ActionError as exc:
                self._error(str(exc), exc.status)
            except Exception:
                traceback.print_exc()
                self._error("The local UI could not complete this request.", 500)

    return Handler


def create_server(
    root: pathlib.Path | str, run: pathlib.Path | str, host: str = "127.0.0.1", port: int = 8765,
) -> tuple[ThreadingHTTPServer, LocalUI]:
    if host not in LOOPBACKS:
        raise ValueError("the local UI may only bind to a loopback host: 127.0.0.1, localhost, or ::1")
    app = LocalUI(pathlib.Path(root), pathlib.Path(run), secrets.token_urlsafe(32))
    # Load before binding so configuration errors never leave a half-working server.
    app.load()
    server = ThreadingHTTPServer((host, port), _handler(app))
    server.daemon_threads = True
    return server, app


def serve(
    root: pathlib.Path | str, run: pathlib.Path | str, *, host: str = "127.0.0.1",
    port: int = 8765, open_browser: bool = True,
) -> None:
    server, _ = create_server(root, run, host, port)
    actual_host, actual_port = server.server_address[:2]
    display_host = "127.0.0.1" if actual_host in ("0.0.0.0", "::") else actual_host
    url = f"http://{display_host}:{actual_port}/"
    print(f"Local UI: {url}")
    print("Bound to this computer only. Press Ctrl-C to stop.")
    if open_browser:
        threading.Timer(0.15, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        print("\nLocal UI stopped.")
    finally:
        server.server_close()
