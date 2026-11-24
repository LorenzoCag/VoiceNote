"""Local note storage: one JSON file per note, no database.

    data/
      recordings/<id>.wav     the audio
      notes/<id>.json         transcript + summary + metadata

The note id is the timestamp-based stem of the audio file, e.g. "20261124-170512".
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1
_ID_RE = re.compile(r"^\d{8}-\d{6}(-\d+)?$")  # also blocks path traversal like "../x"


@dataclass
class Note:
    id: str
    created_at: str  # ISO 8601, local time
    audio_file: str | None = None  # file name inside the recordings directory
    transcript: dict | None = None  # Transcript.to_dict()
    summary: dict | None = None  # Summary.to_dict()
    summary_error: str | None = None  # set when summarization failed or was impossible
    title: str = ""
    version: int = SCHEMA_VERSION

    @property
    def transcript_text(self) -> str:
        return (self.transcript or {}).get("text", "")

    @property
    def created(self) -> datetime:
        return datetime.fromisoformat(self.created_at)

    def to_dict(self) -> dict:
        return asdict(self)


def make_title(note: Note, max_len: int = 60) -> str:
    """Short human title: first sentence of the summary, else the start of the transcript."""
    source = (note.summary or {}).get("summary") or note.transcript_text
    source = " ".join(source.split())
    if not source:
        return "Empty recording"
    first = re.split(r"(?<=[.!?])\s", source, maxsplit=1)[0]
    if len(first) > max_len:
        first = first[: max_len - 1].rstrip() + "…"
    return first


def new_note(note_id: str, audio_file: str | None, transcript: dict | None = None) -> Note:
    note = Note(
        id=note_id,
        created_at=datetime.now().isoformat(timespec="seconds"),
        audio_file=audio_file,
        transcript=transcript,
    )
    note.title = make_title(note)
    return note


def to_markdown(note: Note) -> str:
    """A readable export of a note."""
    lines = [f"# {note.title}", "", f"*{note.created:%A, %B %d, %Y at %H:%M}*", ""]
    if note.summary:
        lines += ["## Summary", "", note.summary["summary"], ""]
        if note.summary["key_points"]:
            lines += ["## Key points", ""] + [f"- {p}" for p in note.summary["key_points"]] + [""]
        if note.summary["action_items"]:
            lines += ["## Action items", ""] + [f"- [ ] {a}" for a in note.summary["action_items"]] + [""]
    elif note.summary_error:
        lines += [f"> Summary unavailable: {note.summary_error}", ""]
    lines += ["## Transcript", "", note.transcript_text or "(no speech detected)", ""]
    return "\n".join(lines)


class NoteStore:
    def __init__(self, data_dir: Path):
        self.notes_dir = Path(data_dir) / "notes"
        self.recordings_dir = Path(data_dir) / "recordings"

    # -- write ----------------------------------------------------------------

    def save(self, note: Note) -> None:
        """Atomically write the note (temp file + rename) so a crash never leaves a half file."""
        self._check_id(note.id)
        note.title = make_title(note)
        self.notes_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.notes_dir, prefix=".tmp-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(note.to_dict(), f, indent=2, ensure_ascii=False)
            os.replace(tmp, self._path(note.id))
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def delete(self, note_id: str) -> None:
        """Delete a note and its audio file."""
        note = self.get(note_id)
        self._path(note_id).unlink(missing_ok=True)
        if note and note.audio_file:
            audio = self.recordings_dir / Path(note.audio_file).name  # .name: never leave the folder
            audio.unlink(missing_ok=True)

    # -- read -----------------------------------------------------------------

    def get(self, note_id: str) -> Note | None:
        self._check_id(note_id)
        path = self._path(note_id)
        if not path.is_file():
            return None
        return self._read(path)

    def list(self) -> list[Note]:
        """All readable notes, newest first. Unreadable files are skipped (and logged)."""
        if not self.notes_dir.is_dir():
            return []
        notes = [n for p in self.notes_dir.glob("*.json") if (n := self._read(p))]
        return sorted(notes, key=lambda n: n.id, reverse=True)

    def audio_path(self, note: Note) -> Path | None:
        if not note.audio_file:
            return None
        path = self.recordings_dir / Path(note.audio_file).name
        return path if path.is_file() else None

    # -- internals ------------------------------------------------------------

    def _path(self, note_id: str) -> Path:
        return self.notes_dir / f"{note_id}.json"

    @staticmethod
    def _check_id(note_id: str) -> None:
        if not _ID_RE.match(note_id):
            raise ValueError(f"Invalid note id: {note_id!r}")

    @staticmethod
    def _read(path: Path) -> Note | None:
        try:
            if not _ID_RE.match(path.stem):
                raise ValueError("file name is not a valid note id")
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("top-level JSON value is not an object")
            known = {k: v for k, v in raw.items() if k in Note.__dataclass_fields__}
            known["id"] = path.stem  # the file name is the source of truth
            return Note(**known)
        except (OSError, ValueError, TypeError) as e:
            log.warning("Skipping unreadable note %s: %s", path.name, e)
            return None
