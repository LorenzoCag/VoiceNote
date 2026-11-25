import Foundation

// The seam between the app and whatever does the AI work.
//
// Today the app ships with the demo engines in DemoEngine.swift. To go on-device, add types that
// conform to these protocols (e.g. a WhisperKit-based Transcribing and an MLX Swift-based
// Summarizing) and switch `Engines.current`. Nothing in the UI needs to change.
//
// Note for real engines: heavy inference should run off the main actor (mark the work @concurrent
// or run it in a detached task) so the UI stays responsive.

nonisolated protocol Transcribing: Sendable {
    var displayName: String { get }
    func transcribe(audioURL: URL) async throws -> TranscriptData
}

nonisolated protocol Summarizing: Sendable {
    var displayName: String { get }
    /// Throws `SummarizationFailure.noSpeech` for an empty transcript.
    func summarize(_ transcript: TranscriptData) async throws -> SummaryData
}

nonisolated enum SummarizationFailure: LocalizedError {
    case noSpeech

    var errorDescription: String? {
        switch self {
        case .noSpeech: "No speech was detected in this recording."
        }
    }
}

nonisolated struct Engines: Sendable {
    var transcriber: any Transcribing
    var summarizer: any Summarizing
    /// True while placeholder engines are in use; the UI says so openly.
    var isDemo: Bool

    static let demo = Engines(transcriber: DemoTranscriber(), summarizer: HeuristicSummarizer(), isDemo: true)

    /// The engines the app uses. Swap this when real on-device models are available.
    static let current = Engines.demo
}
