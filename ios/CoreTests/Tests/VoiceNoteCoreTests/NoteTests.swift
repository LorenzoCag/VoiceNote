import Foundation
import Testing

@testable import VoiceNoteCore

@Suite struct NoteTests {
    /// A note exactly as the Mac app (voicenote/storage.py) writes it.
    static let macJSON = """
    {
      "audio_file": "20261124-171258.wav",
      "created_at": "2026-11-24T17:12:58",
      "id": "20261124-171258",
      "summary": {
        "action_items": ["need to update pricing page before the launch"],
        "chunks": 1,
        "elapsed_seconds": 4.3,
        "generation_tokens": 112,
        "key_points": ["Product launch delayed from March 3 to March 17"],
        "llm_calls": 1,
        "model": "mlx-community/Qwen3-0.6B-8bit",
        "peak_memory_gb": 1.46,
        "prompt_tokens": 284,
        "summary": "Product launch is delayed due to a checkout bug. More detail follows.",
        "warnings": ["dropped ungrounded key point: 'x'"]
      },
      "summary_error": null,
      "title": "Product launch is delayed due to a checkout bug.",
      "transcript": {
        "elapsed_seconds": 0.8,
        "language": "en",
        "model": "mlx-community/whisper-base-mlx",
        "segments": [{"start": 0.0, "end": 2.5, "text": "Okay, quick note."}],
        "text": "Okay, quick note about the product launch."
      },
      "version": 1
    }
    """

    @Test func decodesNotesWrittenByTheMacApp() throws {
        let note = try JSONDecoder().decode(Note.self, from: Data(Self.macJSON.utf8))
        #expect(note.id == "20261124-171258")
        #expect(note.audioFile == "20261124-171258.wav")
        #expect(note.transcript?.segments.count == 1)
        #expect(note.summary?.actionItems == ["need to update pricing page before the launch"])
        #expect(note.summary?.peakMemoryGb == 1.46)
        #expect(note.summaryError == nil)
    }

    @Test func roundTripPreservesEverything() throws {
        let original = try JSONDecoder().decode(Note.self, from: Data(Self.macJSON.utf8))
        let again = try JSONDecoder().decode(Note.self, from: JSONEncoder().encode(original))
        #expect(again == original)
    }

    @Test func encodedKeysAreSnakeCaseSoTheMacAppCanReadThem() throws {
        let note = try JSONDecoder().decode(Note.self, from: Data(Self.macJSON.utf8))
        let json = String(decoding: try JSONEncoder().encode(note), as: UTF8.self)
        for key in ["created_at", "audio_file", "key_points", "action_items", "elapsed_seconds", "llm_calls", "peak_memory_gb"] {
            #expect(json.contains("\"\(key)\""), "missing key \(key)")
        }
        #expect(!json.contains("createdAt"))
    }

    @Test func decodingIsLenientAboutMissingOptionalData() throws {
        let minimal = #"{"id": "20261124-100000", "created_at": "2026-11-24T10:00:00"}"#
        let note = try JSONDecoder().decode(Note.self, from: Data(minimal.utf8))
        #expect(note.summary == nil)
        #expect(note.transcriptText == "")
        #expect(note.version == Note.schemaVersion)
    }

    @Test func rejectsNotesWithoutAnIdentity() {
        #expect(throws: (any Error).self) { try JSONDecoder().decode(Note.self, from: Data(#"{"created_at": "x"}"#.utf8)) }
        #expect(throws: (any Error).self) { try JSONDecoder().decode(Note.self, from: Data(#""just a string""#.utf8)) }
    }

    @Test func createdDateParsesAndRoundTrips() {
        let date = Date(timeIntervalSince1970: 1_800_000_000)
        let string = NoteDates.string(from: date)
        #expect(NoteDates.date(from: string)?.timeIntervalSince1970 == date.timeIntervalSince1970)
        #expect(NoteDates.idString(from: date).count == 15)
    }

    // MARK: titles

    @Test func titlePrefersSummaryFirstSentence() {
        #expect(Note.makeTitle(summary: "Plans for the trip. More detail here.", transcript: "uh so anyway") == "Plans for the trip.")
    }

    @Test func titleFallsBackToTranscriptAndHandlesEmpty() {
        #expect(Note.makeTitle(summary: nil, transcript: "Call the dentist tomorrow.") == "Call the dentist tomorrow.")
        #expect(Note.makeTitle(summary: "", transcript: "  \n ") == "Empty recording")
    }

    @Test func longTitlesAreTruncated() {
        let title = Note.makeTitle(summary: nil, transcript: String(repeating: "word ", count: 50))
        #expect(title.count <= 60)
        #expect(title.hasSuffix("…"))
    }

    // MARK: sentences

    @Test func sentenceSplitting() {
        #expect(Sentences.split("One. Two! Three? Four") == ["One.", "Two!", "Three?", "Four"])
        #expect(Sentences.split("It cost 3.5 dollars. Fine.") == ["It cost 3.5 dollars.", "Fine."])
        #expect(Sentences.split("   ").isEmpty)
    }

    // MARK: markdown

    @Test func markdownExport() throws {
        let note = try JSONDecoder().decode(Note.self, from: Data(Self.macJSON.utf8))
        let md = NoteMarkdown.render(note)
        for expected in ["# Product launch is delayed", "## Summary", "- Product launch delayed", "- [ ] need to update", "## Transcript"] {
            #expect(md.contains(expected), "missing: \(expected)")
        }
    }

    @Test func markdownExportWithoutSummaryShowsTheReason() {
        var note = Note.create(id: "20261124-100000", audioFile: nil, transcript: TranscriptData(text: "Hello."))
        note.summaryError = "Model failed"
        #expect(NoteMarkdown.render(note).contains("Summary unavailable: Model failed"))
    }
}
