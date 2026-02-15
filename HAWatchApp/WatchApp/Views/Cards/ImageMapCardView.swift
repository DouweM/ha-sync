import SwiftUI
import HAWatchCore

struct ImageMapCardView: View {
    let imageMap: RenderedImageMap
    @Environment(SettingsManager.self) private var settings
    @Environment(\.apiClient) private var sharedAPIClient
    @State private var imageData: Data?
    @State private var showFullScreen = false
    @State private var loadFailed = false

    var body: some View {
        Button {
            showFullScreen = true
        } label: {
            GeometryReader { geometry in
                let focusOffsetX: CGFloat = imageMap.focusCenterX.map { (0.5 - $0) * geometry.size.width } ?? 0
                let focusOffsetY: CGFloat = imageMap.focusCenterY.map { (0.5 - $0) * geometry.size.height } ?? 0

                ZStack {
                    Color.black // prevent grey background showing through

                    // Background image
                    if let imageData = imageData,
                       let uiImage = UIImage(data: imageData) {
                        Image(uiImage: uiImage)
                            .resizable()
                            .scaledToFill()
                            .frame(width: geometry.size.width, height: geometry.size.height)
                            .offset(x: focusOffsetX, y: focusOffsetY)
                            .clipped()
                    } else if loadFailed {
                        RoundedRectangle(cornerRadius: 8)
                            .fill(.regularMaterial)
                            .overlay {
                                VStack(spacing: 4) {
                                    Image(systemName: "map.fill")
                                        .font(.title3)
                                        .foregroundStyle(.secondary)
                                    Text("Failed to load")
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                }
                            }
                    } else {
                        RoundedRectangle(cornerRadius: 8)
                            .fill(.regularMaterial)
                            .overlay {
                                ProgressView()
                            }
                    }

                    // Entity markers at normalized positions
                    ForEach(Array(imageMap.markers.enumerated()), id: \.offset) { _, marker in
                        if let x = marker.normalizedX, let y = marker.normalizedY {
                            Group {
                                if let pictureURL = marker.entityPictureURL,
                                   !pictureURL.isEmpty,
                                   let baseURL = settings.appSettings.baseURL {
                                    EntityPictureView(
                                        url: pictureURL,
                                        baseURL: baseURL,
                                        token: settings.appSettings.accessToken,
                                        size: CGFloat(marker.size ?? 24)
                                    )
                                } else {
                                    Circle()
                                        .fill(Color.fromHAColorName(marker.colorName))
                                        .frame(width: CGFloat(marker.size ?? 24), height: CGFloat(marker.size ?? 24))
                                        .overlay {
                                            Text(String(marker.name.prefix(1)))
                                                .font(.system(size: 10, weight: .bold))
                                                .foregroundStyle(.white)
                                        }
                                }
                            }
                            .position(
                                x: x * geometry.size.width + focusOffsetX,
                                y: y * geometry.size.height + focusOffsetY
                            )
                        }
                    }

                    // Zone markers
                    ForEach(Array(imageMap.zoneMarkers.enumerated()), id: \.offset) { _, zone in
                        if let iconName = zone.iconName {
                            Image(systemName: iconName)
                                .font(.caption2)
                                .foregroundStyle(Color.fromHAColorName(zone.colorName).opacity(0.7))
                                .position(
                                    x: zone.normalizedX * geometry.size.width + focusOffsetX,
                                    y: zone.normalizedY * geometry.size.height + focusOffsetY
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
        .task {
            await loadImage()
        }
        .fullScreenCover(isPresented: $showFullScreen) {
            ImageMapFullScreenView(imageMap: imageMap, imageData: imageData)
        }
    }

    private func loadImage() async {
        guard let baseURL = settings.appSettings.baseURL else {
            loadFailed = true
            return
        }
        let client = sharedAPIClient ?? HAAPIClient(baseURL: baseURL, token: settings.appSettings.accessToken)
        do {
            let result = try await withThrowingTaskGroup(of: Data.self) { group in
                group.addTask {
                    try await client.fetchImage(path: imageMap.imageURL)
                }
                group.addTask {
                    try await Task.sleep(for: .seconds(10))
                    throw CancellationError()
                }
                let data = try await group.next()!
                group.cancelAll()
                return data
            }
            imageData = result
        } catch {
            loadFailed = true
        }
    }

}

struct ImageMapFullScreenView: View {
    let imageMap: RenderedImageMap
    let imageData: Data?
    @Environment(SettingsManager.self) private var settings
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        GeometryReader { geometry in
            ZStack {
                Color.black.ignoresSafeArea()

                if let imageData = imageData,
                   let uiImage = UIImage(data: imageData) {
                    Image(uiImage: uiImage)
                        .resizable()
                        .scaledToFit()

                    // Markers overlaid on the image
                    ForEach(Array(imageMap.markers.enumerated()), id: \.offset) { _, marker in
                        if let x = marker.normalizedX, let y = marker.normalizedY {
                            Group {
                                if let pictureURL = marker.entityPictureURL,
                                   !pictureURL.isEmpty,
                                   let baseURL = settings.appSettings.baseURL {
                                    EntityPictureView(
                                        url: pictureURL,
                                        baseURL: baseURL,
                                        token: settings.appSettings.accessToken,
                                        size: CGFloat(marker.size ?? 28)
                                    )
                                } else {
                                    Circle()
                                        .fill(Color.fromHAColorName(marker.colorName))
                                        .frame(width: CGFloat(marker.size ?? 28), height: CGFloat(marker.size ?? 28))
                                        .overlay {
                                            Text(String(marker.name.prefix(1)))
                                                .font(.system(size: 12, weight: .bold))
                                                .foregroundStyle(.white)
                                        }
                                }
                            }
                            .position(
                                x: x * geometry.size.width,
                                y: y * geometry.size.height
                            )
                        }
                    }
                } else {
                    VStack {
                        Image(systemName: "map.fill")
                            .font(.largeTitle)
                            .foregroundStyle(.secondary)
                        Text("Image Map")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
        .ignoresSafeArea()
        .onTapGesture { dismiss() }
    }
}
