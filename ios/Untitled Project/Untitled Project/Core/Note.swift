import Foundation

// The note format intentionally matches the JSON written by the Mac app (voicenote/storage.py),
// so notes can move between the two. Keys are snake_case on disk; decoding is lenient about
// missing optional data so older or hand-edited files still load.

// MARK: - Transcript

nonisolated struct Segment: Codable, Hashable, Sendable {
    var start: Double
    var end: Double
    var text: String
}

nonisolated struct TranscriptData: Codable, Hashable, Sendable {
    var text: String
    var language: String?
    var segments: [Segment]
    var model: String
    var elapsedSeconds: Double

    init(text: String, language: String? = nil, segments: [Segment] = [], model: String = "", elapsedSeconds: Double = 0) {
        self.text = text
        self.language = language
        self.segments = segments
        self.model = model
        self.elapsedSeconds = elapsedSeconds
    }

    private enum CodingKeys: String, CodingKey {
        case text, language, segments, model
        case elapsedSeconds = "elapsed_seconds"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        text = try c.decodeIfPresent(String.self, forKey: .text) ?? ""
        language = try c.decodeIfPresent(String.self, forKey: .language)
        segments = try c.decodeIfPresent([Segment].self, forKey: .segments) ?? []
        model = try c.decodeIfPresent(String.self, forKey: .model) ?? ""
        elapsedSeconds = try c.decodeIfPresent(Double.self, forKey: .elapsedSeconds) ?? 0
    }
}

// MARK: - Summary

nonisolated struct SummaryData: Codable, Hashable, Sendable {
    var summary: String
    var keyPoints: [String]
    var actionItems: [String]
    var model: String
    var elapsedSeconds: Double
    var llmCalls: Int
    var chunks: Int
    var promptTokens: Int
    var generationTokens: Int
    var peakMemoryGb: Double
    var warnings: [String]

    init(
        summary: String,
        keyPoints: [String] = [],
        actionItems: [String] = [],
        model: String = "",
        elapsedSeconds: Double = 0,
        llmCalls: Int = 0,
        chunks: Int = 1,
        promptTokens: Int = 0,
        generationTokens: Int = 0,
        peakMemoryGb: Double = 0,
        warnings: [String] = []
    ) {
        self.summary = summary
        self.keyPoints = keyPoints
        self.actionItems = actionItems
        self.model = model
        self.elapsedSeconds = elapsedSeconds
        self.llmCalls = llmCalls
        self.chunks = chunks
        self.promptTokens = promptTokens
        self.generationTokens = generationTokens
        self.peakMemoryGb = peakMemoryGb
        self.warnings = warnings
    }

    private enum CodingKeys: String, CodingKey {
        case summary, model, chunks, warnings
        case keyPoints = "key_points"
        case actionItems = "action_items"
        case elapsedSeconds = "elapsed_seconds"
        case llmCalls = "llm_calls"
        case promptTokens = "prompt_tokens"
        case generationTokens = "generation_tokens"
        case peakMemoryGb = "peak_memory_gb"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        summary = try c.decode(String.self, forKey: .summary)
        keyPoints = try c.decodeIfPresent([String].self, forKey: .keyPoints) ?? []
        actionItems = try c.decodeIfPresent([String].self, forKey: .actionItems) ?? []
        model = try c.decodeIfPresent(String.self, forKey: .model) ?? ""
        elapsedSeconds = try c.decodeIfPresent(Double.self, forKey: .elapsedSeconds) ?? 0
        llmCalls = try c.decodeIfPresent(Int.self, forKey: .llmCalls) ?? 0
        chunks = try c.decodeIfPresent(Int.self, forKey: .chunks) ?? 1
        promptTokens = try c.decodeIfPresent(Int.self, forKey: .promptTokens) ?? 0
        generationTokens = try c.decodeIfPresent(Int.self, forKey: .generationTokens) ?? 0
        peakMemoryGb = try c.decodeIfPresent(Double.self, forKey: .peakMemoryGb) ?? 0
        warnings = try c.decodeIfPresent([String].self, forKey: .warnings) ?? []
    }
}

// MARK: - Note

nonisolated struct Note: Codable, Hashable, Identifiable, Sendable {
    static let schemaVersion = 1

    var id: String
    var createdAt: String  // "2026-11-24T17:12:58", local time, same as the Mac app
    var audioFile: String?  // file name inside the recordings directory
    var transcript: TranscriptData?
    var summary: SummaryData?
    var summaryError: String?
    var title: String
    var version: Int

    init(
        id: String,
        createdAt: String,
        audioFile: String? = nil,
        transcript: TranscriptData? = nil,
        summary: SummaryData? = nil,
        summaryError: String? = nil,
        title: String = "",
        version: Int = Note.schemaVersion
    ) {
        self.id = id
        self.createdAt = createdAt
        self.audioFile = audioFile
        self.transcript = transcript
        self.summary = summary
        self.summaryError = summaryError
        self.title = title
        self.version = version
    }

    private enum CodingKeys: String, CodingKey {
        case id, transcript, summary, title, version
        case createdAt = "created_at"
        case audioFile = "audio_file"
        case summaryError = "summary_error"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        createdAt = try c.decode(String.self, forKey: .createdAt)
        audioFile = try c.decodeIfPresent(String.self, forKey: .audioFile)
        transcript = try c.decodeIfPresent(TranscriptData.self, forKey: .transcript)
        summary = try c.decodeIfPresent(SummaryData.self, forKey: .summary)
        summaryError = try c.decodeIfPresent(String.self, forKey: .summaryError)
        title = try c.decodeIfPresent(String.self, forKey: .title) ?? ""
        version = try c.decodeIfPresent(Int.self, forKey: .version) ?? Note.schemaVersion
    }

    var transcriptText: String { transcript?.text ?? "" }
    var created: Date { NoteDates.date(from: createdAt) ?? .distantPast }

    static func create(id: String, audioFile: String?, transcript: TranscriptData?, date: Date = Date()) -> Note {
        var note = Note(id: id, createdAt: NoteDates.string(from: date), audioFile: audioFile, transcript: transcript)
        note.refreshTitle()
        return note
    }

    mutating func refreshTitle() {
        title = Note.makeTitle(summary: summary?.summary, transcript: transcriptText)
    }

    /// Short human title: first sentence of the summary, else the start of the transcript.
    static func makeTitle(summary: String?, transcript: String, maxLength: Int = 60) -> String {
        let source = (summary?.isEmpty == false ? summary : nil) ?? transcript
        let flat = source.split(whereSeparator: \.isWhitespace).joined(separator: " ")
        guard !flat.isEmpty else { return "Empty recording" }
        let first = Sentences.split(flat).first ?? flat
        guard first.count > maxLength else { return first }
        return String(first.prefix(maxLength - 1)).trimmingCharacters(in: .whitespaces) + "…"
    }
}

// MARK: - Dates

nonisolated enum NoteDates {
    private static func formatter(_ format: String) -> DateFormatter {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = .current
        f.dateFormat = format
        return f
    }

    static func string(from date: Date) -> String { formatter("yyyy-MM-dd'T'HH:mm:ss").string(from: date) }
    static func date(from string: String) -> Date? { formatter("yyyy-MM-dd'T'HH:mm:ss").date(from: string) }
    /// Note id / audio file stem, e.g. "20261124-171258".
    static func idString(from date: Date) -> String { formatter("yyyyMMdd-HHmmss").string(from: date) }
}

// MARK: - Sentences

nonisolated enum Sentences {
    /// Splits on . ! ? followed by whitespace or the end of the text ("3.5" stays together).
    static func split(_ text: String) -> [String] {
        let chars = Array(text)
        var result: [String] = []
        var current = ""
        for (i, ch) in chars.enumerated() {
            current.append(ch)
            guard ch == "." || ch == "!" || ch == "?" else { continue }
            let atEnd = i + 1 >= chars.count
            if atEnd || chars[i + 1].isWhitespace {
                result.append(current.trimmingCharacters(in: .whitespacesAndNewlines))
                current = ""
            }
        }
        let tail = current.trimmingCharacters(in: .whitespacesAndNewlines)
        if !tail.isEmpty { result.append(tail) }
        return result.filter { !$0.isEmpty }
    }
}
