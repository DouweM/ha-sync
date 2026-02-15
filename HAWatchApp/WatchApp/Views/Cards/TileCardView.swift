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
