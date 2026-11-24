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


def is_cached(model: str) -> bool:
    if Path(model).expanduser().exists():  # a local model directory
        return True
    from huggingface_hub import snapshot_download

    try:
        snapshot_download(model, local_files_only=True)
        return True
    except Exception:
        return False


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
