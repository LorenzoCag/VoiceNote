"""Backend-agnostic summarization types.

Two layers keep models swappable:
  * `LLM`        - a raw text generator (one implementation per inference library).
  * `Summarizer` - prompts, chunking, JSON validation (in pipeline.py); works with any LLM.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Protocol


@dataclass
class Generation:
    text: str  # full model output, including any prefill
    prompt_tokens: int
    generation_tokens: int
    seconds: float
    peak_memory_gb: float = 0.0


class LLM(Protocol):
    model: str

    def generate(
        self,
        messages: list[dict],
        max_tokens: int,
        temperature: float,
        prefill: str = "",
    ) -> Generation:
        """Chat-complete `messages`. If `prefill` is given, the reply must start with it
        and the returned text includes it."""
        ...

    def count_tokens(self, text: str) -> int: ...


@dataclass
class Summary:
    summary: str
    key_points: list[str]
    action_items: list[str]
    model: str = ""
    # Run statistics, useful for benchmarking different models.
    elapsed_seconds: float = 0.0
    llm_calls: int = 0
    chunks: int = 1
    prompt_tokens: int = 0
    generation_tokens: int = 0
    peak_memory_gb: float = 0.0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class SummarizationError(RuntimeError):
    """The model never produced valid structured output."""
