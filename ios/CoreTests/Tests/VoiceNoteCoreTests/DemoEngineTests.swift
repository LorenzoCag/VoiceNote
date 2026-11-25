import Foundation
import Testing

@testable import VoiceNoteCore

@Suite struct DemoEngineTests {
    let summarizer = HeuristicSummarizer(latency: .zero)
    let transcriber = DemoTranscriber(latency: .zero)

    func summary(of text: String) async throws -> SummaryData {
        try await summarizer.summarize(TranscriptData(text: text))
    }

    // MARK: summarizer

    @Test func errandsYieldTheRightActionItems() async throws {
        let s = try await summary(of: DemoSamples.errands)
        #expect(s.actionItems.count == 4)
        let joined = s.actionItems.joined(separator: " ").lowercased()
        for expected in ["dentist", "dry cleaning", "sarah", "tom"] { #expect(joined.contains(expected), "missing \(expected)") }
    }

    @Test func reflectionHasNoActionItems() async throws {
        let s = try await summary(of: DemoSamples.reflection)
        #expect(s.actionItems.isEmpty)
        #expect(!s.keyPoints.isEmpty)
    }

    @Test func meetingKeepsOwnersInActionItems() async throws {
        let s = try await summary(of: DemoSamples.meeting)
        let joined = s.actionItems.joined(separator: " ")
        for name in ["Priya", "Marcus", "Dana"] { #expect(joined.contains(name), "missing \(name)") }
    }

    @Test func fillerWordsAndClosersAreRemoved() async throws {
        let s = try await summary(of: DemoSamples.errands)
        let all = ([s.summary] + s.keyPoints + s.actionItems).joined(separator: " ").lowercased()
        #expect(!all.contains(" um,"))
        #expect(!all.contains("that's it"))
        #expect(!s.summary.hasPrefix("Okay"))
    }

    @Test func everythingComesFromTheTranscript() async throws {
        // Extractive by design: no word in the output may be absent from the transcript.
        let words = { (text: String) in Set(text.lowercased().split(whereSeparator: { !$0.isLetter && !$0.isNumber && $0 != "'" }).map(String.init)) }
        for sample in DemoSamples.all {
            let s = try await summary(of: sample)
            let source = words(sample)
            let produced = words(([s.summary] + s.keyPoints + s.actionItems).joined(separator: " "))
            #expect(produced.isSubset(of: source), "invented: \(produced.subtracting(source))")
        }
    }

    @Test func tinyTranscriptStillWorks() async throws {
        let s = try await summary(of: "Just a reminder that the library book is due on Tuesday.")
        #expect(s.summary.contains("library book"))
        #expect(s.actionItems.isEmpty)  // "reminder" is not a commitment cue
    }

    @Test func tooShortToSummarizeFallsBackToTheTextItself() async throws {
        let s = try await summary(of: "Hello there.")
        #expect(s.summary == "Hello there.")
    }

    @Test func emptyTranscriptThrowsNoSpeech() async {
        await #expect(throws: SummarizationFailure.self) { try await summary(of: "  \n ") }
    }

    @Test func summaryIsShortEnough() async throws {
        for sample in DemoSamples.all {
            let s = try await summary(of: sample)
            #expect(s.summary.count <= 300)
            #expect(s.keyPoints.count <= 6)
        }
    }

    // MARK: rules

    @Test func actionCues() {
        #expect(HeuristicSummarizer.isAction("I need to call the dentist."))
        #expect(HeuristicSummarizer.isAction("Remind Tom to bring the projector."))
        #expect(HeuristicSummarizer.isAction("Don't forget the milk."))
        #expect(!HeuristicSummarizer.isAction("The view was beautiful."))
        #expect(!HeuristicSummarizer.isAction("Just a reminder about the book."))
    }

    @Test func actionPhraseTrimsExplanationsAndPunctuation() {
        #expect(HeuristicSummarizer.actionPhrase("I need to call the dentist, because it hurts.") == "I need to call the dentist")
        #expect(HeuristicSummarizer.actionPhrase("Send the report by Friday.") == "Send the report by Friday")
    }

    // MARK: transcriber

    @Test func sameFileNameGivesTheSameSample() async throws {
        let a = try await transcriber.transcribe(audioURL: URL(fileURLWithPath: "/x/20261124-100000.m4a"))
        let b = try await transcriber.transcribe(audioURL: URL(fileURLWithPath: "/y/20261124-100000.m4a"))
        #expect(a.text == b.text)
        #expect(DemoSamples.all.contains(a.text))
        #expect(a.model.contains("Demo"))
    }

    @Test func segmentsCoverTheTextWithIncreasingTimestamps() async throws {
        let t = try await transcriber.transcribe(audioURL: URL(fileURLWithPath: "memo.m4a"))
        #expect(!t.segments.isEmpty)
        #expect(zip(t.segments, t.segments.dropFirst()).allSatisfy { $0.end <= $1.start + 0.0001 })
        #expect(t.segments.map(\.text).joined(separator: " ") == Sentences.split(t.text).joined(separator: " "))
    }

    @Test func differentFileNamesReachAllSamples() {
        let indices = Set((0..<60).map { DemoSamples.index(for: "20261124-1000\(String(format: "%02d", $0)).m4a", count: 3) })
        #expect(indices.count == 3)
    }
}
