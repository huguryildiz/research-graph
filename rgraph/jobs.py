"""Background provider execution: one child process per approved plan.

A browser tab is not a terminal. It can be closed, reloaded, or left open on a
laptop that sleeps, so the thing that must survive is the *record* of what was
started, not the page that started it. Every invocation here gets an immutable
job id, an ordered event sequence, a bounded redacted transcript, and a state
that is only ever set from something observed — `RUNNING` means a child process
exists, and a server that restarts marks what it can no longer see `INTERRUPTED`
rather than claiming it is still going.

Nothing in this module builds a command line. It runs the argv a `Plan` already
carries, with `shell=False`, and never reads a byte from the browser into it.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import pathlib
import re
import signal
import subprocess
import sys
import threading
import time as _time
import uuid
from dataclasses import asdict, dataclass, field

from rgraph.runner import resolve_executable
from rgraph.services import joblog

QUEUED = "QUEUED"
RUNNING = "RUNNING"
VALIDATING = "VALIDATING"
COMPLETE = "COMPLETE"
FAILED = "FAILED"
CANCELLING = "CANCELLING"
CANCELLED = "CANCELLED"
INTERRUPTED = "INTERRUPTED"

ACTIVE_STATES = frozenset({QUEUED, RUNNING, VALIDATING, CANCELLING})
FINAL_STATES = frozenset({COMPLETE, FAILED, CANCELLED, INTERRUPTED})

# Bounds. Provider output is untrusted and unbounded; a browser tab is neither.
MAX_LINE_CHARS = 1000
MAX_EVENTS = 1200
MAX_STREAM_CHARS = 512 * 1024
CANCEL_GRACE_SECONDS = 5.0

# Control sequences that would move the cursor, repaint, retitle a window, or
# smuggle an escape through the DOM. Stripped before anything is stored, so the
# bounded transcript is text and only text.
_CSI = re.compile(r"\x1b\[[0-9;?<>=]*[ -/]*[@-~]")
_OSC = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
_OTHER_ESCAPE = re.compile(r"\x1b[@-_][^\x1b]*?(?:\x1b\\|\x07)|\x1b[ -/]*[0-~]")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Credential shapes worth removing on sight. This is a heuristic: it reduces the
# chance that a browser pane shows a secret. It does not establish that provider
# output contains none, and no screen may say that it does.
_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"\b(?:gh[pousr]|github_pat)_[A-Za-z0-9_]{16,}"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),
    re.compile(r"(?i)\b(?:bearer|token|api[_-]?key|secret|password|passwd)\b"
               r"\s*[:=]\s*[\"']?([^\s\"']{8,})"),
)
_CREDENTIAL_ENV_HINTS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "PASSWD", "CREDENTIAL")
REDACTED = "[redacted]"


def _now() -> str:
    return (
        _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)
        .isoformat().replace("+00:00", "Z")
    )


def scrub(text: str) -> str:
    """Remove control sequences, keeping line breaks and tabs."""
    text = _OSC.sub("", text)
    text = _CSI.sub("", text)
    text = _OTHER_ESCAPE.sub("", text)
    return _CONTROL.sub("", text)


class Redactor:
    """Best-effort removal of credential-shaped text from provider output.

    Two sources: values this process was told are secret (session and approval
    tokens, credential environment values) which are removed exactly, and
    patterns that look like keys, which are removed heuristically. Callers must
    describe the second kind as a reduction in exposure, never as a guarantee.
    """

    def __init__(self, literals: tuple[str, ...] = ()) -> None:
        self._literals = tuple(sorted(
            {value for value in literals if isinstance(value, str) and len(value) >= 8},
            key=len, reverse=True,
        ))

    @staticmethod
    def environment_literals() -> tuple[str, ...]:
        values = []
        for name, value in os.environ.items():
            upper = name.upper()
            if any(hint in upper for hint in _CREDENTIAL_ENV_HINTS) and len(value) >= 8:
                values.append(value)
        return tuple(values)

    def with_literals(self, *extra: str) -> Redactor:
        return Redactor(self._literals + tuple(extra))

    def __call__(self, text: str) -> str:
        for literal in self._literals:
            if literal and literal in text:
                text = text.replace(literal, REDACTED)
        for pattern in _SECRET_PATTERNS:
            if pattern.groups:
                text = pattern.sub(
                    lambda match: match.group(0).replace(match.group(1), REDACTED), text
                )
            else:
                text = pattern.sub(REDACTED, text)
        return text


@dataclass
class JobEvent:
    seq: int
    at: str
    channel: str  # "output" | "state" | "notice"
    text: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Job:
    """One approved invocation, and everything observed about it."""

    id: str
    run: str
    kind: str                    # "unit" | "challenge"
    target: str                  # unit id or gate id
    title: str
    role: str | None
    provider: str
    model: str
    argv: list[str]
    inputs: list[dict]
    expected_outputs: list[str]
    declared_paths: list[str]
    log: str | None
    prompt_sha256: str | None = None
    state: str = QUEUED
    created_at: str = field(default_factory=_now)
    started_at: str | None = None
    ended_at: str | None = None
    pid: int | None = None
    exit_code: int | None = None
    cancel_requested_at: str | None = None
    cancel_requested_by: str | None = None
    failure_category: str | None = None
    validation: dict | None = None
    produced: list[str] = field(default_factory=list)
    truncated: bool = False
    last_event_at: str | None = None
    last_seq: int = 0

    def elapsed_seconds(self) -> float | None:
        if self.started_at is None:
            return None
        end = self.ended_at or _now()
        try:
            start = _dt.datetime.fromisoformat(self.started_at.replace("Z", "+00:00"))
            stop = _dt.datetime.fromisoformat(end.replace("Z", "+00:00"))
        except ValueError:
            return None
        return max(0.0, (stop - start).total_seconds())

    def as_dict(self) -> dict:
        body = asdict(self)
        body["elapsed_seconds"] = self.elapsed_seconds()
        body["active"] = self.state in ACTIVE_STATES
        return body


class JobError(Exception):
    """A refusal from the job manager, safe to show."""

    def __init__(self, message: str, *, status: int = 409) -> None:
        super().__init__(message)
        self.status = status


WATCH_INTERVAL_SECONDS = 2.0
WATCH_REPORT_LIMIT = 8


def _observe_tree(root: pathlib.Path) -> dict[str, tuple[int, int]]:
    """Size and modification time of every file in the study, `logs/` aside.

    Deliberately not a digest: this answers "did something change, and when",
    cheaply and often. What the bytes actually are is settled once, at the end,
    by the acceptance rules that already recompute every hash.
    """
    state: dict[str, tuple[int, int]] = {}
    try:
        for path in root.rglob("*"):
            try:
                if not path.is_file():
                    continue
                relative = path.relative_to(root)
            except (OSError, ValueError):
                continue
            if relative.parts and relative.parts[0] == "logs":
                continue
            try:
                info = path.stat()
            except OSError:
                continue
            state[relative.as_posix()] = (info.st_size, info.st_mtime_ns)
    except OSError:
        return state
    return state


def _describe_change(name: str, before, after, declared: frozenset[str]) -> str:
    inside = "declared output" if name in declared else "not a declared output"
    if before is None:
        return f"created {name} ({after[0]} bytes, {inside})"
    if after is None:
        return f"removed {name} ({inside})"
    return f"wrote {name} ({after[0]} bytes, {inside})"


def _relative_log(log_path, run_root: pathlib.Path) -> str | None:
    """The provider log as a path inside the study, resolving symlinked roots.

    On macOS `/tmp` is a link to `/private/tmp`, so a run directory and a plan
    built from it can disagree about their own prefix. Both sides are resolved
    before comparing, and a log genuinely outside the study keeps its full path
    rather than being dropped.
    """
    if log_path is None:
        return None
    resolved = pathlib.Path(log_path).resolve()
    try:
        return str(resolved.relative_to(pathlib.Path(run_root).resolve()))
    except ValueError:
        return str(resolved)


def _jobs_dir(run_root: pathlib.Path) -> pathlib.Path:
    # Below `logs/`, which every integrity snapshot in this codebase already
    # excludes. An operational record must never look like a research artifact.
    return joblog.jobs_dir(run_root)


class JobManager:
    """Owns every child process this server started, and their transcripts."""

    def __init__(self, redactor: Redactor | None = None) -> None:
        self._jobs: dict[str, Job] = {}
        self._events: dict[str, list[JobEvent]] = {}
        self._streamed: dict[str, int] = {}
        self._processes: dict[str, subprocess.Popen] = {}
        self._lock = threading.RLock()
        self._changed = threading.Condition(self._lock)
        self._redactor = redactor or Redactor(Redactor.environment_literals())

    # ── reading ────────────────────────────────────────────────────────────

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return job

    def require(self, job_id: str, run_root: pathlib.Path | None = None) -> Job:
        job = self.get(job_id)
        if job is None:
            raise JobError("No such execution on this server.", status=404)
        if run_root is not None and job.run != str(pathlib.Path(run_root).resolve()):
            raise JobError("That execution belongs to a different study.", status=403)
        return job

    def for_run(self, run_root: pathlib.Path) -> list[Job]:
        target = str(pathlib.Path(run_root).resolve())
        with self._lock:
            return sorted(
                (job for job in self._jobs.values() if job.run == target),
                key=lambda item: item.created_at, reverse=True,
            )

    def active(self, run_root: pathlib.Path) -> Job | None:
        return next(
            (job for job in self.for_run(run_root) if job.state in ACTIVE_STATES), None
        )

    def events(self, job_id: str, after: int = 0) -> list[dict]:
        with self._lock:
            return [
                event.as_dict() for event in self._events.get(job_id, [])
                if event.seq > after
            ]

    def wait(self, job_id: str, after: int, timeout: float) -> list[dict]:
        """Block until there is something after `after`, or the timeout expires."""
        deadline = timeout
        with self._changed:
            while True:
                fresh = [
                    event.as_dict() for event in self._events.get(job_id, [])
                    if event.seq > after
                ]
                if fresh:
                    return fresh
                job = self._jobs.get(job_id)
                if job is None or job.state in FINAL_STATES:
                    return []
                if deadline <= 0:
                    return []
                started = _dt.datetime.now()
                self._changed.wait(min(deadline, 1.0))
                deadline -= (_dt.datetime.now() - started).total_seconds()

    # ── recording ──────────────────────────────────────────────────────────

    def _emit(self, job: Job, channel: str, text: str) -> None:
        with self._changed:
            events = self._events.setdefault(job.id, [])
            job.last_seq += 1
            job.last_event_at = _now()
            event = JobEvent(job.last_seq, job.last_event_at, channel, text)
            events.append(event)
            if len(events) > MAX_EVENTS:
                del events[: len(events) - MAX_EVENTS]
                job.truncated = True
            self._append_event_line(job, event)
            self._changed.notify_all()

    def _set_state(self, job: Job, state: str, note: str | None = None) -> None:
        with self._changed:
            job.state = state
            if state in FINAL_STATES and job.ended_at is None:
                job.ended_at = _now()
            self._changed.notify_all()
        self._emit(job, "state", note or state)
        self._persist(job)

    def _persist(self, job: Job) -> None:
        """Write the machine record and the human transcript side by side.

        Both are named for when they ran and what they ran, so the directory
        listing answers "which file is last night's u01" without opening one.
        """
        record = job.as_dict()
        directory = _jobs_dir(pathlib.Path(job.run))
        try:
            directory.mkdir(parents=True, exist_ok=True)
            (directory / f"{joblog.slug(record)}.json").write_text(
                json.dumps(record, indent=2) + "\n", encoding="utf-8",
            )
        except OSError:
            # A study on a read-only or full disk still deserves a working
            # console; the in-memory record remains authoritative for this server.
            return
        with self._lock:
            history = [event.as_dict() for event in self._events.get(job.id, [])]
        joblog.write_transcript(job.run, record, history)

    def _append_event_line(self, job: Job, event: JobEvent) -> None:
        directory = _jobs_dir(pathlib.Path(job.run))
        try:
            directory.mkdir(parents=True, exist_ok=True)
            name = f"{joblog.slug(job.as_dict())}.events.jsonl"
            with (directory / name).open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event.as_dict()) + "\n")
        except OSError:
            pass

    # ── starting ───────────────────────────────────────────────────────────

    def _register(self, job: Job) -> Job:
        with self._lock:
            running = self.active(pathlib.Path(job.run))
            if running is not None:
                raise JobError(
                    f"{running.target} is already running in this study "
                    f"({running.state}). One provider execution at a time."
                )
            self._jobs[job.id] = job
            self._events[job.id] = []
        self._emit(job, "state", QUEUED)
        self._persist(job)
        return job

    def start(
        self,
        *,
        run_root: pathlib.Path,
        kind: str,
        target: str,
        title: str,
        role: str | None,
        plan,
        inputs: list[dict],
        expected_outputs: list[str],
        declared_paths: list[str],
        prompt_sha256: str | None,
        finish,
        secrets: tuple[str, ...] = (),
    ) -> Job:
        """Register a job and run `plan.argv` as a child process in the background.

        `finish(job, exit_code, output)` runs on the worker thread after the
        process exits, in the `VALIDATING` state. Whatever it returns is stored
        as the job's validation result; raising marks the job `FAILED`.
        """
        if not plan.argv:
            raise JobError("This provider has no executable command template.")
        run_root = pathlib.Path(run_root).resolve()
        job = Job(
            id=uuid.uuid4().hex,
            run=str(run_root),
            kind=kind,
            target=target,
            title=title,
            role=role,
            provider=plan.provider,
            model=plan.model,
            argv=list(plan.argv),
            inputs=inputs,
            expected_outputs=list(expected_outputs),
            declared_paths=sorted(declared_paths),
            log=_relative_log(plan.log_path, run_root),
            prompt_sha256=prompt_sha256,
        )
        self._register(job)
        redactor = self._redactor.with_literals(*secrets)
        worker = threading.Thread(
            target=self._run, args=(job, plan, finish, redactor),
            name=f"rgraph-job-{job.id[:8]}", daemon=True,
        )
        worker.start()
        return job

    def _spawn(self, plan) -> subprocess.Popen:
        host_bin = str(pathlib.Path(os.path.abspath(sys.executable)).parent)
        inherited_path = os.environ.get("PATH", "")
        provider_path = host_bin + (os.pathsep + inherited_path if inherited_path else "")
        creation: dict = {}
        if os.name == "nt":
            creation["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            # Its own session, so cancellation can signal exactly this process
            # group and nothing that happened to be nearby.
            creation["start_new_session"] = True
        return subprocess.Popen(
            # a list: never a shell string, and argv[0] resolved against the
            # PATH this child is given so a Windows `claude.cmd` starts at all.
            resolve_executable(plan.argv, provider_path),
            shell=False,
            cwd=plan.cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,        # one ordered stream, as the CLI captures it
            text=True,
            bufsize=1,
            env={
                **os.environ,
                "PATH": provider_path,
                "RGRAPH_ACTIVE_INVOCATION": plan.unit,
            },
            **creation,
        )

    def _run(self, job: Job, plan, finish, redactor: Redactor) -> None:
        try:
            process = self._spawn(plan)
        except (OSError, ValueError) as exc:
            job.failure_category = "provider-start"
            self._emit(job, "notice", f"The provider could not be started: {exc}")
            self._set_state(job, FAILED)
            return

        with self._lock:
            self._processes[job.id] = process
            job.pid = process.pid
            job.started_at = _now()
        self._set_state(job, RUNNING, f"{RUNNING} (pid {process.pid})")
        stop_watching = threading.Event()
        watcher = threading.Thread(
            target=self._watch_files, args=(job, stop_watching), daemon=True,
            name=f"rgraph-watch-{job.id[:8]}",
        )
        watcher.start()

        captured: list[str] = []
        streamed = 0
        try:
            if process.stdin is not None:
                try:
                    process.stdin.write(plan.stdin_text)
                except (BrokenPipeError, OSError):
                    pass
                finally:
                    try:
                        process.stdin.close()
                    except OSError:
                        pass
            if process.stdout is not None:
                for line in process.stdout:
                    captured.append(line)
                    text = scrub(line).rstrip("\n")
                    if len(text) > MAX_LINE_CHARS:
                        text = text[:MAX_LINE_CHARS] + " …[line truncated]"
                    if streamed >= MAX_STREAM_CHARS:
                        if not job.truncated:
                            job.truncated = True
                            self._emit(
                                job, "notice",
                                "Live output reached its display limit. The complete "
                                "provider log on disk continues to be written.",
                            )
                        continue
                    streamed += len(text) + 1
                    self._emit(job, "output", redactor(text))
            exit_code = process.wait()
        except Exception as exc:  # noqa: BLE001 - the worker must never die silently
            job.failure_category = "stream"
            self._emit(job, "notice", f"Reading provider output failed: {exc}")
            exit_code = process.poll() if process.poll() is not None else -1
        finally:
            with self._lock:
                self._processes.pop(job.id, None)
            # One last look while the provider is still the only thing that has
            # written here, then stop: everything after this line is the host's
            # own bookkeeping and reporting it as provider activity would lie.
            stop_watching.set()
            watcher.join(timeout=WATCH_INTERVAL_SECONDS + 1.0)

        output = "".join(captured)
        if plan.log_path is not None:
            try:
                pathlib.Path(plan.log_path).parent.mkdir(parents=True, exist_ok=True)
                pathlib.Path(plan.log_path).write_text(output, encoding="utf-8")
            except OSError as exc:
                self._emit(job, "notice", f"The provider log could not be written: {exc}")

        job.exit_code = exit_code
        cancelled = job.cancel_requested_at is not None
        self._set_state(
            job, VALIDATING,
            "VALIDATING — the process has exited; its output is not yet an artifact.",
        )
        try:
            job.validation = finish(job, exit_code, output)
        except Exception as exc:  # noqa: BLE001 - report, never crash the server
            job.failure_category = job.failure_category or "validation"
            job.validation = {
                "ok": False,
                "problems": [f"output validation could not complete: {exc}"],
            }
        job.produced = list((job.validation or {}).get("produced", []))
        if cancelled:
            job.failure_category = job.failure_category or "cancelled"
            self._set_state(
                job, CANCELLED,
                "CANCELLED — the provider was stopped; anything it already wrote is "
                "listed under artifacts and was not sealed.",
            )
        elif (job.validation or {}).get("ok"):
            self._set_state(job, COMPLETE)
        else:
            job.failure_category = job.failure_category or (
                "provider-exit" if exit_code != 0 else "output-invalid"
            )
            self._set_state(job, FAILED)

    def _watch_files(self, job: Job, stop: threading.Event) -> None:
        """Report what the provider is doing to the study while it is doing it.

        Nothing here interprets provider output, so nothing here is specific to
        any provider: it is the same filesystem observation the acceptance rules
        make before and after a run, taken repeatedly. It says which files
        changed and whether each one was declared — never what the provider
        "decided" or "intended", which this cannot know.
        """
        root = pathlib.Path(job.run)
        declared = frozenset(job.declared_paths)
        previous = _observe_tree(root)
        while True:
            stopping = stop.wait(WATCH_INTERVAL_SECONDS)
            current = _observe_tree(root)
            changed = sorted(
                name for name in previous.keys() | current.keys()
                if previous.get(name) != current.get(name)
            )
            if changed:
                for name in changed[:WATCH_REPORT_LIMIT]:
                    self._emit(job, "activity", _describe_change(
                        name, previous.get(name), current.get(name), declared,
                    ))
                if len(changed) > WATCH_REPORT_LIMIT:
                    self._emit(job, "activity", (
                        f"and {len(changed) - WATCH_REPORT_LIMIT} more file(s) "
                        "changed in this interval"
                    ))
            if stopping:
                return
            previous = current

    # ── stopping ───────────────────────────────────────────────────────────

    def cancel(self, job_id: str, run_root: pathlib.Path, requested_by: str) -> Job:
        job = self.require(job_id, run_root)
        if job.state in FINAL_STATES:
            raise JobError(f"{job.target} already finished ({job.state}).")
        if job.state == CANCELLING:
            return job
        with self._lock:
            process = self._processes.get(job_id)
            job.cancel_requested_at = _now()
            job.cancel_requested_by = requested_by
        self._set_state(
            job, CANCELLING,
            "CANCELLING — stopping the provider process. Anything it already wrote "
            "stays on disk and is re-checked afterwards.",
        )
        if process is None:
            self._set_state(job, CANCELLED, "CANCELLED — no child process was running.")
            return job
        threading.Thread(
            target=self._terminate, args=(job, process), daemon=True,
            name=f"rgraph-cancel-{job.id[:8]}",
        ).start()
        return job

    def _terminate(self, job: Job, process: subprocess.Popen) -> None:
        self._signal(process, hard=False)
        try:
            process.wait(timeout=CANCEL_GRACE_SECONDS)
            return
        except subprocess.TimeoutExpired:
            pass
        self._emit(
            job, "notice",
            f"The provider did not stop within {CANCEL_GRACE_SECONDS:.0f}s; escalating.",
        )
        self._signal(process, hard=True)
        try:
            process.wait(timeout=CANCEL_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            self._emit(job, "notice", "The provider process could not be stopped.")

    @staticmethod
    def _signal(process: subprocess.Popen, *, hard: bool) -> None:
        """Signal only what this manager started.

        On POSIX the child got its own session, so its process-group id equals
        its pid; anything else means the group is not ours and only the process
        itself is signalled. On Windows the child owns a new process group, and
        `taskkill /T` ends that tree.
        """
        if process.poll() is not None:
            return
        if os.name == "nt":  # pragma: no cover - exercised on Windows CI only
            if not hard:
                try:
                    process.send_signal(signal.CTRL_BREAK_EVENT)
                    return
                except (OSError, ValueError):
                    pass
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                    capture_output=True, timeout=10, check=False,
                )
                return
            except (OSError, subprocess.SubprocessError):
                pass
            try:
                process.kill()
            except OSError:
                pass
            return
        sig = signal.SIGKILL if hard else signal.SIGTERM
        try:
            group = os.getpgid(process.pid)
        except (OSError, AttributeError):
            group = None
        try:
            if group == process.pid:
                os.killpg(group, sig)
            else:
                process.send_signal(sig)
        except (OSError, ValueError):
            pass

    # ── after a restart ────────────────────────────────────────────────────

    def adopt_records(self, run_root: pathlib.Path) -> list[dict]:
        """Read job records this server did not start, and tell the truth about them.

        A record left in an active state belongs to a process this server never
        had a handle on. It is reported `INTERRUPTED`, never `RUNNING`.
        """
        directory = _jobs_dir(pathlib.Path(run_root))
        if not directory.is_dir():
            return []
        known = {job.id for job in self.for_run(run_root)}
        out: list[dict] = []
        for path, record in joblog.stored(run_root):
            if record["id"] in known:
                continue
            if record.get("state") in ACTIVE_STATES:
                record["state"] = INTERRUPTED
                record["active"] = False
                record["failure_category"] = record.get("failure_category") or "interrupted"
                record["interrupted_note"] = (
                    "This execution was started by an earlier server process. "
                    "Its outcome cannot be observed from here, so it is not "
                    "reported as running."
                )
                try:
                    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
                except OSError:
                    pass
            record["adopted"] = True
            out.append(record)
        return out

    def stored_events(self, run_root: pathlib.Path, job_id: str, after: int = 0) -> list[dict]:
        """Bounded transcript of a job this server no longer holds in memory."""
        record = joblog.find(run_root, job_id)
        if record is None:
            return []
        return joblog.events(run_root, record, after)[-MAX_EVENTS:]

    def shutdown(self) -> None:
        with self._lock:
            processes = list(self._processes.values())
        for process in processes:
            self._signal(process, hard=False)
