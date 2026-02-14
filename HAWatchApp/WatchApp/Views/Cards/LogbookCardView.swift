import SwiftUI
import HAWatchCore

struct LogbookCardView: View {
    let logbook: RenderedLogbook

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            ForEach(Array(logbook.entries.enumerated()), id: \.offset) { _, entry in
                HStack {
                    Text(entry.name)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)

                    EntityStateText(state: entry.state)
                        .font(.caption2)

                    Spacer(minLength: 0)

                    Text(entry.timeAgo)
                        .font(.system(size: 9))
                        .foregroundStyle(.tertiary)
                }
            }
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 12))
    }
}
