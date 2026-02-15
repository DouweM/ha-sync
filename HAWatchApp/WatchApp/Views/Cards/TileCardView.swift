import SwiftUI
import HAWatchCore

struct TileCardView: View {
    let tile: RenderedTile
    var viewModel: DashboardViewModel?
    @Environment(SettingsManager.self) private var settings
    @State private var isTapped = false

    private var isToggleable: Bool {
        let domain = tile.entityId.split(separator: ".").first.map(String.init) ?? ""
        let toggleableDomains: Set<String> = [
            "light", "switch", "fan", "input_boolean", "lock",
            "cover", "climate", "script", "scene", "automation"
        ]
        return toggleableDomains.contains(domain)
    }

    var body: some View {
        if isToggleable {
            Button {
                #if canImport(WatchKit)
                WKInterfaceDevice.current().play(.click)
                #endif
                isTapped.toggle()
                Task {
                    await viewModel?.toggleEntity(entityId: tile.entityId)
                }
            } label: {
                tileContent
            }
            .buttonStyle(.plain)
        } else {
            tileContent
        }
    }

    private var tileContent: some View {
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
                .symbolEffect(.bounce, value: isTapped)
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
        .glassCardBackground()
    }

    private var tileIconColor: Color? {
        if let colorName = tile.colorName {
            return .fromHAColorName(colorName)
        }
        return tile.state.color.isActive ? tile.state.color.swiftUIColor : nil
    }
}
