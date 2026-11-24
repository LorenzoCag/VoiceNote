"""Offline tests for note storage and the transcribe/summarize service (fake models)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from voicenote.config import Config
from voicenote.service import VoiceNoteService
from voicenote.storage import NoteStore, make_title, new_note, to_markdown
from voicenote.summarization import SummarizationError, Summary
from voicenote.transcription import Segment, Transcript


class TmpDirCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)


class StoreTests(TmpDirCase):
    def make(self, note_id="20261124-170000", text="Call the dentist tomorrow."):
        return new_note(note_id, f"{note_id}.wav", {"text": text, "segments": []})

    def test_roundtrip(self):
        store = NoteStore(self.root)
        note = self.make()
        store.save(note)
        loaded = store.get(note.id)
        self.assertEqual(loaded.transcript_text, "Call the dentist tomorrow.")
        self.assertEqual(loaded.title, "Call the dentist tomorrow.")

    def test_list_is_newest_first_and_skips_corrupt_files(self):
        store = NoteStore(self.root)
        store.save(self.make("20261124-100000"))
        store.save(self.make("20261124-120000"))
        (store.notes_dir / "20261124-110000.json").write_text("{not json")
        (store.notes_dir / "20261124-130000.json").write_text('"a string, not an object"')
        self.assertEqual([n.id for n in store.list()], ["20261124-120000", "20261124-100000"])

    def test_list_empty_when_no_directory(self):
        self.assertEqual(NoteStore(self.root / "nope").list(), [])

    def test_unknown_fields_are_ignored(self):
        store = NoteStore(self.root)
        note = self.make()
        store.save(note)
        path = store.notes_dir / f"{note.id}.json"
        data = json.loads(path.read_text())
        data["field_from_the_future"] = 1
        path.write_text(json.dumps(data))
        self.assertEqual(store.get(note.id).id, note.id)

    def test_delete_removes_note_and_audio(self):
        store = NoteStore(self.root)
        note = self.make()
        store.recordings_dir.mkdir(parents=True)
        audio = store.recordings_dir / note.audio_file
        audio.write_bytes(b"RIFF")
        store.save(note)
        store.delete(note.id)
        self.assertIsNone(store.get(note.id))
        self.assertFalse(audio.exists())

    def test_rejects_path_traversal_ids(self):
        store = NoteStore(self.root)
        for bad in ["../secret", "a/b", "", "20261124-17000", "20261124-170000.json"]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                store.get(bad)

    def test_audio_file_name_cannot_escape_recordings_dir(self):
        store = NoteStore(self.root)
        victim = self.root / "victim.txt"
        victim.write_text("keep me")
        note = self.make()
        note.audio_file = "../victim.txt"
        store.save(note)
        store.delete(note.id)
        self.assertTrue(victim.exists())

    def test_save_leaves_no_temp_files(self):
        store = NoteStore(self.root)
        store.save(self.make())
        self.assertEqual([p.name for p in store.notes_dir.iterdir()], ["20261124-170000.json"])


class TitleAndExportTests(unittest.TestCase):
    def test_title_prefers_summary_first_sentence(self):
        note = new_note("20261124-170000", None, {"text": "uh so anyway"})
        note.summary = {"summary": "Plans for the trip. More detail here.", "key_points": [], "action_items": []}
        self.assertEqual(make_title(note), "Plans for the trip.")

    def test_title_truncates_and_handles_empty(self):
        note = new_note("20261124-170000", None, {"text": "word " * 50})
        self.assertLessEqual(len(make_title(note)), 60)
        self.assertEqual(make_title(new_note("20261124-170001", None, {"text": " "})), "Empty recording")

    def test_markdown_export(self):
        note = new_note("20261124-170000", None, {"text": "Email Sam."})
        note.summary = {"summary": "Email Sam.", "key_points": ["A point"], "action_items": ["Email Sam"]}
        md = to_markdown(note)
        for expected in ["## Summary", "- A point", "- [ ] Email Sam", "## Transcript"]:
            self.assertIn(expected, md)

    def test_markdown_export_without_summary(self):
        note = new_note("20261124-170000", None, {"text": "Hello."})
        note.summary_error = "Model failed"
        self.assertIn("Summary unavailable: Model failed", to_markdown(note))


# ---------------------------------------------------------------- service with fakes


class FakeTranscriber:
    model = "fake-whisper"

    def __init__(self, text="Call the dentist tomorrow at nine."):
        self.text = text

    def transcribe(self, path):
        return Transcript(
            text=self.text, language="en", model=self.model,
            segments=[Segment(0.0, 2.0, self.text)] if self.text else [],
        )


class FakeSummarizer:
    def __init__(self, error=None):
        self.error, self.received = error, None

    def summarize(self, transcript):
        self.received = transcript
        if self.error:
            raise self.error
        return Summary(summary="Dentist call.", key_points=["Call at 9"], action_items=["Call the dentist"])


def make_config(root: Path) -> Config:
    return Config(
        sample_rate=16000, input_device=None, data_dir=root,
        transcription_backend="mlx-whisper", transcription_model="x", transcription_language=None,
        offline=False,
    )


class ServiceTests(TmpDirCase):
    def service(self, transcriber=None, summarizer=None):
        return VoiceNoteService(
            make_config(self.root), transcriber=transcriber or FakeTranscriber(),
            summarizer=summarizer or FakeSummarizer(),
        )

    def test_full_flow_stores_note_with_summary(self):
        svc = self.service()
        path = svc.save_audio(b"fake audio", ".wav")
        note = svc.summarize(svc.transcribe(path))
        stored = svc.store.get(note.id)
        self.assertEqual(stored.summary["action_items"], ["Call the dentist"])
        self.assertEqual(stored.audio_file, path.name)
        self.assertTrue(svc.store.audio_path(stored).is_file())

    def test_transcribe_saves_note_before_summarizing(self):
        svc = self.service()
        note = svc.transcribe(svc.save_audio(b"x", ".wav"))
        self.assertIsNone(svc.store.get(note.id).summary)  # transcript survives a failed summary

    def test_summarizer_receives_segments_for_chunking(self):
        summarizer = FakeSummarizer()
        svc = self.service(summarizer=summarizer)
        svc.summarize(svc.transcribe(svc.save_audio(b"x", ".wav")))
        self.assertEqual(len(summarizer.received.segments), 1)

    def test_summarization_failure_keeps_transcript_and_records_error(self):
        svc = self.service(summarizer=FakeSummarizer(error=SummarizationError("bad json")))
        note = svc.summarize(svc.transcribe(svc.save_audio(b"x", ".wav")))
        stored = svc.store.get(note.id)
        self.assertIsNone(stored.summary)
        self.assertEqual(stored.summary_error, "bad json")
        self.assertEqual(stored.transcript_text, "Call the dentist tomorrow at nine.")

    def test_retry_clears_previous_error(self):
        svc = self.service(summarizer=FakeSummarizer(error=SummarizationError("bad json")))
        note = svc.summarize(svc.transcribe(svc.save_audio(b"x", ".wav")))
        svc.summarizer = FakeSummarizer()
        note = svc.summarize(note)
        self.assertIsNone(note.summary_error)
        self.assertIsNotNone(note.summary)

    def test_silent_recording_gets_friendly_message_and_no_model_call(self):
        summarizer = FakeSummarizer()
        svc = self.service(transcriber=FakeTranscriber(text=""), summarizer=summarizer)
        note = svc.summarize(svc.transcribe(svc.save_audio(b"x", ".wav")))
        self.assertIn("No speech", note.summary_error)
        self.assertIsNone(summarizer.received)

    def test_unsupported_audio_type_rejected(self):
        with self.assertRaises(ValueError):
            self.service().save_audio(b"x", ".exe")

    def test_same_second_recordings_do_not_overwrite(self):
        svc = self.service()
        paths = {svc.save_audio(b"x", ".wav") for _ in range(3)}
        self.assertEqual(len(paths), 3)
        for p in paths:  # every generated name must be a valid note id
            NoteStore(self.root).get(p.stem)


if __name__ == "__main__":
    unittest.main()
