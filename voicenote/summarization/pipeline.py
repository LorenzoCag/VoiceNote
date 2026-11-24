"""Model-independent summarization logic: chunking, JSON validation, retry, grounding."""

from __future__ import annotations

import json
import re
import time

from voicenote.config import SummarizationConfig
from voicenote.summarization import prompts
from voicenote.summarization.base import LLM, Generation, SummarizationError, Summary
from voicenote.transcription import Transcript

# First try + retries with the validation error fed back to the model. Each retry raises the
# temperature a little so a small model doesn't repeat the exact same malformed output.
MAX_ATTEMPTS = 3
RETRY_TEMPERATURE_STEP = 0.2
MAX_KEY_POINTS = 8
GROUNDING_THRESHOLD = 0.6  # min fraction of an item's content words found in the transcript

_STOPWORDS = {
    "that", "this", "with", "from", "have", "will", "they", "them", "then", "than", "there",
    "their", "about", "would", "could", "should", "which", "what", "when", "where", "been",
    "were", "also", "into", "some", "more", "very", "just", "your", "need", "needs", "note",
    "speaker", "says", "said", "mentions", "mentioned",
}


# --------------------------------------------------------------------------- parsing


def _parse_summary_json(text: str) -> dict:
    """Extract and validate the JSON object; raise ValueError describing any problem."""
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object found")
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid JSON ({e.msg} at position {e.pos})") from None
    if not isinstance(obj, dict):
        raise ValueError("top-level JSON value must be an object")

    for key in ("summary", "key_points", "action_items"):
        if key not in obj:
            raise ValueError(f'missing key "{key}"')
    if not isinstance(obj["summary"], str) or not obj["summary"].strip():
        raise ValueError('"summary" must be a non-empty string')
    for key in ("key_points", "action_items"):
        if not isinstance(obj[key], list):
            raise ValueError(f'"{key}" must be a list of strings')

    return {
        "summary": obj["summary"].strip(),
        "key_points": _clean_items(obj["key_points"]),
        "action_items": _clean_items(obj["action_items"]),
    }


def _clean_items(items: list) -> list[str]:
    """Coerce list entries to unique, non-empty strings (small models sometimes emit dicts)."""
    out: list[str] = []
    for item in items:
        if isinstance(item, dict):
            item = " - ".join(str(v) for v in item.values() if v)
        text = str(item).strip()
        if text and text.lower() not in {o.lower() for o in out}:
            out.append(text)
    return out


# ------------------------------------------------------------------------ grounding


def _stem(word: str) -> str:
    return word[:5]  # crude prefix match: "calling" ~ "call", "reports" ~ "report"


def _content_words(text: str) -> list[str]:
    # Digit-only tokens are ignored: "$12,000" in a summary vs "twelve thousand" in the
    # transcript would otherwise look like invented numbers. (Tradeoff: a wrong number in
    # an otherwise grounded item is not caught here.)
    words = re.findall(r"[a-z0-9']+", text.lower())
    return [w for w in words if len(w) > 3 and not w.isdigit() and w not in _STOPWORDS]


def _is_grounded(item: str, transcript_stems: set[str]) -> bool:
    words = _content_words(item)
    if not words:
        return True
    found = sum(1 for w in words if _stem(w) in transcript_stems)
    return found / len(words) >= GROUNDING_THRESHOLD


# ------------------------------------------------------------------------- chunking


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p for p in parts if p]


class Summarizer:
    def __init__(self, llm: LLM, config: SummarizationConfig):
        self.llm = llm
        self.config = config

    # -- public ---------------------------------------------------------------

    def summarize(self, transcript: Transcript | str) -> Summary:
        text = transcript if isinstance(transcript, str) else transcript.text
        text = text.strip()
        if not text:
            raise ValueError("Transcript is empty; nothing to summarize.")

        units = self._units(transcript, text)
        stats = _Stats()
        started = time.perf_counter()

        if self.llm.count_tokens(text) <= self.config.max_input_tokens:
            result = self._summarize_text(text, stats)
            chunks = 1
        else:
            chunks_text = self._chunk(units)
            partials = [
                self._summarize_text(chunk, stats, part=i, parts=len(chunks_text))
                for i, chunk in enumerate(chunks_text, 1)
            ]
            result = self._merge(partials, stats)
            chunks = len(chunks_text)

        warnings = stats.warnings + self._ground(result, text)
        return Summary(
            summary=result["summary"],
            key_points=result["key_points"][:MAX_KEY_POINTS],
            action_items=result["action_items"],
            model=self.llm.model,
            elapsed_seconds=time.perf_counter() - started,
            llm_calls=stats.calls,
            chunks=chunks,
            prompt_tokens=stats.prompt_tokens,
            generation_tokens=stats.generation_tokens,
            peak_memory_gb=stats.peak_memory_gb,
            warnings=warnings,
        )

    # -- steps ----------------------------------------------------------------

    def _summarize_text(self, text: str, stats: "_Stats", part: int | None = None, parts: int | None = None) -> dict:
        messages = [{"role": "system", "content": prompts.SUMMARIZE_SYSTEM}]
        for example_user, example_reply in prompts.SUMMARIZE_EXAMPLES:
            messages.append({"role": "user", "content": example_user})
            messages.append({"role": "assistant", "content": example_reply})
        messages.append({"role": "user", "content": prompts.summarize_user(text, part, parts)})
        return self._generate_json(messages, stats)

    def _merge(self, partials: list[dict], stats: "_Stats") -> dict:
        """Merge partial results; recurses in groups if the partials are themselves too long."""
        while True:
            rendered = [_render_partial(p) for p in partials]
            total = sum(self.llm.count_tokens(r) for r in rendered)
            if total <= self.config.max_input_tokens or len(partials) <= 2:
                break
            group = max(2, len(partials) // 2)
            partials = [
                self._merge_group(partials[i : i + group], stats) for i in range(0, len(partials), group)
            ]
        return self._merge_group(partials, stats)

    def _merge_group(self, partials: list[dict], stats: "_Stats") -> dict:
        if len(partials) == 1:
            return partials[0]
        messages = [
            {"role": "system", "content": prompts.MERGE_SYSTEM},
            {"role": "user", "content": prompts.merge_user([_render_partial(p) for p in partials])},
        ]
        return self._generate_json(messages, stats)

    def _generate_json(self, messages: list[dict], stats: "_Stats") -> dict:
        """Generate, validate, and retry once with the error fed back. Prefills '{' so the
        model starts directly with a JSON object."""
        messages = list(messages)
        last_error = "unknown error"
        for attempt in range(1, MAX_ATTEMPTS + 1):
            gen = self.llm.generate(
                messages,
                max_tokens=self.config.max_new_tokens,
                temperature=self.config.temperature + RETRY_TEMPERATURE_STEP * (attempt - 1),
                prefill="{",
            )
            stats.add(gen)
            try:
                return _parse_summary_json(gen.text)
            except ValueError as e:
                last_error = str(e)
                stats.warnings.append(f"attempt {attempt} produced invalid output: {last_error}")
                messages = messages + [
                    {"role": "assistant", "content": gen.text},
                    {"role": "user", "content": prompts.retry_message(last_error)},
                ]
        raise SummarizationError(
            f"Model '{self.llm.model}' did not return valid JSON after {MAX_ATTEMPTS} attempts "
            f"(last error: {last_error})."
        )

    # -- helpers --------------------------------------------------------------

    @staticmethod
    def _units(transcript: Transcript | str, text: str) -> list[str]:
        """Smallest pieces we may split on: Whisper segments if available, else sentences."""
        segments = getattr(transcript, "segments", None)
        if segments:
            return [s.text for s in segments if s.text.strip()]
        return _split_sentences(text)

    def _chunk(self, units: list[str]) -> list[str]:
        """Greedily pack units into chunks of about `chunk_tokens` tokens."""
        limit = self.config.chunk_tokens
        chunks: list[str] = []
        current: list[str] = []
        current_tokens = 0
        for unit in self._split_oversized(units, limit):
            n = self.llm.count_tokens(unit)
            if current and current_tokens + n > limit:
                chunks.append(" ".join(current))
                current, current_tokens = [], 0
            current.append(unit)
            current_tokens += n
        if current:
            chunks.append(" ".join(current))
        return chunks

    def _split_oversized(self, units: list[str], limit: int) -> list[str]:
        """Break any single unit that alone exceeds `limit` tokens (e.g. no punctuation)."""
        out: list[str] = []
        for unit in units:
            if self.llm.count_tokens(unit) <= limit:
                out.append(unit)
                continue
            words = unit.split()
            step = max(1, len(words) * limit // max(1, self.llm.count_tokens(unit)))
            out.extend(" ".join(words[i : i + step]) for i in range(0, len(words), step))
        return out

    @staticmethod
    def _ground(result: dict, transcript_text: str) -> list[str]:
        """Drop key points / action items that share too few words with the transcript."""
        stems = {_stem(w) for w in re.findall(r"[a-z0-9']+", transcript_text.lower())}
        warnings = []
        for field in ("key_points", "action_items"):
            kept = []
            for item in result[field]:
                if _is_grounded(item, stems):
                    kept.append(item)
                else:
                    warnings.append(f"dropped ungrounded {field[:-1].replace('_', ' ')}: {item!r}")
            result[field] = kept
        return warnings


def _render_partial(p: dict) -> str:
    lines = [f"Summary: {p['summary']}"]
    if p["key_points"]:
        lines.append("Key points:\n" + "\n".join(f"- {x}" for x in p["key_points"]))
    if p["action_items"]:
        lines.append("Action items:\n" + "\n".join(f"- {x}" for x in p["action_items"]))
    return "\n".join(lines)


class _Stats:
    def __init__(self):
        self.calls = 0
        self.prompt_tokens = 0
        self.generation_tokens = 0
        self.peak_memory_gb = 0.0
        self.warnings: list[str] = []

    def add(self, gen: Generation) -> None:
        self.calls += 1
        self.prompt_tokens += gen.prompt_tokens
        self.generation_tokens += gen.generation_tokens
        self.peak_memory_gb = max(self.peak_memory_gb, gen.peak_memory_gb)
