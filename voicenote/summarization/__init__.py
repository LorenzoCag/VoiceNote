"""Summarization with a local small language model.

To add an inference backend (llama.cpp, a quantized variant, ...):
  1. Create a class implementing `LLM` (see base.py).
  2. Register it in `_BACKENDS` below.
  3. Select it with `backend = "..."` under [summarization] in config.toml.
"""

from __future__ import annotations

from voicenote.config import SummarizationConfig
from voicenote.summarization.base import LLM, SummarizationError, Summary
from voicenote.summarization.pipeline import Summarizer


def _mlx_lm(config: SummarizationConfig) -> LLM:
    from voicenote.summarization.mlx_lm_backend import MLXLMModel

    return MLXLMModel(config.model)


# Factories are lazy so unused backends never import their heavy dependencies.
_BACKENDS = {
    "mlx-lm": _mlx_lm,
}


def get_summarizer(config: SummarizationConfig) -> Summarizer:
    try:
        factory = _BACKENDS[config.backend]
    except KeyError:
        raise ValueError(
            f"Unknown summarization backend '{config.backend}'. Available: {sorted(_BACKENDS)}"
        ) from None
    return Summarizer(factory(config), config)


__all__ = ["LLM", "SummarizationError", "Summarizer", "Summary", "get_summarizer"]
