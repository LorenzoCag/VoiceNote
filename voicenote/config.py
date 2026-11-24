"""Load settings from config.toml (stdlib only)."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.toml"


@dataclass(frozen=True)
class Config:
    sample_rate: int
    input_device: int | str | None  # None = system default microphone
    data_dir: Path
    transcription_backend: str
    transcription_model: str
    transcription_language: str | None  # None = auto-detect

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
    return Config(
        sample_rate=int(raw.get("audio", {}).get("sample_rate", 16000)),
        input_device=raw.get("audio", {}).get("input_device") or None,
        data_dir=data_dir,
        transcription_backend=t.get("backend", "mlx-whisper"),
        transcription_model=t.get("model", "mlx-community/whisper-base-mlx"),
        transcription_language=t.get("language") or None,
    )
