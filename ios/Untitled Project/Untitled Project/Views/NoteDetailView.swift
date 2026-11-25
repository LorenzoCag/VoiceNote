import SwiftUI

struct NoteDetailView: View {
    let note: Note
    @Environment(AppModel.self) private var model
    @State private var confirmingDelete = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                if let url = model.store.audioURL(for: note) {
                    AudioPlayerView(url: url).padding(.bottom, 20)
                }

                if let summary = note.summary {
                    summarySections(summary)
                } else {
                    unavailable
                }

                SectionLabel(text: "Transcript").padding(.top, 28).padding(.bottom, 8)
                DisclosureGroup("Show transcript") {
                    Text(note.transcriptText.isEmpty ? "(no speech detected)" : note.transcriptText)
                        .lineSpacing(5)
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.top, 8)
                }

                Text(footer)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .padding(.top, 24)
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 12)
            .frame(maxWidth: 720, alignment: .leading)  // keeps lines readable on iPad
            .frame(maxWidth: .infinity)
        }
        .navigationTitle(note.created.formatted(.dateTime.month(.abbreviated).day().hour().minute()))
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .toolbar {
            ToolbarItemGroup(placement: .primaryAction) {
                ShareLink(item: NoteMarkdown.render(note), subject: Text(note.title)) {
                    Label("Share", systemImage: "square.and.arrow.up")
                }
                Button(role: .destructive) { confirmingDelete = true } label: {
                    Label("Delete", systemImage: "trash")
                }
            }
        }
        .confirmationDialog("Delete this note and its recording?", isPresented: $confirmingDelete, titleVisibility: .visible) {
            Button("Delete", role: .destructive) { model.delete(note.id) }
            Button("Cancel", role: .cancel) {}
        }
    }

    // MARK: sections

    @ViewBuilder
    private func summarySections(_ summary: SummaryData) -> some View {
        Text(summary.summary)
            .font(.title3.weight(.medium))
            .lineSpacing(4)

        if !summary.keyPoints.isEmpty {
            SectionLabel(text: "Key points").padding(.top, 28).padding(.bottom, 8)
            BulletList(items: summary.keyPoints)
        }

        SectionLabel(text: "Action items").padding(.top, 28).padding(.bottom, 8)
        if summary.actionItems.isEmpty {
            Text("None").foregroundStyle(.secondary)
        } else {
            BulletList(items: summary.actionItems)
        }

        let removed = summary.warnings.filter { $0.hasPrefix("dropped ungrounded") }.count
        if removed > 0 {
            Text("\(removed) generated item(s) were removed because they did not match what was said.")
                .font(.footnote)
                .foregroundStyle(.secondary)
                .padding(.top, 16)
        }
    }

    private var unavailable: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Summary unavailable", systemImage: "exclamationmark.triangle").font(.headline)
            Text(note.summaryError ?? "Unknown error").foregroundStyle(.secondary)
            if !note.transcriptText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                HStack(spacing: 12) {
                    Button("Try again") { Task { await model.retrySummary(for: note.id) } }
                        .buttonStyle(.bordered)
                        .disabled(model.isBusy)
                    if model.isBusy { ProgressView() }
                }
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.orange.opacity(0.12), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }

    private var footer: String {
        var parts: [String] = []
        if let model = note.transcript?.model, !model.isEmpty { parts.append(model) }
        if let summary = note.summary {
            if !summary.model.isEmpty { parts.append(summary.model) }
            parts.append("summarized in \(String(format: "%.1f", summary.elapsedSeconds))s")
        }
        return parts.joined(separator: " · ")
    }
}

#Preview {
    let model = AppModel.preview(seeded: false)
    let transcript = TranscriptData(text: DemoSamples.errands, language: "en", segments: DemoSamples.segments(for: DemoSamples.errands), model: "Demo")
    var note = Note.create(id: "20261124-100000", audioFile: nil, transcript: transcript)
    note.summary = SummaryData(
        summary: "Tomorrow morning I need to call the dentist at 9 to reschedule my cleaning.",
        keyPoints: ["The project report deadline is firm"],
        actionItems: ["Call the dentist", "Send the report to Sarah by Friday"],
        model: "Demo"
    )
    return NavigationStack { NoteDetailView(note: note) }.environment(model).tint(.primary)
}
