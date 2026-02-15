import SwiftUI
import HAWatchCore

struct BadgeView: View {
    let badge: RenderedBadge
    @Environment(SettingsManager.self) private var settings

    var body: some View {
        HStack(spacing: 4) {
            if let pictureURL = badge.entityPictureURL,
               !pictureURL.isEmpty,
               let baseURL = settings.appSettings.baseURL {
                EntityPictureView(
                    url: pictureURL,
                    baseURL: baseURL,
                    token: settings.appSettings.accessToken,
                    size: 16
                )
            } else if let iconName = badge.iconName {
                EntityIconView(sfSymbolName: iconName, size: .caption)
            }

            if badge.showName {
                Text(badge.name)
                    .font(.caption2)
                    .lineLimit(1)
            }

            if let state = badge.state {
                EntityStateText(state: state)
                    .font(.caption2)
            }
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .glassCapsuleBackground()
    }
}
