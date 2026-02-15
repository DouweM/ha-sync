import SwiftUI
import HAWatchCore

struct TileCardView: View {
    let tile: RenderedTile
    @Environment(SettingsManager.self) private var settings

    var body: some View {
        HStack(spacing: 8) {
            if let pictureURL = tile.entityPictureURL,
               !pictureURL.isEmpty,
               let baseURL = settings.appSettings.baseURL {
                EntityPictureView(
                    url: pictureURL,
                    baseURL: baseURL,
                    token: settings.appSettings.accessToken,
                    size: 28
                )
            } else if let iconName = tile.iconName {
                EntityIconView(
                    sfSymbolName: iconName,
                    color: tileIconColor
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

    private var tileIconColor: Color? {
        if let colorName = tile.colorName {
            return tileColor(colorName)
        }
        return tile.state.color.isActive ? tile.state.color.swiftUIColor : nil
    }

    private func tileColor(_ name: String) -> Color {
        switch name.lowercased() {
        case "red": return .red
        case "green": return .green
        case "blue", "light-blue": return .blue
        case "yellow", "amber": return .yellow
        case "orange", "deep-orange": return .orange
        case "cyan", "teal": return .cyan
        case "purple", "pink": return .purple
        default: return .accentColor
        }
    }
}
