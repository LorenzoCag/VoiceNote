# VoiceNote

A local, privacy-first voice note app for Apple Silicon Macs. Record or upload audio, transcribe it with Whisper (MLX), and summarize it with a small language model (MLX-LM), all in a simple page in your browser. After a one-time model download nothing leaves your machine.

**Status:** Phase 3 of 4 (web UI, local note storage, history). Remaining: end-to-end polish and docs.

## Setup

Requires macOS on Apple Silicon, Python 3.11+, and [ffmpeg](https://ffmpeg.org) (decodes non-WAV audio).

```bash
brew install ffmpeg            # skip if already installed
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m voicenote setup      # one-time model download: the ONLY step that needs internet
```

## Use it

```bash
python -m voicenote ui         # opens http://localhost:8501
```

- **New note:** record in the browser (it asks for microphone permission and lets you pick the mic) or upload an audio file, then press *Transcribe and summarize*.
- **A note** shows the summary, key points, action items, the transcript, and the audio. Download it as Markdown or JSON, or delete it.
- **History** lives in the sidebar. Everything is stored under `data/` (git-ignored):
  - `data/recordings/<id>.wav`: the audio
  - `data/notes/<id>.json`: transcript, summary, and metadata, one readable JSON file per note. No database.

The server only listens on `127.0.0.1`, so nothing on your network can reach it, and Streamlit's usage telemetry is switched off in `.streamlit/config.toml`.

### Command line

The same pipeline is available without the UI:

```bash
python -m voicenote record --summarize           # record from the mic, transcribe, summarize
python -m voicenote transcribe audio.m4a --summarize
python -m voicenote summarize notes.txt          # a text transcript or an audio file
python -m voicenote summarize notes.txt --json   # raw JSON
python -m voicenote devices                      # list microphones (CLI recording only)
```

## Fully offline

`python -m voicenote setup` downloads the models named in `config.toml` into `~/.cache/huggingface`. With `offline = true` (the default), every other command, including the UI, blocks all network access and tells you to run `setup` if a model is missing.

### Verifying it's local

- **Wi-Fi off.** Turn on airplane mode and use the app normally.
- **Block and log the network:**
  ```bash
  python scripts/prove_offline.py summarize notes.txt
  ```
  runs the real pipeline with every non-local connection and DNS lookup blocked and logged, and reports `PASS` only if it finished with zero attempts. (Running `setup` through it fails by design, which shows it can catch attempts.)
- **From outside the process.** While the UI is running, `lsof -a -p <pid> -i -n -P` should list only `127.0.0.1` sockets. Activity Monitor's Network tab or a firewall like [LuLu](https://objective-see.org/products/lulu.html) show the same.
- There is no cloud SDK, API key, or HTTP client in `voicenote/`.

## Microphone notes (CLI recording)

macOS asks for microphone access the first time your terminal records. If you denied it, recordings are silently all zeros; VoiceNote detects this and warns you. Fix it in **System Settings > Privacy & Security > Microphone**, enable your terminal app, and restart it. Plugging in headphones can switch the default input to the headphone jack's mic (silent if the headphones have no mic); set `input_device` in `config.toml` or pass `--device`.

The browser recorder in the UI avoids all of this: the browser handles permission and device choice.

## Summarization output

Every summary is validated JSON:

```json
{"summary": "...", "key_points": ["..."], "action_items": ["..."]}
```

plus run statistics (`model`, `elapsed_seconds`, `generation_tokens`, `peak_memory_gb`, `chunks`, `warnings`).

How it stays reliable with a tiny model:

- **Few-shot prompt, thinking off.** Two worked examples (one with tasks, one without) show the format; Qwen3's `<think>` mode is disabled.
- **Prefilled `{`**, low temperature, and **validation with up to 3 attempts**. Each retry shows the model its error and raises the temperature slightly. If all fail you get a clear error, never garbage; in the UI the transcript is kept and a *Try again* button appears.
- **Grounding check.** Key points and action items that share too few words with the transcript are dropped and reported in `warnings` (e.g. when a 0.6B model parrots its prompt examples).
- **Long transcripts.** Up to `max_input_tokens` (default 3000, roughly 20 minutes of speech) the transcript is summarized in one pass. Longer ones are split on segment boundaries into `chunk_tokens` pieces, summarized separately, then merged.

### Choosing a model

Quality depends heavily on model size. Results from `python eval/run.py` (5 cases, coarse checks):

| Model | Passed | Time per note | Peak memory | Notes |
|-------|--------|---------------|-------------|-------|
| `Qwen3-0.6B-8bit` | 3/5 | 0.4-3 s | ~1.5 GB | Fine on simple lists; on rambling notes it tends to leave out owners or action items, merge ideas, or copy its prompt examples |
| `Qwen3-1.7B-8bit` | 5/5 | 1-3.5 s | ~2.6 GB | Correct owners and deadlines on the meeting note; handles chunked merge |

To switch, change `model` under `[summarization]` in `config.toml`, then run `python -m voicenote setup` once to download it. The 0.6B model is the default (it is the target for later quantization and fine-tuning experiments); use 1.7B for better day-to-day results.

## Configuration

Edit `config.toml`; no code changes needed:

```toml
[general]
offline = true                             # never use the network (except `setup`)

[audio]
input_device = ""                          # CLI recording: name substring or index; "" = system default

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

The UI picks up config changes on the next page reload.

## Testing and evaluation

```bash
python -m unittest discover tests          # 50+ offline tests: pipeline, storage, service, and the UI itself
python eval/run.py                         # eval cases against the model in config.toml
python eval/run.py --model mlx-community/Qwen3-1.7B-8bit
python eval/run.py --case meeting_rambling -v
```

The unit tests use fake models and run in about a second; the UI tests drive the real `app.py` with Streamlit's `AppTest`. `eval/cases.json` lists the test transcripts in `eval/transcripts/` with coarse expectations (key facts mentioned, action-item counts, chunking happened) and reports pass/fail, time, and memory per case. It is the starting point for comparing models, quantization levels, prompts, and fine-tuned checkpoints. Add your own cases as you find failures.

## Project layout

```
app.py                       the web UI (Streamlit)
config.toml                  model selection and settings
.streamlit/config.toml       UI theme, localhost-only server, telemetry off
voicenote/
  config.py                  loads config.toml
  models.py                  one-time download (`setup`), offline mode, cache checks
  audio.py                   microphone recording, WAV saving, file import
  storage.py                 Note type and JSON file storage
  service.py                 workflow: save audio -> transcribe -> summarize -> store
  transcription/             Transcript types, backend registry, mlx-whisper backend
  summarization/             Summary types, prompts, pipeline (chunking, validation,
                             retry, grounding), mlx-lm backend, backend registry
  cli.py                     command-line interface
scripts/prove_offline.py     run any command with the network blocked and logged
eval/                        eval cases, transcripts, runner
tests/                       offline tests
```

To add an inference backend (llama.cpp, a quantized variant, ...), implement the small `LLM` protocol (`generate` and `count_tokens`) and register it; the prompts, chunking, and validation work unchanged. Transcription backends work the same way. MLX streams are per-thread, so the UI runs all model calls on one dedicated worker thread.

## Roadmap

1. ~~Recording + Whisper transcription~~ (done)
2. ~~Summarization with Qwen3 via MLX-LM~~ (done)
3. ~~Web UI, JSON storage, note history~~ (done)
4. End-to-end polish, benchmarking, quantization and fine-tuning experiments

Next idea here would be to develop an ios version of the app.
