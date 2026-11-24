"""Command-line entry point.

    python -m voicenote record                # record until you press Enter, then transcribe
    python -m voicenote record --seconds 10   # record a fixed duration
    python -m voicenote record --summarize    # ...and summarize the transcript
    python -m voicenote transcribe FILE       # transcribe an existing audio file
    python -m voicenote summarize FILE        # summarize a .txt transcript or an audio file
    python -m voicenote devices               # list microphones
    python -m voicenote setup                 # one-time model download (the only online step)
"""

from __future__ import annotations

import argparse
import json
import threading
from pathlib import Path

from voicenote import audio, models
from voicenote.config import load_config
from voicenote.summarization import SummarizationError, Summary, get_summarizer
from voicenote.transcription import Transcript, get_transcriber

TEXT_EXTENSIONS = {".txt", ".md"}


def _print_transcript(t: Transcript) -> None:
    print("\n--- Transcript " + "-" * 50)
    print(t.text or "(no speech detected)")
    print("-" * 65)
    print(f"model={t.model}  language={t.language}  inference={t.elapsed_seconds:.2f}s")


def _print_summary(s: Summary) -> None:
    print("\n--- Summary " + "-" * 53)
    print(s.summary)
    print("\nKey points:")
    for p in s.key_points or ["(none)"]:
        print(f"  - {p}")
    print("\nAction items:")
    for a in s.action_items or ["(none)"]:
        print(f"  - {a}")
    print("-" * 65)
    tps = s.generation_tokens / s.elapsed_seconds if s.elapsed_seconds else 0
    print(
        f"model={s.model}  time={s.elapsed_seconds:.2f}s  calls={s.llm_calls}  chunks={s.chunks}  "
        f"gen_tokens={s.generation_tokens}  ~{tps:.0f} tok/s  peak_mem={s.peak_memory_gb:.2f}GB"
    )
    for w in s.warnings:
        print(f"  note: {w}")


def _transcribe(config, path: Path) -> Transcript:
    models.require(config, "transcription")
    print(f"Transcribing {path} ...")
    transcript = get_transcriber(config).transcribe(path)
    _print_transcript(transcript)
    return transcript


def _summarize(config, transcript: Transcript | str, as_json: bool = False) -> int:
    models.require(config, "summarization")
    if not as_json:
        print("\nSummarizing ...")
    try:
        summary = get_summarizer(config.summarization).summarize(transcript)
    except ValueError as e:  # empty transcript
        print(f"\nCannot summarize: {e}")
        return 1
    except SummarizationError as e:
        print(f"\nSummarization failed: {e}")
        return 1
    if as_json:
        print(json.dumps(summary.to_dict(), indent=2, ensure_ascii=False))
    else:
        _print_summary(summary)
    return 0


def cmd_setup(args, config) -> int:
    print("Downloading the models named in config.toml (the only step that needs internet)...\n")
    try:
        models.download_all(config)
    except Exception as e:
        print(f"\nDownload failed: {e}\nCheck your internet connection and run `python -m voicenote setup` again.")
        return 1
    print("\nAll models are ready. VoiceNote now works fully offline.")
    return 0


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
        transcript = _transcribe(config, path)
        if args.summarize:
            return _summarize(config, transcript)
    return 0


def cmd_transcribe(args, config) -> int:
    try:
        path = audio.import_audio(args.file, config.recordings_dir)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}")
        return 1
    print(f"Audio file: {path}")
    transcript = _transcribe(config, path)
    if args.summarize:
        return _summarize(config, transcript)
    return 0


def cmd_summarize(args, config) -> int:
    file: Path = args.file.expanduser()
    if not file.is_file():
        print(f"Error: file not found: {file}")
        return 1

    if file.suffix.lower() in TEXT_EXTENSIONS:
        return _summarize(config, file.read_text(encoding="utf-8"), as_json=args.json)

    try:
        path = audio.import_audio(file, config.recordings_dir)
    except ValueError as e:
        print(f"Error: {e}")
        return 1
    transcript = _transcribe(config, path)
    return _summarize(config, transcript, as_json=args.json)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="voicenote", description="Local voice note transcription and summarization")
    parser.add_argument("--config", type=Path, help="path to an alternate config.toml")
    sub = parser.add_subparsers(dest="command", required=True)

    rec = sub.add_parser("record", help="record from the microphone and transcribe")
    rec.add_argument("--seconds", type=float, help="record for a fixed duration instead of until Enter")
    rec.add_argument("--no-transcribe", action="store_true", help="only save the recording")
    rec.add_argument("--summarize", action="store_true", help="also summarize the transcript")
    rec.add_argument("--device", help="microphone index or name (see `devices`); default from config")
    rec.set_defaults(func=cmd_record)

    dev = sub.add_parser("devices", help="list available microphones")
    dev.set_defaults(func=cmd_devices)

    st = sub.add_parser("setup", help="download the configured models once (needs internet)")
    st.set_defaults(func=cmd_setup)

    tr = sub.add_parser("transcribe", help="transcribe an existing audio file")
    tr.add_argument("file", type=Path)
    tr.add_argument("--summarize", action="store_true", help="also summarize the transcript")
    tr.set_defaults(func=cmd_transcribe)

    sm = sub.add_parser("summarize", help="summarize a .txt transcript or an audio file")
    sm.add_argument("file", type=Path)
    sm.add_argument("--json", action="store_true", help="print the raw JSON result only")
    sm.set_defaults(func=cmd_summarize)

    args = parser.parse_args(argv)
    config = load_config(args.config)
    if args.command != "setup":  # setup is the one command allowed to use the network
        models.apply_offline_mode(config)
    try:
        return args.func(args, config)
    except models.ModelNotAvailable as e:
        print(f"\nError: {e}")
        return 1
