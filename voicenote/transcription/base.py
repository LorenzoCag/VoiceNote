"""Backend-agnostic transcription types."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class Segment:
    start: float
    end: float
    text: str


@dataclass
class Transcript:
    text: str
    language: str | None
    segments: list[Segment] = field(default_factory=list)
    model: str = ""
    elapsed_seconds: float = 0.0  # wall-clock inference time (useful for later benchmarking)

    def to_dict(self) -> dict:
        return asdict(self)


class Transcriber(Protocol):
    model: str

    def transcribe(self, audio_path: Path) -> Transcript: ...
