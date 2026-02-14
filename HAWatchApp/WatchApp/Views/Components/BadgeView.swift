import SwiftUI
import HAWatchCore

struct BadgeView: View {
    let badge: RenderedBadge

    var body: some View {
        HStack(spacing: 4) {
            if let iconName = badge.iconName {
                EntityIconView(sfSymbolName: iconName, size: .caption)
            }

            Text(badge.name)
                .font(.caption2)
                .lineLimit(1)

            if let state = badge.state {
                EntityStateText(state: state)
                    .font(.caption2)
            }
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(.ultraThinMaterial, in: Capsule())
    }
}
