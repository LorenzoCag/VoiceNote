"""Whisper transcription on Apple Silicon via mlx-whisper."""

from __future__ import annotations

import time
from pathlib import Path

from voicenote.transcription.base import Segment, Transcript


class MLXWhisperTranscriber:
    def __init__(self, model: str, language: str | None = None):
        self.model = model
        self.language = language

    def transcribe(self, audio_path: Path) -> Transcript:
        import mlx_whisper  # lazy: importing MLX is slow

        audio_path = Path(audio_path)
        if not audio_path.is_file():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        start = time.perf_counter()
        # The model is downloaded on first use, then loaded from the local HF cache.
        # condition_on_previous_text=False reduces repetition loops on long audio.
        result = mlx_whisper.transcribe(
            str(audio_path),
            path_or_hf_repo=self.model,
            language=self.language,
            condition_on_previous_text=False,
            verbose=None,
        )
        elapsed = time.perf_counter() - start

        return Transcript(
            text=result["text"].strip(),
            language=result.get("language"),
            segments=[
                Segment(start=s["start"], end=s["end"], text=s["text"].strip())
                for s in result.get("segments", [])
            ],
            model=self.model,
            elapsed_seconds=elapsed,
        )
