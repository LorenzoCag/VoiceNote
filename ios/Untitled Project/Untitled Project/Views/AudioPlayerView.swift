import SwiftUI

/// A compact play/pause control with a progress bar.
struct AudioPlayerView: View {
    @State private var player: AudioPlayerModel

    init(url: URL) {
        _player = State(initialValue: AudioPlayerModel(url: url))
    }

    var body: some View {
        HStack(spacing: 14) {
            Button { player.toggle() } label: {
                Image(systemName: player.isPlaying ? "pause.fill" : "play.fill")
                    .font(.title3)
                    .frame(width: 32, height: 32)
            }
            .buttonStyle(.plain)
            .disabled(!player.isAvailable)
            .accessibilityLabel(player.isPlaying ? "Pause" : "Play recording")

            ProgressView(value: player.progress)
                .tint(.primary)

            Text(player.isAvailable ? (player.isPlaying ? player.currentTime : player.duration).clock : "Unavailable")
                .font(.footnote.monospacedDigit())
                .foregroundStyle(.secondary)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(.quaternary.opacity(0.5), in: Capsule())
        .onDisappear { player.stop() }
    }
}
