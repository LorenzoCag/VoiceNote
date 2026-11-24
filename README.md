# VoiceNote

A local, privacy-first voice note app for Apple Silicon Macs: record audio, transcribe it with Whisper (MLX), and (soon) summarize it with a small language model. Nothing leaves your machine after the one-time model download.

**Status:** Phase 1 of 4 (recording + transcription). Summarization, UI, and history come next.

## Setup

Requires macOS on Apple Silicon, Python 3.11+, and [ffmpeg](https://ffmpeg.org) (used to decode non-WAV audio).

```bash
brew install ffmpeg            # skip if already installed
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

```bash
# Record until you press Enter, then transcribe
python -m voicenote record

# Record a fixed duration
python -m voicenote record --seconds 10

# Record without transcribing
python -m voicenote record --no-transcribe

# Transcribe an existing file (wav, mp3, m4a, flac, ogg, aiff, ...)
python -m voicenote transcribe path/to/audio.m4a
```

Recordings are saved to `data/recordings/` (git-ignored). Uploaded files are copied there too.

The first transcription downloads the Whisper model (~150 MB for base) into `~/.cache/huggingface`. After that everything runs offline; set `HF_HUB_OFFLINE=1` to enforce it.

### Microphone permission

macOS asks for microphone access the first time your terminal records. If you denied it, recordings are silently all zeros. VoiceNote detects this and warns you. Fix it in **System Settings > Privacy & Security > Microphone**, enable your terminal app, and restart the terminal.

## Configuration

Edit `config.toml` to change models; no code changes needed:

```toml
[transcription]
backend = "mlx-whisper"
model = "mlx-community/whisper-base-mlx"   # or whisper-small-mlx, whisper-large-v3-turbo, ...
language = ""                              # "" = auto-detect
```

## Project layout

```
config.toml                  model selection and paths
voicenote/
  config.py                  loads config.toml
  audio.py                   microphone recording, WAV saving, file import
  transcription/
    base.py                  Transcript/Segment types and Transcriber protocol
    mlx_whisper_backend.py   mlx-whisper implementation
    __init__.py              backend registry (add new backends here)
  cli.py                     command-line interface
```

Each backend returns a `Transcript` that includes the model name and inference time, so benchmarking different models later is straightforward.

## Roadmap

1. ~~Recording + Whisper transcription~~ (done)
2. Summarization with Qwen3-0.6B via MLX-LM
3. Streamlit UI, JSON storage, note history
4. End-to-end testing and docs
