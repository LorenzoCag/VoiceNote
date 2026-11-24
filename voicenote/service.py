"""The workflow the UI drives: save audio -> transcribe -> summarize -> store.

Kept free of any UI code so it is easy to test and to reuse from other front ends.

Threading note: MLX streams are per-thread, so a model must be loaded and used on the same
thread. Front ends that serve requests from several threads (like Streamlit) should run
`transcribe` and `summarize` on one dedicated worker thread.
"""

from __future__ import annotations

from pathlib import Path

from voicenote import audio, models
from voicenote.config import Config
from voicenote.storage import Note, NoteStore, new_note
from voicenote.summarization import SummarizationError, Summarizer, get_summarizer
from voicenote.transcription import Segment, Transcriber, Transcript, get_transcriber


def _transcript_from_dict(data: dict) -> Transcript:
    return Transcript(
        text=data.get("text", ""),
        language=data.get("language"),
        segments=[Segment(**s) for s in data.get("segments", [])],
        model=data.get("model", ""),
        elapsed_seconds=data.get("elapsed_seconds", 0.0),
    )


class VoiceNoteService:
    def __init__(
        self,
        config: Config,
        store: NoteStore | None = None,
        transcriber: Transcriber | None = None,
        summarizer: Summarizer | None = None,
    ):
        self.config = config
        self.store = store or NoteStore(config.data_dir)
        # Construction is cheap: the models themselves load on first use.
        self.transcriber = transcriber or get_transcriber(config)
        self.summarizer = summarizer or get_summarizer(config.summarization)

    def check_models(self) -> None:
        """Raise ModelNotAvailable up front (offline mode, model not downloaded)."""
        models.require(self.config, "transcription")
        models.require(self.config, "summarization")

    def save_audio(self, data: bytes, suffix: str = ".wav") -> Path:
        suffix = suffix.lower()
        if suffix not in audio.AUDIO_EXTENSIONS:
            raise ValueError(f"Unsupported audio type '{suffix}'.")
        path = audio.new_recording_path(self.store.recordings_dir, suffix)
        path.write_bytes(data)
        return path

    def transcribe(self, audio_path: Path) -> Note:
        """Transcribe and store a new note (without a summary yet)."""
        transcript = self.transcriber.transcribe(audio_path)
        note = new_note(audio_path.stem, audio_path.name, transcript.to_dict())
        self.store.save(note)
        return note

    def summarize(self, note: Note) -> Note:
        """Add a summary to the note, or record why it isn't available. Never raises for
        model/output problems; the transcript is always kept."""
        note.summary, note.summary_error = None, None
        if not note.transcript_text.strip():
            note.summary_error = "No speech was detected in this recording."
        else:
            try:
                transcript = _transcript_from_dict(note.transcript)  # keeps segments for chunking
                note.summary = self.summarizer.summarize(transcript).to_dict()
            except SummarizationError as e:
                note.summary_error = str(e)
        self.store.save(note)
        return note
