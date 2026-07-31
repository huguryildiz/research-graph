"""Independence levels. The word 'independent' is never printed; a level is."""

from __future__ import annotations

from dataclasses import dataclass

from rgraph.config import Assignment, Gate

LEVELS = ("context_only", "separate_model", "separate_provider")
LABELS = {
    "context_only": "CONTEXT ONLY",
    "separate_model": "SEPARATE MODEL",
    "separate_provider": "SEPARATE PROVIDER",
}
CONTEXT_ONLY_NOTE = (
    "Reviewer uses a separate session, but the same model\n"
    "and provider. Correlated errors may remain."
)


@dataclass(frozen=True)
class SeparationVerdict:
    level: str | None
    status: str
    note: str | None = None


def rank(level: str) -> int:
    return LEVELS.index(level)


def level_for(producer: Assignment, reviewer: Assignment) -> str:
    if producer.provider != reviewer.provider:
        return "separate_provider"
    if producer.model != reviewer.model:
        return "separate_model"
    return "context_only"


def _level_from_identities(producer: str, reviewer: str) -> str:
    """Compare two recorded identity strings of the form 'provider/model'."""
    producer_provider, _, producer_model = producer.partition("/")
    reviewer_provider, _, reviewer_model = reviewer.partition("/")
    if producer_provider != reviewer_provider:
        return "separate_provider"
    if producer_model != reviewer_model:
        return "separate_model"
    return "context_only"


def evaluate(
    gate: Gate,
    producer: Assignment | None,
    reviewer: Assignment | None,
    *,
    recorded_producer: str | None = None,
    reviewer_identity: str | None = None,
) -> SeparationVerdict:
    """Decide the separation level for a gate.

    ``recorded_producer`` is the identity the produced artifact actually carries.
    When it is present it wins over ``assignment.yaml``: the configuration says
    who was meant to run the role, the artifact says who the run recorded, and
    only the second one is evidence.
    """
    if gate.separation_required is None:
        return SeparationVerdict(level=None, status="PASS")
    if producer is None or reviewer is None:
        return SeparationVerdict(level=None, status="FAIL", note="No assignment for this gate.")

    if recorded_producer and reviewer_identity:
        if recorded_producer == reviewer_identity:
            return SeparationVerdict(
                level="context_only", status="FAIL",
                note=f"The reviewed artifact records produced_by.identity = "
                     f"{recorded_producer},\nwhich is the identity deciding this gate.",
            )
        level = _level_from_identities(recorded_producer, reviewer_identity)
    else:
        level = level_for(producer, reviewer)
    if rank(level) < rank(gate.separation_required):
        return SeparationVerdict(
            level=level,
            status="FAIL",
            note=f"Gate {gate.id} requires at least {LABELS[gate.separation_required]}.",
        )
    if gate.separation_preferred and rank(level) < rank(gate.separation_preferred):
        note = (
            CONTEXT_ONLY_NOTE
            if level == "context_only"
            else (
                "Reviewer shares a provider with the producer. "
                f"{LABELS[gate.separation_preferred]} would be stronger."
            )
        )
        return SeparationVerdict(level=level, status="CAVEAT", note=note)
    return SeparationVerdict(level=level, status="PASS")
