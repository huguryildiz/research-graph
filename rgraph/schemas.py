"""Schema registry. Loads schemas/*.schema.json once and validates against them."""

from __future__ import annotations

import functools
import json
import pathlib
from dataclasses import dataclass

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


@dataclass(frozen=True)
class SchemaError:
    path: str
    message: str


class SchemaRegistry:
    def __init__(self, directory: pathlib.Path) -> None:
        self._validators: dict[str, Draft202012Validator] = {}
        resources: list[tuple[str, Resource]] = []
        documents: dict[str, dict] = {}
        for path in sorted(directory.glob("*.schema.json")):
            document = json.loads(path.read_text(encoding="utf-8"))
            documents[path.name.removesuffix(".schema.json")] = document
            resources.append((document["$id"], Resource.from_contents(document)))
        registry = Registry().with_resources(resources)
        for name, document in documents.items():
            if name.startswith("_"):
                continue
            self._validators[name] = Draft202012Validator(document, registry=registry)

    def has(self, artifact_id: str) -> bool:
        return artifact_id in self._validators

    def validate(self, artifact_id: str, document) -> list[SchemaError]:
        validator = self._validators.get(artifact_id)
        if validator is None:
            return [SchemaError(path="", message=f"no schema for '{artifact_id}'")]
        errors = []
        for error in sorted(validator.iter_errors(document), key=lambda e: list(e.absolute_path)):
            path = "/".join(str(part) for part in error.absolute_path) or "<root>"
            errors.append(SchemaError(path=path, message=error.message))
        return errors


@functools.lru_cache(maxsize=8)
def registry(root: pathlib.Path) -> SchemaRegistry:
    return SchemaRegistry(pathlib.Path(root) / "schemas")
