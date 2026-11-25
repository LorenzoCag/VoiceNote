import Foundation

/// A readable export of a note (same layout as the Mac app's Markdown export).
nonisolated enum NoteMarkdown {
    static func render(_ note: Note) -> String {
        var lines = [
            "# \(note.title)",
            "",
            "*\(note.created.formatted(.dateTime.weekday(.wide).month(.wide).day().year().hour().minute()))*",
            "",
        ]
        if let s = note.summary {
            lines += ["## Summary", "", s.summary, ""]
            if !s.keyPoints.isEmpty { lines += ["## Key points", ""] + s.keyPoints.map { "- \($0)" } + [""] }
            if !s.actionItems.isEmpty { lines += ["## Action items", ""] + s.actionItems.map { "- [ ] \($0)" } + [""] }
        } else if let error = note.summaryError {
            lines += ["> Summary unavailable: \(error)", ""]
        }
        lines += ["## Transcript", "", note.transcriptText.isEmpty ? "(no speech detected)" : note.transcriptText, ""]
        return lines.joined(separator: "\n")
    }
}
