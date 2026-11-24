"""Command-line entry point for Phase 1.

    python -m voicenote record                # record until you press Enter, then transcribe
    python -m voicenote record --seconds 10   # record a fixed duration
    python -m voicenote transcribe FILE       # transcribe an existing audio file
    python -m voicenote devices               # list microphones
"""

from __future__ import annotations

import argparse
import threading
from pathlib import Path

from voicenote import audio
from voicenote.config import load_config
from voicenote.transcription import Transcript, get_transcriber


def _print_transcript(t: Transcript) -> None:
    print("\n--- Transcript " + "-" * 50)
    print(t.text or "(no speech detected)")
    print("-" * 65)
    print(f"model={t.model}  language={t.language}  inference={t.elapsed_seconds:.2f}s")


def _transcribe(config, path: Path) -> None:
    print(f"Transcribing {path} (first run downloads the model; later runs are offline)...")
    _print_transcript(get_transcriber(config).transcribe(path))


def cmd_devices(args, config) -> int:
    print("Input devices (* = system default):")
    for index, name, is_default in audio.list_input_devices():
        print(f"  {'*' if is_default else ' '} {index}: {name}")
    print("\nUse one with:  python -m voicenote record --device <index or name>")
    return 0


def _resolve_device(device: str | int | None):
    """Turn '3' into 3; leave names (matched as substrings by PortAudio) as-is."""
    if isinstance(device, str) and device.strip().isdigit():
        return int(device)
    return device


def cmd_record(args, config) -> int:
    device = _resolve_device(args.device if args.device is not None else config.input_device)
    print(f"Microphone: {audio.input_device_name(device)}")

    stop = threading.Event()
    if args.seconds:
        print(f"Recording for {args.seconds}s...")
    else:
        print("Recording... press Enter to stop.")
        threading.Thread(target=lambda: (input(), stop.set()), daemon=True).start()

    try:
        samples = audio.record(
            config.sample_rate, max_seconds=args.seconds, stop_event=stop, device=device
        )
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130
    except Exception as e:  # e.g. unknown/unavailable device
        print(f"\nCould not open the microphone: {e}\nRun `python -m voicenote devices` to see options.")
        return 1

    if len(samples) == 0:
        print("No audio captured. Check microphone permissions for your terminal.")
        return 1

    path = audio.new_recording_path(config.recordings_dir)
    audio.save_wav(path, samples, config.sample_rate)
    print(f"Saved {audio.duration_seconds(samples, config.sample_rate):.1f}s recording to {path}")

    if audio.is_silent(samples):
        # A real mic always has some noise floor; exact zeros mean macOS blocked access.
        print(
            "\nWarning: the recording is completely silent. macOS is probably blocking microphone\n"
            "access for this app. Open System Settings > Privacy & Security > Microphone, enable\n"
            "your terminal (Terminal, iTerm, Cursor, ...), restart it, and try again."
        )
        return 1

    if not args.no_transcribe:
        _transcribe(config, path)
    return 0


def cmd_transcribe(args, config) -> int:
    try:
        path = audio.import_audio(args.file, config.recordings_dir)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}")
        return 1
    print(f"Audio file: {path}")
    _transcribe(config, path)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="voicenote", description="Local voice note transcription")
    parser.add_argument("--config", type=Path, help="path to an alternate config.toml")
    sub = parser.add_subparsers(dest="command", required=True)

    rec = sub.add_parser("record", help="record from the microphone and transcribe")
    rec.add_argument("--seconds", type=float, help="record for a fixed duration instead of until Enter")
    rec.add_argument("--no-transcribe", action="store_true", help="only save the recording")
    rec.add_argument("--device", help="microphone index or name (see `devices`); default from config")
    rec.set_defaults(func=cmd_record)

    dev = sub.add_parser("devices", help="list available microphones")
    dev.set_defaults(func=cmd_devices)

    tr = sub.add_parser("transcribe", help="transcribe an existing audio file")
    tr.add_argument("file", type=Path)
    tr.set_defaults(func=cmd_transcribe)

    args = parser.parse_args(argv)
    return args.func(args, load_config(args.config))
