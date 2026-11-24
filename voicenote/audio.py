"""Audio handling: microphone recording and saving/importing audio files.

Recordings are mono 16-bit PCM WAV at the configured sample rate (16 kHz by
default, which is what Whisper expects).
"""

from __future__ import annotations

import shutil
import threading
import wave
from datetime import datetime
from pathlib import Path

import numpy as np

AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".aiff", ".aif", ".mp4", ".webm"}


def new_recording_path(recordings_dir: Path, suffix: str = ".wav") -> Path:
    recordings_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = recordings_dir / f"{stamp}{suffix}"
    n = 1
    while path.exists():  # two recordings in the same second must not overwrite each other
        path = recordings_dir / f"{stamp}-{n}{suffix}"
        n += 1
    return path


def save_wav(path: Path, samples: np.ndarray, sample_rate: int) -> None:
    """Write int16 mono samples to a WAV file."""
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(samples.astype(np.int16).tobytes())


def list_input_devices() -> list[tuple[int, str, bool]]:
    """Return (index, name, is_default) for every device that can record."""
    import sounddevice as sd

    default = sd.default.device[0]
    if default is None or default < 0:
        default = sd.query_devices(kind="input")["index"]
    return [
        (i, d["name"], i == default)
        for i, d in enumerate(sd.query_devices())
        if d["max_input_channels"] > 0
    ]


def input_device_name(device: int | str | None = None) -> str:
    """Human-readable name of the device that `record(device=...)` will use."""
    import sounddevice as sd

    try:
        return sd.query_devices(device, kind="input")["name"]
    except Exception:
        return str(device)


def record(
    sample_rate: int = 16000,
    max_seconds: float | None = None,
    stop_event: threading.Event | None = None,
    device: int | str | None = None,
) -> np.ndarray:
    """Record from a microphone until stopped; returns int16 mono samples.

    `device` is a device index or name substring (None = system default input).
    Stops when `stop_event` is set or `max_seconds` elapses, whichever is first.
    """
    import sounddevice as sd  # imported lazily so file-only workflows don't need PortAudio

    stop_event = stop_event or threading.Event()
    chunks: list[np.ndarray] = []

    def callback(indata, frames, time_info, status):
        if status:
            print(f"[audio warning] {status}")
        chunks.append(indata.copy())

    with sd.InputStream(
        samplerate=sample_rate, channels=1, dtype="int16", device=device, callback=callback
    ):
        stop_event.wait(timeout=max_seconds)

    if not chunks:
        return np.zeros(0, dtype=np.int16)
    return np.concatenate(chunks, axis=0).reshape(-1)


def import_audio(src: Path, recordings_dir: Path) -> Path:
    """Copy an existing audio file into the recordings folder and return the new path."""
    src = Path(src).expanduser()
    if not src.is_file():
        raise FileNotFoundError(f"Audio file not found: {src}")
    if src.suffix.lower() not in AUDIO_EXTENSIONS:
        raise ValueError(f"Unsupported audio type '{src.suffix}'. Supported: {sorted(AUDIO_EXTENSIONS)}")
    if src.resolve().parent == Path(recordings_dir).resolve():
        return src  # already in the recordings folder; don't duplicate it
    dest = new_recording_path(recordings_dir, suffix=src.suffix.lower())
    shutil.copy2(src, dest)
    return dest


def is_silent(samples: np.ndarray) -> bool:
    """True if every sample is exactly zero (typical when mic permission is denied)."""
    return len(samples) > 0 and not np.any(samples)


def duration_seconds(samples: np.ndarray, sample_rate: int) -> float:
    return len(samples) / sample_rate
