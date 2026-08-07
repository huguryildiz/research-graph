"""Which copy of rgraph is answering, and where its configuration comes from.

"It worked yesterday" is usually two installations. This reports what can be
observed locally — the interpreter, the package directory, the kit root, the
effective assignment — and declines to guess anything it cannot see. It makes
no network request.
"""

from __future__ import annotations

import pathlib
import sys

from rgraph import __version__
from rgraph.config import machine_assignment_path, resolve_assignment


def _install_kind(package_dir: pathlib.Path) -> tuple[str, str]:
    """A short label for this installation and one sentence saying why.

    Honest by construction: every branch below is a fact about the filesystem.
    Where the evidence is ambiguous, the label says so rather than picking.
    """
    parts = package_dir.resolve().parts
    if (package_dir.parent / "graph.yaml").exists():
        return (
            "source checkout",
            "The package sits beside graph.yaml, so this is a working copy of the "
            "repository rather than a released build.",
        )
    if "site-packages" not in parts and "dist-packages" not in parts:
        return (
            "unknown layout",
            "The package is outside a site-packages directory and beside no "
            "graph.yaml; what produced it cannot be determined from here.",
        )
    for marker, label, detail in (
        ("uv", "uv tool", "The package lives under a uv tool directory."),
        ("pipx", "pipx", "The package lives under a pipx venv."),
    ):
        if any(part == marker or part.startswith(f"{marker}-") or part == f".{marker}"
               for part in parts):
            return label, detail
    if (package_dir.parent / f"__editable__.research_graph-{__version__}.pth").exists() \
            or any(package_dir.parent.glob("__editable__*research?graph*")):
        return (
            "editable install",
            "An editable install points this import back at a source checkout.",
        )
    return (
        "installed package",
        "The package was installed into an environment; whether it came from a "
        "wheel or an sdist is not recorded in a way this can read.",
    )


def installation(root: pathlib.Path | str, run: pathlib.Path | str | None) -> dict:
    package_dir = pathlib.Path(__file__).resolve().parent.parent
    kind, why = _install_kind(package_dir)
    kit_root = pathlib.Path(root).resolve()
    assignment = resolve_assignment(pathlib.Path(root))
    return {
        "version": __version__,
        "python": str(pathlib.Path(sys.executable)),
        "python_version": sys.version.split()[0],
        "package": str(package_dir),
        "kit_root": str(kit_root),
        "packaged_kit": str((package_dir / "kit").resolve())
        if (package_dir / "kit" / "graph.yaml").exists() else None,
        "cwd": str(pathlib.Path.cwd()),
        "run": str(pathlib.Path(run).resolve()) if run is not None else None,
        # The reference plate is a document this installation either carries or
        # does not; the browser hides its link rather than offering a dead one.
        "architecture": (kit_root / "architecture.html").is_file(),
        "install_kind": kind,
        "install_detail": why,
        "assignment": str(assignment) if assignment is not None else None,
        "machine_assignment": str(machine_assignment_path()),
        "update_note": (
            "This screen makes no network request. To check for a newer release, "
            "look at the project's releases page yourself; a branch is not a "
            "release, and rgraph will not claim one is."
        ),
    }
