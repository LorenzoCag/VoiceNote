"""Model availability: one-time download (`setup`) and offline checks.

Models live in the standard Hugging Face cache (~/.cache/huggingface). In offline mode the
app never touches the network; if a model is missing it says so instead of trying to fetch it.
"""

from __future__ import annotations

import os
from pathlib import Path

from voicenote.config import Config


class ModelNotAvailable(RuntimeError):
    """A configured model is not in the local cache and offline mode forbids downloading."""


def configured_models(config: Config) -> dict[str, str]:
    return {
        "transcription": config.transcription_model,
        "summarization": config.summarization.model,
    }


def apply_offline_mode(config: Config) -> None:
    """Block all Hugging Face network access. Must run before huggingface_hub is imported."""
    if config.offline:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"


def is_cached(model: str, cache_dir: str | Path | None = None) -> bool:
    """True if the model is usable from the local cache without any network access.

    Deliberately checks only what the loaders need (config.json + weight files) rather than
    every file in the repo: mlx-lm and mlx-whisper skip README/.gitattributes, and
    snapshot_download(local_files_only=True) would wrongly call such a cache incomplete.
    """
    if Path(model).expanduser().exists():  # a local model directory
        return True
    from huggingface_hub import try_to_load_from_cache

    config_path = try_to_load_from_cache(model, "config.json", cache_dir=cache_dir)
    if not isinstance(config_path, str):  # None, or a "known missing" marker
        return False
    snapshot = Path(config_path).parent
    weights = [*snapshot.glob("*.safetensors"), *snapshot.glob("*.npz")]
    return any(w.exists() for w in weights)  # exists() follows symlinks, so broken links don't count


def require(config: Config, kind: str) -> None:
    """Raise ModelNotAvailable if offline and the model for `kind` isn't cached."""
    if not config.offline:
        return
    model = configured_models(config)[kind]
    if not is_cached(model):
        raise ModelNotAvailable(
            f"The {kind} model '{model}' is not downloaded and offline mode is on.\n"
            f"Run once while online:  python -m voicenote setup"
        )


def download_all(config: Config, report=print) -> None:
    """Download every configured model into the local cache (needs network)."""
    from huggingface_hub import snapshot_download

    for kind, model in configured_models(config).items():
        if Path(model).expanduser().exists():
            report(f"{kind}: {model} (local directory, nothing to download)")
            continue
        report(f"{kind}: downloading {model} ...")
        snapshot_download(model)
        report(f"{kind}: ready")
