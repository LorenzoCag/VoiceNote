"""Run the summarization eval cases against the configured (or a given) model.

    python eval/run.py                              # model from config.toml
    python eval/run.py --model mlx-community/Qwen3-0.6B-4bit
    python eval/run.py --case meeting_rambling -v   # one case, print the full summary

The checks are deliberately coarse (key facts mentioned, action-item counts, chunking
happened). They catch regressions and let you compare models/prompts by pass rate,
speed, and memory; they are not a quality score.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from voicenote.config import load_config  # noqa: E402
from voicenote.summarization import SummarizationError, Summarizer, get_summarizer  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent


def check(case: dict, summary) -> list[str]:
    """Return a list of failure messages (empty = pass)."""
    failures = []
    haystack = " ".join([summary.summary, *summary.key_points, *summary.action_items]).lower()
    for alternatives in case.get("must_mention", []):
        if not any(a.lower() in haystack for a in alternatives):
            failures.append(f"missing any of {alternatives}")
    n = len(summary.action_items)
    if "action_items_min" in case and n < case["action_items_min"]:
        failures.append(f"{n} action items < min {case['action_items_min']}")
    if "action_items_max" in case and n > case["action_items_max"]:
        failures.append(f"{n} action items > max {case['action_items_max']}")
    if "chunks_min" in case and summary.chunks < case["chunks_min"]:
        failures.append(f"{summary.chunks} chunks < min {case['chunks_min']}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", help="override summarization.model from config.toml")
    parser.add_argument("--case", help="run only this case")
    parser.add_argument("-v", "--verbose", action="store_true", help="print each full summary")
    args = parser.parse_args()

    config = load_config().summarization
    if args.model:
        config = dataclasses.replace(config, model=args.model)
    base = get_summarizer(config)  # loads the model lazily, once; reused across cases

    cases = json.loads((EVAL_DIR / "cases.json").read_text())["cases"]
    if args.case:
        cases = [c for c in cases if c["name"] == args.case]
        if not cases:
            print(f"No case named '{args.case}'")
            return 2

    print(f"model: {config.model}\n")
    passed = 0
    total_time = 0.0
    for case in cases:
        text = "\n\n".join((EVAL_DIR / "transcripts" / f).read_text() for f in case["files"])
        case_config = dataclasses.replace(config, **case.get("overrides", {}))
        summarizer = Summarizer(base.llm, case_config)
        try:
            summary = summarizer.summarize(text)
        except SummarizationError as e:
            print(f"FAIL  {case['name']:<18} {e}")
            continue

        failures = check(case, summary)
        total_time += summary.elapsed_seconds
        status = "PASS" if not failures else "FAIL"
        passed += not failures
        print(
            f"{status}  {case['name']:<18} {summary.elapsed_seconds:5.1f}s  calls={summary.llm_calls} "
            f"chunks={summary.chunks}  points={len(summary.key_points)} actions={len(summary.action_items)}"
            f"  mem={summary.peak_memory_gb:.2f}GB"
        )
        for f in failures:
            print(f"        - {f}")
        for w in summary.warnings:
            print(f"        note: {w}")
        if args.verbose:
            print(json.dumps(summary.to_dict(), indent=2, ensure_ascii=False))

    print(f"\n{passed}/{len(cases)} passed, {total_time:.1f}s total inference")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
