import SwiftUI

/// The one prominent button style: solid, monochrome (black in light mode, white in dark mode).
struct PrimaryButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.headline)
            .foregroundStyle(.background)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 16)
            .background(
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .fill(.primary)
                    .opacity(isEnabled ? (configuration.isPressed ? 0.8 : 1) : 0.2)
            )
    }
}

/// Small uppercase heading above a section ("KEY POINTS").
struct SectionLabel: View {
    let text: String

    var body: some View {
        Text(text.uppercased())
            .font(.caption.weight(.semibold))
            .tracking(1)
            .foregroundStyle(.secondary)
            .accessibilityAddTraits(.isHeader)
    }
}

struct BulletList: View {
    let items: [String]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                HStack(alignment: .firstTextBaseline, spacing: 10) {
                    Text("•").foregroundStyle(.secondary)
                    Text(item.capitalizedFirst)
                }
                .accessibilityElement(children: .combine)
            }
        }
    }
}

/// Shown while placeholder engines are in use, so nobody mistakes the output for real AI results.
struct DemoNotice: View {
    var body: some View {
        Label {
            Text("Demo mode: transcripts and summaries are placeholders until the on-device models are added.")
                .font(.footnote)
        } icon: {
            Image(systemName: "info.circle")
        }
        .foregroundStyle(.secondary)
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.quaternary.opacity(0.5), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
    }
}

extension String {
    /// The model often returns lowercase fragments; capitalize for display only.
    var capitalizedFirst: String { prefix(1).uppercased() + dropFirst() }
}

extension TimeInterval {
    /// "0:07", "12:03"
    var clock: String { String(format: "%d:%02d", Int(self) / 60, Int(self) % 60) }
}
