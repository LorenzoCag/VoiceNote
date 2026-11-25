import AVFoundation
import Observation

/// Plays back a note's recording.
@Observable
final class AudioPlayerModel {
    private(set) var isPlaying = false
    private(set) var progress: Double = 0
    private(set) var currentTime: TimeInterval = 0
    private(set) var duration: TimeInterval = 0

    private var player: AVAudioPlayer?
    private var ticker: Task<Void, Never>?

    /// False if the file couldn't be decoded.
    var isAvailable: Bool { player != nil }

    init(url: URL) {
        player = try? AVAudioPlayer(contentsOf: url)
        duration = player?.duration ?? 0
    }

    func toggle() {
        guard let player else { return }
        if player.isPlaying {
            pause()
            return
        }
        #if os(iOS)
        try? AVAudioSession.sharedInstance().setCategory(.playback)
        try? AVAudioSession.sharedInstance().setActive(true)
        #endif
        player.play()
        isPlaying = true
        startTicker()
    }

    func pause() {
        player?.pause()
        isPlaying = false
        ticker?.cancel()
    }

    func stop() {
        player?.stop()
        player?.currentTime = 0
        isPlaying = false
        progress = 0
        currentTime = 0
        ticker?.cancel()
    }

    private func startTicker() {
        ticker?.cancel()
        ticker = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .milliseconds(100))
                guard let self, let player = self.player else { return }
                if player.isPlaying {
                    self.currentTime = player.currentTime
                    self.progress = player.duration > 0 ? player.currentTime / player.duration : 0
                } else {
                    // Reached the end (or was paused elsewhere): reset.
                    self.isPlaying = false
                    if player.currentTime == 0 || player.currentTime >= player.duration - 0.2 {
                        self.progress = 0
                        self.currentTime = 0
                    }
                    return
                }
            }
        }
    }
}
