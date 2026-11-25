import SwiftUI

struct HistoryView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        @Bindable var model = model

        List(selection: $model.selection) {
            ForEach(model.notes) { note in
                NoteRow(note: note)
                    .tag(note.id)
                    .swipeActions {
                        Button(role: .destructive) { model.delete(note.id) } label: {
                            Label("Delete", systemImage: "trash")
                        }
                    }
            }
        }
        .overlay {
            if model.notes.isEmpty {
                ContentUnavailableView(
                    "No notes yet",
                    systemImage: "waveform",
                    description: Text("Record or import audio to get a transcript, summary, and action items.")
                )
            }
        }
        .navigationTitle("VoiceNote")
        #if os(iOS)
        .navigationSubtitle("Private. Runs entirely on this device.")
        #endif
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button { model.isPresentingNewNote = true } label: { Label("New note", systemImage: "plus") }
            }
        }
        .safeAreaInset(edge: .bottom) {
            Button { model.isPresentingNewNote = true } label: {
                Label("New note", systemImage: "mic.fill")
            }
            .buttonStyle(PrimaryButtonStyle())
            .padding(.horizontal, 20)
            .padding(.vertical, 8)
        }
    }
}

private struct NoteRow: View {
    let note: Note

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(note.title).lineLimit(2)
            HStack(spacing: 6) {
                Text(note.created.formatted(.dateTime.month(.abbreviated).day().hour().minute()))
                if note.summary == nil {
                    Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(.orange)
                        .accessibilityLabel("Summary unavailable")
                }
            }
            .font(.caption)
            .foregroundStyle(.secondary)
        }
        .padding(.vertical, 2)
    }
}

#Preview {
    NavigationStack { HistoryView() }.environment(AppModel.preview()).tint(.primary)
}
