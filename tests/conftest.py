import pathlib
import shutil

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture
def example_run(tmp_path):
    """A writable copy of example-run. Never mutate the committed one."""
    target = tmp_path / "run"
    shutil.copytree(ROOT / "example-run", target)
    return target


@pytest.fixture
def reseal():
    """Re-stamp a whole run the way a re-run would, digests and links together.

    A test that edits one artifact and wants a single check to object needs the
    chain repaired first, or staleness answers before the check under test does.
    """
    import json

    from rgraph.commands.seal import seal_document
    from rgraph.config import ARTIFACTS, PAYLOAD_ARTIFACTS

    def _reseal(run_dir):
        current: dict[str, str] = {}
        for artifact_id in ARTIFACTS:
            payload_name = PAYLOAD_ARTIFACTS.get(artifact_id)
            path = run_dir / (
                f"{artifact_id}.meta.json" if payload_name else f"{artifact_id}.json"
            )
            if not path.exists():
                continue
            document = json.loads(path.read_text(encoding="utf-8"))
            document, _ = seal_document(
                document, current, run_dir / payload_name if payload_name else None
            )
            current[artifact_id] = document["content_hash"]
            path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        for path in sorted((run_dir / "gates").glob("*.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            for reference in record.get("inputs", []):
                fresh = current.get(reference["artifact_id"])
                if fresh:
                    reference["content_hash"] = fresh
            path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        from rgraph.hashing import document_hash

        meta_path = run_dir / "meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta.pop("content_hash", None)
        meta["content_hash"] = document_hash(meta)
        meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    return _reseal
