"""Prompt templates. Kept separate so they are easy to iterate on and later reuse as
the instruction format when fine-tuning."""

from __future__ import annotations

OUTPUT_FORMAT = '{"summary": "...", "key_points": ["..."], "action_items": ["..."]}'

SUMMARIZE_SYSTEM = f"""You summarize voice note transcripts.

Rules:
- Use ONLY information stated in the transcript. Never invent names, dates, numbers, or tasks.
- The transcript is raw speech-to-text. Ignore filler words, repetition, and small transcription errors.
- "summary": 1-3 sentences saying what the note is about.
- "key_points": the main facts, decisions, or ideas as short statements (at most 8). Mention people by name.
- "action_items": EVERY task, reminder, or to-do the speaker mentions, whether for themselves or for someone else (e.g. "need to", "have to", "should", "remind", "don't forget", "is going to", "by Friday"). Write each as a short phrase and keep the name of whoever is responsible, plus any deadline. Use an empty list [] ONLY if the transcript contains no tasks at all.
- Do not describe what the note is about in "key_points" if it is already in "summary".
- Write in the same language as the transcript.
- The earlier example conversations only demonstrate the format. Their content (camping, octopuses) is NOT part of the real transcript; never reuse it.

Respond with ONLY a JSON object in exactly this format:
{OUTPUT_FORMAT}"""

# Worked examples shown to the model as prior chat turns. Small models follow a demonstrated
# format far more reliably than a described one. The topics are deliberately unrelated to
# the eval transcripts so the eval measures generalization, not memorization.
_EXAMPLE_WITH_ACTIONS = (
    "So, um, for the camping trip next weekend, I still have to book the campsite, and Jake "
    "said he'd bring the tent. I need to buy a new sleeping bag, mine is falling apart. We're "
    "leaving Friday at six in the morning. Oh, and don't forget to check the weather forecast "
    "on Thursday."
)
_EXAMPLE_WITH_ACTIONS_JSON = (
    '{"summary": "Planning for next weekend\'s camping trip: the campsite still needs booking '
    'and the group leaves Friday at 6 a.m.", '
    '"key_points": ["The group leaves Friday at 6 a.m.", '
    '"The speaker\'s old sleeping bag is falling apart"], '
    '"action_items": ["Book the campsite", "Buy a new sleeping bag", '
    '"Jake to bring the tent", "Check the weather forecast on Thursday"]}'
)
_EXAMPLE_NO_ACTIONS = (
    "I watched that documentary about octopuses last night. Apparently they have three hearts "
    "and blue blood, and each arm has its own mini-brain. It was fascinating how they solve "
    "puzzles. I'd honestly recommend it to anyone."
)
_EXAMPLE_NO_ACTIONS_JSON = (
    '{"summary": "The speaker enjoyed a documentary about octopuses and found their '
    'intelligence fascinating.", '
    '"key_points": ["Octopuses have three hearts and blue blood", '
    '"Each arm has its own mini-brain", "Octopuses can solve puzzles"], '
    '"action_items": []}'
)

# (user, assistant) pairs placed between the system prompt and the real request.
SUMMARIZE_EXAMPLES: list[tuple[str, str]] = [
    (f'Transcript:\n"""\n{_EXAMPLE_WITH_ACTIONS}\n"""\n\nReturn the JSON object.', _EXAMPLE_WITH_ACTIONS_JSON),
    (f'Transcript:\n"""\n{_EXAMPLE_NO_ACTIONS}\n"""\n\nReturn the JSON object.', _EXAMPLE_NO_ACTIONS_JSON),
]

MERGE_SYSTEM = f"""You combine partial summaries of consecutive parts of ONE voice note into a single summary.

Rules:
- Use ONLY information present in the partial summaries. Never add anything new.
- "summary": 2-4 sentences about the whole note.
- "key_points": the most important points overall, merging duplicates (at most 8).
- "action_items": every distinct action item from all parts, merging duplicates. If there are none, use an empty list [].
- Write in the same language as the partial summaries.

Respond with ONLY a JSON object in exactly this format:
{OUTPUT_FORMAT}"""

def retry_message(error: str) -> str:
    # Not str.format: OUTPUT_FORMAT contains literal braces.
    return (
        f"That reply was not valid: {error}\n"
        f"Respond again with ONLY the JSON object in exactly this format:\n{OUTPUT_FORMAT}"
    )


def summarize_user(transcript: str, part: int | None = None, parts: int | None = None) -> str:
    header = ""
    if part is not None and parts is not None and parts > 1:
        header = f"This is part {part} of {parts} of a longer transcript.\n\n"
    return f'{header}Transcript:\n"""\n{transcript}\n"""\n\nReturn the JSON object.'


def merge_user(partials: list[str]) -> str:
    body = "\n\n".join(f"--- Part {i} ---\n{p}" for i, p in enumerate(partials, 1))
    return f"Partial summaries:\n\n{body}\n\nReturn the JSON object."
