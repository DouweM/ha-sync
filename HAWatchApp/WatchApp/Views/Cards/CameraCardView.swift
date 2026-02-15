import SwiftUI
import HAWatchCore

struct CameraCardView: View {
    let camera: RenderedCamera
    @Environment(SettingsManager.self) private var settings
    @State private var snapshotData: Data?
    @State private var showFullScreen = false

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
                } else {
                    RoundedRectangle(cornerRadius: 8)
                        .fill(.ultraThinMaterial)
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
        guard let baseURL = settings.appSettings.baseURL else { return }
        let client = HAAPIClient(baseURL: baseURL, token: settings.appSettings.accessToken)
        snapshotData = try? await client.fetchCameraSnapshot(entityId: camera.entityId)
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
