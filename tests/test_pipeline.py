"""Offline unit tests for the summarization pipeline using a scripted fake LLM.

    python -m unittest discover tests
"""

from __future__ import annotations

import json
import unittest

from voicenote.config import SummarizationConfig
from voicenote.summarization import SummarizationError
from voicenote.summarization.base import Generation
from voicenote.summarization.pipeline import Summarizer, _parse_summary_json


class FakeLLM:
    """Returns scripted replies in order; tokens are counted as whitespace-separated words."""

    model = "fake"

    def __init__(self, replies: list[str]):
        self.replies = list(replies)
        self.calls: list[list[dict]] = []

    def count_tokens(self, text: str) -> int:
        return len(text.split())

    def generate(self, messages, max_tokens, temperature, prefill=""):
        self.calls.append(messages)
        reply = self.replies.pop(0)
        return Generation(text=prefill + reply, prompt_tokens=10, generation_tokens=5, seconds=0.0)


def ok(summary="A summary.", key_points=(), action_items=()) -> str:
    """A scripted reply body (without the prefilled opening brace)."""
    return json.dumps(
        {"summary": summary, "key_points": list(key_points), "action_items": list(action_items)}
    )[1:]


CFG = SummarizationConfig(max_input_tokens=50, chunk_tokens=20)


class ParseTests(unittest.TestCase):
    def test_valid(self):
        r = _parse_summary_json('{"summary": "s", "key_points": ["a"], "action_items": []}')
        self.assertEqual(r["key_points"], ["a"])

    def test_ignores_trailing_text(self):
        r = _parse_summary_json('{"summary": "s", "key_points": [], "action_items": []} extra')
        self.assertEqual(r["summary"], "s")

    def test_coerces_dict_items_and_dedupes(self):
        r = _parse_summary_json(
            '{"summary": "s", "key_points": ["a", "A"], "action_items": [{"task": "call", "who": "Tom"}]}'
        )
        self.assertEqual(r["key_points"], ["a"])
        self.assertEqual(r["action_items"], ["call - Tom"])

    def test_rejects_bad_output(self):
        for bad in [
            "no json here",
            '{"summary": "s", "key_points": []}',  # missing key
            '{"summary": "", "key_points": [], "action_items": []}',
            '{"summary": "s", "key_points": "x", "action_items": []}',
            '{"summary": "s", "key_points": [',  # truncated
            "[1, 2]",
        ]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                _parse_summary_json(bad)


class SummarizerTests(unittest.TestCase):
    def test_single_pass(self):
        llm = FakeLLM([ok("Dentist call.", ["Call the dentist"], ["call the dentist"])])
        s = Summarizer(llm, CFG).summarize("I need to call the dentist tomorrow.")
        self.assertEqual(s.chunks, 1)
        self.assertEqual(s.llm_calls, 1)
        self.assertEqual(s.action_items, ["call the dentist"])
        self.assertEqual(s.warnings, [])

    def test_retry_after_invalid_output(self):
        llm = FakeLLM(["not json at all", ok("Fine now.")])
        s = Summarizer(llm, CFG).summarize("Some transcript text here.")
        self.assertEqual(s.summary, "Fine now.")
        self.assertEqual(s.llm_calls, 2)
        self.assertEqual(len(s.warnings), 1)
        # the retry must show the model its bad output and the error
        retry_messages = llm.calls[1]
        self.assertEqual(retry_messages[-2]["role"], "assistant")
        self.assertIn("not valid", retry_messages[-1]["content"])

    def test_raises_after_all_attempts_fail(self):
        llm = FakeLLM(["nope", "still nope", "nope again"])
        with self.assertRaises(SummarizationError):
            Summarizer(llm, CFG).summarize("Some transcript text here.")
        self.assertEqual(len(llm.calls), 3)

    def test_retries_raise_temperature(self):
        temps = []

        class Recording(FakeLLM):
            def generate(self, messages, max_tokens, temperature, prefill=""):
                temps.append(temperature)
                return super().generate(messages, max_tokens, temperature, prefill)

        llm = Recording(["bad", "bad", ok()])
        Summarizer(llm, CFG).summarize("Some transcript text here.")
        self.assertEqual(len(temps), 3)
        self.assertLess(temps[0], temps[1])
        self.assertLess(temps[1], temps[2])

    def test_drops_ungrounded_items(self):
        llm = FakeLLM([ok("S.", ["Meeting with the CEO of Acme"], ["call the dentist", "book flights to Paris"])])
        s = Summarizer(llm, CFG).summarize("I need to call the dentist tomorrow morning.")
        self.assertEqual(s.action_items, ["call the dentist"])
        self.assertEqual(s.key_points, [])
        self.assertEqual(len(s.warnings), 2)

    def test_spelled_out_numbers_are_not_flagged(self):
        llm = FakeLLM([ok("S.", [], ["Ad budget of $12,000 approved"])])
        s = Summarizer(llm, CFG).summarize("The ad budget of twelve thousand dollars got approved.")
        self.assertEqual(s.action_items, ["Ad budget of $12,000 approved"])

    def test_empty_transcript(self):
        with self.assertRaises(ValueError):
            Summarizer(FakeLLM([]), CFG).summarize("   ")

    def test_long_transcript_is_chunked_then_merged(self):
        sentences = [f"Sentence number {i} talks about topic{i} in some detail." for i in range(30)]
        text = " ".join(sentences)  # ~240 words, well over max_input_tokens=50
        llm = FakeLLM([])
        # Reply per call: chunk summaries first, then a merge; sized generously.
        llm.replies = [ok(f"Part {i}.", [f"topic{i}"], []) for i in range(100)]
        s = Summarizer(llm, CFG).summarize(text)
        self.assertGreater(s.chunks, 2)
        self.assertEqual(s.llm_calls, len(llm.calls))
        # the final call is a merge call, not a transcript call
        self.assertIn("Partial summaries", llm.calls[-1][-1]["content"])
        # every chunk call stays within the configured chunk size (+ prompt boilerplate)
        for call in llm.calls[: s.chunks]:
            transcript_part = call[-1]["content"].split('"""')[1]
            self.assertLessEqual(len(transcript_part.split()), CFG.chunk_tokens + 15)

    def test_oversized_single_unit_is_split(self):
        text = " ".join(f"word{i}" for i in range(200))  # no punctuation => one huge "sentence"
        llm = FakeLLM([ok() for _ in range(50)])
        s = Summarizer(llm, CFG).summarize(text)
        self.assertGreater(s.chunks, 5)


if __name__ == "__main__":
    unittest.main()
