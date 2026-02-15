import SwiftUI
import HAWatchCore

struct CameraCardView: View {
    let camera: RenderedCamera
    @Environment(SettingsManager.self) private var settings
    @State private var snapshotData: Data?
    @State private var showFullScreen = false
    @State private var loadFailed = false

    var body: some View {
        Button {
            showFullScreen = true
        } label: {
            VStack(alignment: .leading, spacing: 4) {
                if let snapshotData = snapshotData,
                   let uiImage = UIImage(data: snapshotData) {
                    Image(uiImage: uiImage)
                        .resizable()
                        .scaledToFill()
                        .frame(height: 100)
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                } else if loadFailed {
                    RoundedRectangle(cornerRadius: 8)
                        .fill(.regularMaterial)
                        .frame(height: 100)
                        .overlay {
                            VStack(spacing: 4) {
                                Image(systemName: "video.slash.fill")
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
                        .frame(height: 100)
                        .overlay {
                            ProgressView()
                        }
                }

                Text(camera.name)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            .padding(.horizontal, 8)
        }
        .buttonStyle(.plain)
        .task {
            await loadSnapshot()
        }
        .fullScreenCover(isPresented: $showFullScreen) {
            CameraFullScreenView(camera: camera, snapshotData: snapshotData)
        }
    }

    private func loadSnapshot() async {
        guard let baseURL = settings.appSettings.baseURL else {
            loadFailed = true
            return
        }
        let client = HAAPIClient(baseURL: baseURL, token: settings.appSettings.accessToken)
        do {
            let result = try await withThrowingTaskGroup(of: Data.self) { group in
                group.addTask {
                    try await client.fetchCameraSnapshot(entityId: camera.entityId)
                }
                group.addTask {
                    try await Task.sleep(for: .seconds(10))
                    throw CancellationError()
                }
                let data = try await group.next()!
                group.cancelAll()
                return data
            }
            snapshotData = result
        } catch {
            loadFailed = true
        }
    }
}

struct CameraFullScreenView: View {
    let camera: RenderedCamera
    let snapshotData: Data?
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            if let snapshotData = snapshotData,
               let uiImage = UIImage(data: snapshotData) {
                Image(uiImage: uiImage)
                    .resizable()
                    .scaledToFit()
            } else {
                VStack {
                    Image(systemName: "video.fill")
                        .font(.largeTitle)
                        .foregroundStyle(.secondary)
                    Text(camera.name)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .ignoresSafeArea()
        .onTapGesture {
            dismiss()
        }
    }
}
