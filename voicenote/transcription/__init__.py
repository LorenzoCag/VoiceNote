"""Speech-to-text backends.

To add a backend (e.g. whisper.cpp, faster-whisper, a quantized variant):
  1. Create a module with a class implementing `Transcriber`.
  2. Register it in `_BACKENDS` below.
  3. Select it with `backend = "..."` in config.toml.
"""

from __future__ import annotations

from voicenote.config import Config
from voicenote.transcription.base import Segment, Transcriber, Transcript


def _mlx_whisper(config: Config) -> Transcriber:
    from voicenote.transcription.mlx_whisper_backend import MLXWhisperTranscriber

    return MLXWhisperTranscriber(model=config.transcription_model, language=config.transcription_language)


# Factories are lazy so unused backends never import their heavy dependencies.
_BACKENDS = {
    "mlx-whisper": _mlx_whisper,
}


def get_transcriber(config: Config) -> Transcriber:
    try:
        factory = _BACKENDS[config.transcription_backend]
    except KeyError:
        raise ValueError(
            f"Unknown transcription backend '{config.transcription_backend}'. Available: {sorted(_BACKENDS)}"
        ) from None
    return factory(config)


__all__ = ["Segment", "Transcriber", "Transcript", "get_transcriber"]
