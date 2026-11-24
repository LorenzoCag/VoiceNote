"""Tests that run the real app.py (Streamlit AppTest) against fake transcription/summarization.

    python -m unittest discover tests
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import streamlit as st
from streamlit.testing.v1 import AppTest
from test_storage_service import FakeSummarizer, FakeTranscriber, make_config

from voicenote.service import VoiceNoteService
from voicenote.summarization import SummarizationError

APP = str(Path(__file__).resolve().parent.parent / "app.py")
PROCESS_LABEL = "Transcribe and summarize"


class AppCase(unittest.TestCase):
    summarizer: FakeSummarizer

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.config = make_config(Path(self._tmp.name))
        self.summarizer = FakeSummarizer()
        self.transcriber = FakeTranscriber()
        for p in (
            mock.patch("voicenote.config.load_config", return_value=self.config),
            mock.patch("voicenote.service.get_transcriber", return_value=self.transcriber),
            mock.patch("voicenote.service.get_summarizer", side_effect=lambda cfg: self.summarizer),
        ):
            p.start()
            self.addCleanup(p.stop)
        st.cache_resource.clear()
        self.addCleanup(st.cache_resource.clear)
        # A second service on the same data dir, for seeding notes the way the app would.
        self.seed_service = VoiceNoteService(self.config, transcriber=self.transcriber, summarizer=self.summarizer)

    # -- helpers --------------------------------------------------------------

    def app(self) -> AppTest:
        at = AppTest.from_file(APP, default_timeout=30)
        at.run()
        self.assertFalse(at.exception, [e.value for e in at.exception])
        return at

    def seed_note(self):
        note = self.seed_service.transcribe(self.seed_service.save_audio(b"RIFFfake", ".wav"))
        return self.seed_service.summarize(note)

    @staticmethod
    def text(at: AppTest) -> str:
        return "\n".join(m.value for m in at.markdown)

    @staticmethod
    def process_button(at: AppTest):
        return next(b for b in at.button if b.label == PROCESS_LABEL)


class NewNoteTests(AppCase):
    def test_empty_state(self):
        at = self.app()
        self.assertEqual(at.title[0].value, "New note")
        self.assertTrue(self.process_button(at).disabled)
        self.assertIn("No notes yet.", [c.value for c in at.sidebar.caption])

    def test_record_flow_creates_and_shows_note(self):
        at = self.app()
        at.audio_input[0].upload("rec.wav", b"RIFFfake")
        at.run()
        self.assertFalse(self.process_button(at).disabled)
        self.process_button(at).click().run()

        self.assertFalse(at.exception, [e.value for e in at.exception])
        self.assertIsNotNone(at.session_state.selected)
        text = self.text(at)
        self.assertIn("Dentist call.", text)
        self.assertIn("Call the dentist", text)
        self.assertEqual(len(self.seed_service.store.list()), 1)
        self.assertTrue(any((b.key or "").startswith("note_") for b in at.sidebar.button))  # in history

    def test_upload_flow(self):
        at = self.app()
        at.button_group[0].set_value("Upload").run()
        at.file_uploader[0].upload("memo.mp3", b"fake mp3").run()
        self.process_button(at).click().run()
        stored = self.seed_service.store.list()
        self.assertEqual(len(stored), 1)
        self.assertTrue(stored[0].audio_file.endswith(".mp3"))

    def test_model_not_downloaded_shows_friendly_error(self):
        at = self.app()
        at.audio_input[0].upload("rec.wav", b"RIFFfake").run()
        from dataclasses import replace

        offline = replace(self.config, offline=True, transcription_model="nobody/missing-model")
        with mock.patch("voicenote.config.load_config", return_value=offline):
            st.cache_resource.clear()
            at = self.app()
            at.audio_input[0].upload("rec.wav", b"RIFFfake").run()
            self.process_button(at).click().run()
        self.assertTrue(any("python -m voicenote setup" in e.value for e in at.error))
        self.assertEqual(self.seed_service.store.list(), [])

    def test_transcription_crash_shows_error_and_leaves_no_orphan_audio(self):
        self.transcriber.transcribe = mock.Mock(side_effect=RuntimeError("ffmpeg not found"))
        at = self.app()
        at.audio_input[0].upload("rec.wav", b"RIFFfake").run()
        self.process_button(at).click().run()
        self.assertTrue(any("ffmpeg not found" in e.value for e in at.error))
        recordings = self.seed_service.store.recordings_dir
        self.assertEqual(list(recordings.glob("*")) if recordings.exists() else [], [])
        self.assertEqual(self.seed_service.store.list(), [])


class NoteViewTests(AppCase):
    def test_history_selection_shows_that_note(self):
        note = self.seed_note()
        at = self.app()
        at.button(key=f"note_{note.id}").click().run()
        self.assertEqual(at.session_state.selected, note.id)
        self.assertIn("Dentist call.", self.text(at))

    def test_new_note_button_returns_to_recorder(self):
        note = self.seed_note()
        at = self.app()
        at.button(key=f"note_{note.id}").click().run()
        next(b for b in at.sidebar.button if b.label == "New note").click().run()
        self.assertIsNone(at.session_state.selected)
        self.assertEqual(at.title[0].value, "New note")

    def test_delete_removes_note_and_audio(self):
        note = self.seed_note()
        audio_path = self.seed_service.store.audio_path(note)
        self.assertTrue(audio_path.is_file())
        at = self.app()
        at.button(key=f"note_{note.id}").click().run()
        at.button(key=f"delete_{note.id}").click().run()
        self.assertIsNone(self.seed_service.store.get(note.id))
        self.assertFalse(audio_path.exists())
        self.assertIsNone(at.session_state.selected)

    def test_failed_summary_shows_warning_and_retry_recovers(self):
        self.summarizer.error = SummarizationError("model returned bad JSON")
        note = self.seed_note()
        at = self.app()
        at.button(key=f"note_{note.id}").click().run()
        self.assertTrue(any("model returned bad JSON" in w.value for w in at.warning))
        self.assertIn("Show transcript", " ".join(e.label for e in at.expander))

        self.summarizer.error = None  # the model behaves on the second try
        next(b for b in at.button if b.label == "Try again").click().run()
        self.assertIn("Dentist call.", self.text(at))
        self.assertIsNone(self.seed_service.store.get(note.id).summary_error)

    def test_model_output_is_html_escaped(self):
        note = self.seed_note()
        note.summary["summary"] = "<script>alert(1)</script> Plans."
        note.summary["key_points"] = ['<img src=x onerror="bad()">']
        self.seed_service.store.save(note)
        at = self.app()
        at.button(key=f"note_{note.id}").click().run()
        text = self.text(at)
        self.assertNotIn("<script>", text)
        self.assertNotIn("<img", text)
        self.assertIn("&lt;script&gt;", text)

    def test_notes_listed_newest_first_and_corrupt_file_ignored(self):
        first = self.seed_note()
        (self.seed_service.store.notes_dir / "20990101-000000.json").write_text("{broken")
        at = self.app()
        keys = [b.key for b in at.sidebar.button if b.key and b.key.startswith("note_")]
        self.assertEqual(keys, [f"note_{first.id}"])


if __name__ == "__main__":
    unittest.main()
