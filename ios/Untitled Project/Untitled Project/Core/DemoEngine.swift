import Foundation

// Placeholder engines so the whole app works end to end before real models are added.
// They are honest about it: the transcript is canned (it does NOT come from the audio) and the
// summary is built by simple rules, not by a language model. The UI shows a "Demo mode" notice.

nonisolated enum DemoSamples {
    static let errands =
        "Okay so, um, quick note to myself. Tomorrow morning I need to call the dentist at 9 to reschedule my cleaning, because I have that team meeting at 10. After work I have to pick up the dry cleaning and get milk, eggs, and coffee at the store. Oh, and I need to send the project report to Sarah by Friday, she said the deadline is firm. I should also remind Tom to bring the projector to Thursday's demo. Uh, yeah, that's it."

    static let reflection =
        "I was thinking about the hike we did on Saturday. The trail along the ridge was really beautiful, the leaves were all orange and red. It took about four hours round trip, and the view from the top looked out over the whole valley. What struck me most was how quiet it was. We only passed maybe five other people the whole day. Anyway, it was just a really good day."

    static let meeting =
        "So, uh, notes from the planning meeting just now. The big thing is we're moving the launch from March 3rd to March 17th. The reason is the checkout bug, the one where payments fail for people using the older iPhones. Priya said she can fix it but not before the end of February, so she's going to have it done by February 28th. Um, and we also decided to push the mobile app to the third quarter, there's just no way we can do both. Marcus is going to update the pricing page before the launch. Oh, and somebody, I think it was Dana, needs to email the existing customers about the delay. The ad budget of twelve thousand dollars got approved, which is good news. Anyway, that was basically it."

    static let all = [errands, reflection, meeting]

    /// Same file name -> same sample, so the demo is predictable (String.hashValue is randomized per launch).
    static func index(for name: String, count: Int) -> Int {
        name.utf8.reduce(0) { ($0 &+ Int($1)) } % max(count, 1)
    }

    /// Builds segments with plausible timestamps (about 2.6 words per second).
    static func segments(for text: String) -> [Segment] {
        var clock = 0.0
        return Sentences.split(text).map { sentence in
            let duration = max(1.0, Double(sentence.split(separator: " ").count) / 2.6)
            defer { clock += duration }
            return Segment(start: clock, end: clock + duration, text: sentence)
        }
    }
}

nonisolated struct DemoTranscriber: Transcribing {
    var latency: Duration = .milliseconds(1200)
    var displayName: String { "Demo (placeholder transcript)" }

    func transcribe(audioURL: URL) async throws -> TranscriptData {
        let started = ContinuousClock.now
        try await Task.sleep(for: latency)
        let text = DemoSamples.all[DemoSamples.index(for: audioURL.lastPathComponent, count: DemoSamples.all.count)]
        return TranscriptData(
            text: text,
            language: "en",
            segments: DemoSamples.segments(for: text),
            model: displayName,
            elapsedSeconds: started.seconds
        )
    }
}

/// Extractive and rule-based: it only ever re-uses sentences from the transcript, so it can't
/// invent anything. Action items are sentences with commitment cues ("need to", "remind", ...).
nonisolated struct HeuristicSummarizer: Summarizing {
    var latency: Duration = .milliseconds(700)
    var displayName: String { "Demo (rule-based, not a language model)" }

    private static let maxKeyPoints = 6
    private static let maxLeadLength = 280

    func summarize(_ transcript: TranscriptData) async throws -> SummaryData {
        let started = ContinuousClock.now
        try await Task.sleep(for: latency)

        var kept: [(text: String, isAction: Bool)] = []
        for raw in Sentences.split(transcript.text) where !Self.isClosing(raw) {
            let text = Self.clean(raw)
            guard text.split(separator: " ").count >= 4 else { continue }
            kept.append((text, Self.isAction(text)))
        }
        guard !kept.isEmpty else {
            if Sentences.split(transcript.text).isEmpty { throw SummarizationFailure.noSpeech }
            return SummaryData(summary: transcript.text, model: displayName, elapsedSeconds: started.seconds)
        }

        // Lead: the first one or two sentences (one if two would be too long).
        var lead = kept.prefix(2).map(\.text).joined(separator: " ")
        var leadCount = min(2, kept.count)
        if lead.count > Self.maxLeadLength {
            lead = kept[0].text
            leadCount = 1
        }

        let points = kept.dropFirst(leadCount).filter { !$0.isAction }.prefix(Self.maxKeyPoints).map(\.text)
        let actions = kept.filter(\.isAction).map { Self.actionPhrase($0.text) }

        return SummaryData(
            summary: lead,
            keyPoints: points.map { $0 },
            actionItems: actions,
            model: displayName,
            elapsedSeconds: started.seconds
        )
    }

    // MARK: rules

    private static let actionPattern =
        #"\b(need to|needs to|have to|has to|should|must|remind|don't forget|do not forget|make sure|remember to|going to|i'll|i will|gotta)\b"#

    static func isAction(_ sentence: String) -> Bool {
        sentence.range(of: actionPattern, options: [.regularExpression, .caseInsensitive]) != nil
    }

    static func isClosing(_ sentence: String) -> Bool {
        let s = sentence.lowercased()
        return ["that's it", "that's all", "that was it", "that was basically it"].contains { s.contains($0) }
    }

    /// Removes filler words and capitalizes: "Okay so, um, quick note" -> "Quick note".
    static func clean(_ sentence: String) -> String {
        var s = sentence
        s = s.replacingOccurrences(of: #"^(?:(?:so|um|uh|oh|okay|ok|and|also|well|anyway|yeah)[,\s]+)+"#, with: "", options: [.regularExpression, .caseInsensitive])
        s = s.replacingOccurrences(of: #"\s*,?\s*\b(?:um|uh)\b,?"#, with: "", options: [.regularExpression, .caseInsensitive])
        s = s.trimmingCharacters(in: .whitespacesAndNewlines)
        return s.prefix(1).uppercased() + s.dropFirst()
    }

    /// Shortens an action sentence: drops trailing explanations and the final period.
    static func actionPhrase(_ sentence: String) -> String {
        var s = sentence.replacingOccurrences(of: #",\s+(because|which|he|she|they|but|so)\b.*$"#, with: "", options: [.regularExpression, .caseInsensitive])
        while let last = s.last, ".!?,;".contains(last) { s.removeLast() }
        return s
    }
}

extension ContinuousClock.Instant {
    /// Seconds elapsed since this instant.
    nonisolated var seconds: Double {
        let d = ContinuousClock.now - self
        return Double(d.components.seconds) + Double(d.components.attoseconds) / 1e18
    }
}
