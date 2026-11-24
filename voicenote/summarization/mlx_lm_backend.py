"""Text generation on Apple Silicon via mlx-lm."""

from __future__ import annotations

import time

from voicenote.summarization.base import Generation


class MLXLMModel:
    def __init__(self, model: str):
        self.model = model
        self._model = None
        self._tokenizer = None

    def _load(self):
        if self._model is None:
            from mlx_lm import load  # lazy: importing MLX is slow

            # Downloaded on first use, then loaded from the local HF cache.
            self._model, self._tokenizer = load(self.model)
        return self._model, self._tokenizer

    def count_tokens(self, text: str) -> int:
        _, tokenizer = self._load()
        return len(tokenizer.encode(text))

    def generate(
        self,
        messages: list[dict],
        max_tokens: int,
        temperature: float,
        prefill: str = "",
    ) -> Generation:
        from mlx_lm import stream_generate
        from mlx_lm.sample_utils import make_sampler

        model, tokenizer = self._load()
        # enable_thinking=False turns off Qwen3's <think> reasoning (slow, unhelpful for
        # a 0.6B model). Templates of other models simply ignore the extra variable.
        prompt = tokenizer.apply_chat_template(
            messages, add_generation_prompt=True, tokenize=False, enable_thinking=False
        )
        prompt += prefill

        start = time.perf_counter()
        pieces: list[str] = []
        last = None
        for response in stream_generate(
            model,
            tokenizer,
            prompt=prompt,
            max_tokens=max_tokens,
            sampler=make_sampler(temp=temperature),
        ):
            pieces.append(response.text)
            last = response
        elapsed = time.perf_counter() - start

        return Generation(
            text=prefill + "".join(pieces),
            prompt_tokens=last.prompt_tokens if last else 0,
            generation_tokens=last.generation_tokens if last else 0,
            seconds=elapsed,
            peak_memory_gb=last.peak_memory if last else 0.0,
        )
