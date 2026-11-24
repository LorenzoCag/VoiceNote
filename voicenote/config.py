"""Load settings from config.toml (stdlib only)."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.toml"


@dataclass(frozen=True)
class SummarizationConfig:
    backend: str = "mlx-lm"
    model: str = "mlx-community/Qwen3-0.6B-8bit"
    temperature: float = 0.1
    max_new_tokens: int = 700
    # Transcripts up to this many tokens are summarized in one pass; longer ones are
    # split into ~chunk_tokens pieces, summarized separately, then merged.
    max_input_tokens: int = 3000
    chunk_tokens: int = 1500


@dataclass(frozen=True)
class Config:
    sample_rate: int
    input_device: int | str | None  # None = system default microphone
    data_dir: Path
    transcription_backend: str
    transcription_model: str
    transcription_language: str | None  # None = auto-detect
    summarization: SummarizationConfig = SummarizationConfig()
    # True = never touch the network; models must already be downloaded (`python -m voicenote setup`).
    offline: bool = True

    @property
    def recordings_dir(self) -> Path:
        return self.data_dir / "recordings"


def load_config(path: Path | None = None) -> Config:
    path = Path(path) if path else DEFAULT_CONFIG_PATH
    with open(path, "rb") as f:
        raw = tomllib.load(f)

    data_dir = Path(raw.get("storage", {}).get("data_dir", "data"))
    if not data_dir.is_absolute():
        data_dir = PROJECT_ROOT / data_dir

    t = raw.get("transcription", {})
    s = raw.get("summarization", {})
    defaults = SummarizationConfig()
    return Config(
        offline=bool(raw.get("general", {}).get("offline", True)),
        sample_rate=int(raw.get("audio", {}).get("sample_rate", 16000)),
        input_device=raw.get("audio", {}).get("input_device") or None,
        data_dir=data_dir,
        transcription_backend=t.get("backend", "mlx-whisper"),
        transcription_model=t.get("model", "mlx-community/whisper-base-mlx"),
        transcription_language=t.get("language") or None,
        summarization=SummarizationConfig(
            backend=s.get("backend", defaults.backend),
            model=s.get("model", defaults.model),
            temperature=float(s.get("temperature", defaults.temperature)),
            max_new_tokens=int(s.get("max_new_tokens", defaults.max_new_tokens)),
            max_input_tokens=int(s.get("max_input_tokens", defaults.max_input_tokens)),
            chunk_tokens=int(s.get("chunk_tokens", defaults.chunk_tokens)),
        ),
    )
