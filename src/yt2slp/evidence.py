"""Preserve the difference between video evidence and reconstruction hypotheses."""
from dataclasses import dataclass
from enum import Enum
from typing import Generic, TypeVar

T = TypeVar("T")


class Provenance(str, Enum):
    """How a value relates to the source video, not its numerical precision."""

    OBSERVED = "observed"
    INFERRED = "inferred"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Evidence(Generic[T]):
    """A sourced value; unknown values must be None, never guessed defaults.

    Simulator output is inferred with respect to the target video. An observed
    value requires a video source/time reference supplied by its caller.
    """

    value: T | None
    provenance: Provenance
    source: str

    def __post_init__(self) -> None:
        if not isinstance(self.provenance, Provenance):
            raise ValueError("provenance must be a Provenance enum")
        if (self.value is None) != (self.provenance == Provenance.UNKNOWN):
            raise ValueError("only unknown evidence may have no value")
        if not self.source.strip():
            raise ValueError("evidence requires a source or an explanation of what is unknown")
