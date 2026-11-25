import SwiftUI

/// History list on the left (a plain list on iPhone), the selected note on the right.
struct RootView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        @Bindable var model = model

        NavigationSplitView {
            HistoryView()
        } detail: {
            if let id = model.selection, let note = model.note(id) {
                NoteDetailView(note: note).id(note.id)
            } else {
                ContentUnavailableView(
                    "No note selected",
                    systemImage: "waveform",
                    description: Text("Choose a note from the list, or create a new one.")
                )
            }
        }
        .sheet(isPresented: $model.isPresentingNewNote) { NewNoteView() }
        // While the sheet is up it shows its own alert.
        .alert("Something went wrong", isPresented: Binding(
            get: { model.alert != nil && !model.isPresentingNewNote },
            set: { if !$0 { model.alert = nil } }
        )) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(model.alert ?? "")
        }
    }
}

#Preview {
    RootView().environment(AppModel.preview()).tint(.primary)
}
