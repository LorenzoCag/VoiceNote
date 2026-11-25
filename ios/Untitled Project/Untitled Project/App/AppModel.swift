import Foundation
import Observation

/// App-wide state and the "save audio -> transcribe -> summarize -> store" workflow
/// (the iOS counterpart of the Mac app's VoiceNoteService).
@Observable
final class AppModel {
    enum Stage: String {
        case saving = "Saving audio…"
        case transcribing = "Transcribing…"
        case summarizing = "Summarizing…"
    }

    private(set) var notes: [Note] = []
    /// The note shown in the detail column (or pushed on iPhone).
    var selection: String?
    var isPresentingNewNote = false
    /// Non-nil while a note is being processed.
    private(set) var stage: Stage?
    /// A message to show the user, set when processing fails.
    var alert: String?

    let store: NoteStore
    let engines: Engines

    var isBusy: Bool { stage != nil }

    init(store: NoteStore = .default, engines: Engines = .current) {
        self.store = store
        self.engines = engines
        notes = store.list()
        #if DEBUG
        applyLaunchArguments()
        #endif
    }

    func note(_ id: String) -> Note? { notes.first { $0.id == id } }

    func reload() { notes = store.list() }

    // MARK: workflow

    /// Imports (or moves) the audio, transcribes it, summarizes it, and stores the note.
    /// Returns the new note's id, or nil if something failed (see `alert`).
    func process(audio source: URL, move: Bool) async -> String? {
        guard stage == nil else { return nil }
        defer { stage = nil }

        var audioURL: URL?
        do {
            stage = .saving
            let store = self.store
            let url = try await Task.detached { try store.ingestAudio(from: source, move: move) }.value
            audioURL = url

            stage = .transcribing
            let transcript = try await engines.transcriber.transcribe(audioURL: url)
            let note = try store.save(
                Note.create(id: url.deletingPathExtension().lastPathComponent, audioFile: url.lastPathComponent, transcript: transcript)
            )
            reload()

            stage = .summarizing
            return await summarize(note).id
        } catch {
            if let audioURL { try? FileManager.default.removeItem(at: audioURL) }  // no orphan recordings
            alert = error.localizedDescription
            return nil
        }
    }

    /// Adds a summary to the note, or records why it isn't available. Never throws: the
    /// transcript is always kept.
    @discardableResult
    func summarize(_ note: Note) async -> Note {
        var note = note
        note.summary = nil
        note.summaryError = nil
        let transcript = note.transcript ?? TranscriptData(text: "")
        if transcript.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            note.summaryError = SummarizationFailure.noSpeech.localizedDescription
        } else {
            do {
                note.summary = try await engines.summarizer.summarize(transcript)
            } catch {
                note.summaryError = error.localizedDescription
            }
        }
        let saved = (try? store.save(note)) ?? note
        reload()
        return saved
    }

    func retrySummary(for id: String) async {
        guard stage == nil, let note = note(id) else { return }
        stage = .summarizing
        await summarize(note)
        stage = nil
    }

    func delete(_ id: String) {
        try? store.delete(id)
        if selection == id { selection = nil }
        reload()
    }
}

#if DEBUG
// Development helpers: launch arguments for jumping straight to a screen, and previews.
extension AppModel {
    fileprivate func applyLaunchArguments() {
        let args = ProcessInfo.processInfo.arguments
        guard ["-seedDemoNotes", "-openFirstNote", "-showNewNote"].contains(where: args.contains) else { return }
        Task {
            if args.contains("-seedDemoNotes"), notes.isEmpty { await seedDemoNotes() }
            if args.contains("-openFirstNote") { selection = notes.first?.id }
            if args.contains("-showNewNote") { isPresentingNewNote = true }
        }
    }

    /// Fills the store with the three demo samples (no audio files).
    func seedDemoNotes() async {
        let fast = HeuristicSummarizer(latency: .zero)
        for (i, text) in DemoSamples.all.enumerated() {
            let date = Date().addingTimeInterval(-Double(i) * 3 * 3600 - 600)
            let transcript = TranscriptData(text: text, language: "en", segments: DemoSamples.segments(for: text), model: "Demo (placeholder transcript)")
            var note = Note.create(id: NoteDates.idString(from: date), audioFile: nil, transcript: transcript, date: date)
            note.summary = try? await fast.summarize(transcript)
            _ = try? store.save(note)
        }
        reload()
    }

    /// An isolated model backed by a temporary folder, for SwiftUI previews.
    static func preview(seeded: Bool = true) -> AppModel {
        let root = FileManager.default.temporaryDirectory.appending(path: "VoiceNotePreview-\(UUID().uuidString)")
        let model = AppModel(store: NoteStore(root: root), engines: .demo)
        if seeded { Task { await model.seedDemoNotes() } }
        return model
    }
}
#endif
