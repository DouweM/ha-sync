import SwiftUI
import HAWatchCore

struct ImageMapCardView: View {
    let imageMap: RenderedImageMap
    @State private var showFullScreen = false

    var body: some View {
        Button {
            showFullScreen = true
        } label: {
            GeometryReader { geometry in
                ZStack {
                    // Background image (loaded via authenticated URL)
                    RoundedRectangle(cornerRadius: 8)
                        .fill(.ultraThinMaterial)

                    // Entity markers at normalized positions
                    ForEach(Array(imageMap.markers.enumerated()), id: \.offset) { _, marker in
                        if let x = marker.normalizedX, let y = marker.normalizedY {
                            Circle()
                                .fill(markerColor(marker.colorName))
                                .frame(width: CGFloat(marker.size ?? 24), height: CGFloat(marker.size ?? 24))
                                .overlay {
                                    Text(String(marker.name.prefix(1)))
                                        .font(.system(size: 10, weight: .bold))
                                        .foregroundStyle(.white)
                                }
                                .position(
                                    x: x * geometry.size.width,
                                    y: y * geometry.size.height
                                )
                        }
                    }

                    // Zone markers
                    ForEach(Array(imageMap.zoneMarkers.enumerated()), id: \.offset) { _, zone in
                        if let iconName = zone.iconName {
                            Image(systemName: iconName)
                                .font(.caption2)
                                .foregroundStyle(markerColor(zone.colorName).opacity(0.7))
                                .position(
                                    x: zone.normalizedX * geometry.size.width,
                                    y: zone.normalizedY * geometry.size.height
                                )
                        }
                    }
                }
            }
            .frame(height: 120)
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .padding(.horizontal, 8)
        }
        .buttonStyle(.plain)
        .fullScreenCover(isPresented: $showFullScreen) {
            ImageMapFullScreenView(imageMap: imageMap)
        }
    }

    private func markerColor(_ name: String?) -> Color {
        switch name?.lowercased() {
        case "red": return .red
        case "blue": return .blue
        case "green": return .green
        case "yellow": return .yellow
        case "orange": return .orange
        case "purple": return .purple
        case "pink": return .pink
        default: return .accentColor
        }
    }
}

struct ImageMapFullScreenView: View {
    let imageMap: RenderedImageMap
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            Text("Map")
                .foregroundStyle(.secondary)
        }
        .onTapGesture { dismiss() }
    }
}
