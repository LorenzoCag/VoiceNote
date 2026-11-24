# VoiceNote

A local, privacy-first voice note app for Apple Silicon Macs: record audio, transcribe it with Whisper (MLX), and summarize it with a small language model (MLX-LM). Nothing leaves your machine after the one-time model downloads.

**Status:** Phase 2 of 4 (recording, transcription, summarization on the command line). The UI and note history come next.

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
# Record until you press Enter, then transcribe (add --summarize to summarize too)
python -m voicenote record
python -m voicenote record --seconds 10 --summarize

# Choose a microphone
python -m voicenote devices
python -m voicenote record --device "MacBook Pro Microphone"

# Transcribe an existing file (wav, mp3, m4a, flac, ogg, aiff, ...)
python -m voicenote transcribe path/to/audio.m4a --summarize

# Summarize a plain-text transcript, or an audio file (transcribes first)
python -m voicenote summarize notes.txt
python -m voicenote summarize notes.txt --json     # raw JSON, e.g. for scripts
```

Recordings are saved to `data/recordings/` (git-ignored). Imported files are copied there too.

The first run of each model downloads it into `~/.cache/huggingface` (Whisper base ~150 MB, Qwen3-0.6B-8bit ~0.7 GB). After that everything runs offline; set `HF_HUB_OFFLINE=1` to enforce it.

### Microphone permission

macOS asks for microphone access the first time your terminal records. If you denied it, recordings are silently all zeros. VoiceNote detects this and warns you. Fix it in **System Settings > Privacy & Security > Microphone**, enable your terminal app, and restart the terminal.

Plugging in headphones can switch the default input to the headphone jack's mic (silent if the headphones have no mic). Set `input_device` in `config.toml` or pass `--device` to pick one explicitly.

## Summarization output

Every summary is validated JSON:

```json
{"summary": "...", "key_points": ["..."], "action_items": ["..."]}
```

plus run statistics (`model`, `elapsed_seconds`, `generation_tokens`, `peak_memory_gb`, `chunks`, `warnings`).

How it stays reliable with a tiny model:

- **Few-shot prompt, thinking off.** Two worked examples (one with tasks, one without) show the format; Qwen3's `<think>` mode is disabled.
- **Prefilled `{`** so the model starts directly with JSON, low temperature, and **validation with one retry** that shows the model its error. If it fails twice you get a clear error, never garbage.
- **Grounding check.** Key points and action items that share too few words with the transcript are dropped and reported in `warnings` (e.g. when a 0.6B model parrots its prompt examples).
- **Long transcripts.** Up to `max_input_tokens` (default 3000, roughly 20 minutes of speech) the transcript is summarized in one pass. Longer ones are split on sentence/segment boundaries into `chunk_tokens` pieces, summarized separately, then merged.

### Choosing a model

Quality depends heavily on model size. Results from `python eval/run.py` (5 cases, coarse checks):

| Model | Passed | Time per note | Peak memory | Notes |
|-------|--------|---------------|-------------|-------|
| `Qwen3-0.6B-8bit` | 3/5 | 0.4-3 s | ~1.5 GB | Fine on simple lists; on rambling notes it tends to leave action items empty, merge ideas, or copy its prompt examples |
| `Qwen3-1.7B-8bit` | 5/5 | 1-3.5 s | ~2.6 GB | Correct owners and deadlines on the meeting note; handles chunked merge |

To switch, change `model` under `[summarization]` in `config.toml`. The 0.6B model is the default (it is the stated target for later quantization and fine-tuning experiments); use 1.7B when you want better day-to-day results.

## Configuration

Edit `config.toml` to change models; no code changes needed:

```toml
[audio]
input_device = ""                          # name substring or index; "" = system default

[transcription]
backend = "mlx-whisper"
model = "mlx-community/whisper-base-mlx"   # or whisper-small-mlx, whisper-large-v3-turbo, ...
language = ""                              # "" = auto-detect

[summarization]
backend = "mlx-lm"
model = "mlx-community/Qwen3-0.6B-8bit"    # or Qwen3-0.6B-4bit, Qwen3-1.7B-8bit, ...
temperature = 0.1
max_input_tokens = 3000                    # longer transcripts are chunked, then merged
chunk_tokens = 1500
```

## Testing and evaluation

```bash
python -m unittest discover tests          # offline unit tests (scripted fake model, instant)
python eval/run.py                         # run eval cases against the model in config.toml
python eval/run.py --model mlx-community/Qwen3-1.7B-8bit
python eval/run.py --case meeting_rambling -v
```

`eval/cases.json` lists the test transcripts in `eval/transcripts/` with coarse expectations (key facts mentioned, action-item counts, chunking happened). It reports pass/fail, time, and memory per case, which makes it the starting point for comparing models, quantization levels, prompts, and fine-tuned checkpoints. Add your own cases as you find failures.

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
  summarization/
    base.py                  Summary type and LLM protocol (generate + count_tokens)
    mlx_lm_backend.py        mlx-lm implementation
    prompts.py               system prompts and few-shot examples
    pipeline.py              chunking, JSON validation, retry, grounding
    __init__.py              backend registry
  cli.py                     command-line interface
eval/                        eval cases, transcripts, runner
tests/                       offline unit tests
```

To add an inference backend (llama.cpp, a quantized variant, ...), implement the small `LLM` protocol (`generate` and `count_tokens`) and register it; the prompts, chunking, and validation work unchanged. Transcription backends work the same way.

## Roadmap

1. ~~Recording + Whisper transcription~~ (done)
2. ~~Summarization with Qwen3 via MLX-LM~~ (done)
3. Streamlit UI, JSON storage, note history
4. End-to-end testing and docs
