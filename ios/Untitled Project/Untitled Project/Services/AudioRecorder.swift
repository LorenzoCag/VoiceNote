import AVFoundation
import Observation

/// Records a voice note from the microphone to a temporary AAC (.m4a) file, mono at 16 kHz,
/// which is what speech models expect. The caller moves the finished file into the note store.
@Observable
final class AudioRecorder {
    enum State: Equatable {
        case idle
        case recording
        case finished(URL, TimeInterval)
        case denied
        case failed(String)
    }

    private(set) var state: State = .idle
    private(set) var elapsed: TimeInterval = 0

    private var recorder: AVAudioRecorder?
    private var ticker: Task<Void, Never>?

    var isRecording: Bool { state == .recording }

    var recordedURL: URL? {
        if case .finished(let url, _) = state { return url }
        return nil
    }

    func toggle() async {
        if isRecording { stop() } else { await start() }
    }

    func start() async {
        discard()  // drop any previous take
        guard await AVAudioApplication.requestRecordPermission() else {
            state = .denied
            return
        }
        do {
            #if os(iOS)
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playAndRecord, mode: .default, options: [.defaultToSpeaker])
            try session.setActive(true)
            #endif
            let url = FileManager.default.temporaryDirectory.appending(path: "recording-\(UUID().uuidString).m4a")
            let settings: [String: Any] = [
                AVFormatIDKey: Int(kAudioFormatMPEG4AAC),
                AVSampleRateKey: 16_000,
                AVNumberOfChannelsKey: 1,
                AVEncoderAudioQualityKey: AVAudioQuality.medium.rawValue,
            ]
            let recorder = try AVAudioRecorder(url: url, settings: settings)
            guard recorder.record() else { throw RecorderError.couldNotStart }
            self.recorder = recorder
            elapsed = 0
            state = .recording
            ticker = Task { [weak self] in
                while !Task.isCancelled {
                    try? await Task.sleep(for: .milliseconds(200))
                    guard let self, let recorder = self.recorder, recorder.isRecording else { return }
                    self.elapsed = recorder.currentTime
                }
            }
        } catch {
            state = .failed(error.localizedDescription)
        }
    }

    func stop() {
        guard let recorder, isRecording else { return }
        ticker?.cancel()
        let duration = recorder.currentTime
        recorder.stop()
        self.recorder = nil
        elapsed = duration
        state = .finished(recorder.url, duration)
    }

    /// Stops any recording and deletes the temporary file.
    func discard() {
        ticker?.cancel()
        recorder?.stop()
        recorder = nil
        if case .finished(let url, _) = state { try? FileManager.default.removeItem(at: url) }
        state = .idle
        elapsed = 0
    }
}

private enum RecorderError: LocalizedError {
    case couldNotStart
    var errorDescription: String? { "The microphone couldn't be started." }
}
