import SwiftUI
import HAWatchCore

struct TileCardView: View {
    let tile: RenderedTile

    var body: some View {
        HStack(spacing: 8) {
            if let iconName = tile.iconName {
                EntityIconView(
                    sfSymbolName: iconName,
                    color: tile.state.color.isActive ? tile.state.color.swiftUIColor : nil
                )
            }

            VStack(alignment: .leading, spacing: 1) {
                Text(tile.name)
                    .font(.caption)
                    .lineLimit(1)
                    .foregroundStyle(.primary)

                if !tile.state.text.isEmpty {
                    EntityStateText(state: tile.state)
                        .font(.caption2)
                }
            }

            Spacer(minLength: 0)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 12))
    }
}
