import SwiftUI
import UniformTypeIdentifiers

/// The "New note" sheet: record or import audio, then process it.
struct NewNoteView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @Environment(\.openURL) private var openURL

    private enum Source: String, CaseIterable, Identifiable {
        case record = "Record"
        case importFile = "Import"
        var id: Self { self }
    }

    @State private var source: Source = .record
    @State private var recorder = AudioRecorder()
    @State private var importedURL: URL?
    @State private var showingImporter = false

    private var canProcess: Bool {
        source == .record ? recorder.recordedURL != nil : importedURL != nil
    }

    var body: some View {
        NavigationStack {
            Group {
                if let stage = model.stage { processing(stage) } else { form }
            }
            .padding(20)
            .navigationTitle("New note")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") {
                        recorder.discard()
                        dismiss()
                    }
                    .disabled(model.isBusy)
                }
            }
        }
        .interactiveDismissDisabled(model.isBusy || recorder.isRecording)
        .fileImporter(isPresented: $showingImporter, allowedContentTypes: [.audio]) { result in
            if case .success(let url) = result { importedURL = url }
        }
        .alert("Something went wrong", isPresented: Binding(
            get: { model.alert != nil },
            set: { if !$0 { model.alert = nil } }
        )) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(model.alert ?? "")
        }
        .onDisappear { recorder.discard() }
    }

    // MARK: form

    private var form: some View {
        VStack(spacing: 24) {
            Picker("Source", selection: $source) {
                ForEach(Source.allCases) { Text($0.rawValue).tag($0) }
            }
            .pickerStyle(.segmented)
            .disabled(recorder.isRecording)

            Group {
                switch source {
                case .record: recordPane
                case .importFile: importPane
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)

            if model.engines.isDemo { DemoNotice() }

            Button("Transcribe and summarize") { Task { await run() } }
                .buttonStyle(PrimaryButtonStyle())
                .disabled(!canProcess)
        }
    }

    private var recordPane: some View {
        VStack(spacing: 20) {
            Text(recorder.elapsed.clock)
                .font(.system(size: 56, weight: .thin, design: .rounded))
                .monospacedDigit()

            Button { Task { await recorder.toggle() } } label: {
                ZStack {
                    Circle().strokeBorder(.primary.opacity(0.15), lineWidth: 4).frame(width: 96, height: 96)
                    RoundedRectangle(cornerRadius: recorder.isRecording ? 8 : 34, style: .continuous)
                        .fill(.red)
                        .frame(width: recorder.isRecording ? 34 : 68, height: recorder.isRecording ? 34 : 68)
                }
                .animation(.snappy, value: recorder.isRecording)
            }
            .buttonStyle(.plain)
            .accessibilityLabel(recorder.isRecording ? "Stop recording" : "Start recording")

            Text(recordHint)
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)

            if recorder.state == .denied {
                Button("Open Settings") { if let url = URL(string: "app-settings:") { openURL(url) } }
                    .buttonStyle(.bordered)
            }
        }
    }

    private var recordHint: String {
        switch recorder.state {
        case .idle: "Tap to start recording"
        case .recording: "Recording… tap to stop"
        case .finished(_, let duration): "Recorded \(duration.clock). Tap to record again."
        case .denied: "Microphone access is off. Turn it on in Settings > Privacy & Security > Microphone."
        case .failed(let message): "Couldn't record: \(message)"
        }
    }

    private var importPane: some View {
        Button { showingImporter = true } label: {
            VStack(spacing: 10) {
                Image(systemName: importedURL == nil ? "square.and.arrow.down" : "waveform.circle.fill")
                    .font(.system(size: 34, weight: .light))
                Text(importedURL?.lastPathComponent ?? "Choose an audio file")
                    .font(.headline)
                    .multilineTextAlignment(.center)
                Text(importedURL == nil
                     ? "From Files or iCloud Drive. For a Voice Memo: open it, tap Share, then Save to Files."
                     : "Tap to choose a different file")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            }
            .padding(24)
            .frame(maxWidth: .infinity, minHeight: 200)
            .background(
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .strokeBorder(.secondary.opacity(0.4), style: StrokeStyle(lineWidth: 1.5, dash: [7]))
            )
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    private func processing(_ stage: AppModel.Stage) -> some View {
        VStack(spacing: 16) {
            ProgressView().controlSize(.large)
            Text(stage.rawValue).font(.headline)
            Text("Everything runs on this device.").font(.subheadline).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: action

    private func run() async {
        let url: URL
        let move: Bool
        switch source {
        case .record:
            guard let recorded = recorder.recordedURL else { return }
            (url, move) = (recorded, true)  // a temporary file: move it into the store
        case .importFile:
            guard let imported = importedURL else { return }
            (url, move) = (imported, false)  // the user's own file: copy, never move
        }
        if let id = await model.process(audio: url, move: move) {
            model.selection = id
            dismiss()
        }
    }
}

#Preview {
    NewNoteView().environment(AppModel.preview(seeded: false)).tint(.primary)
}
