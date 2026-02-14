import SwiftUI
import HAWatchCore

struct CameraCardView: View {
    let camera: RenderedCamera
    @State private var showFullScreen = false

    var body: some View {
        Button {
            showFullScreen = true
        } label: {
            VStack(alignment: .leading, spacing: 4) {
                // Camera snapshot placeholder
                // In production, load via authenticated AsyncImage
                RoundedRectangle(cornerRadius: 8)
                    .fill(.ultraThinMaterial)
                    .frame(height: 100)
                    .overlay {
                        Image(systemName: "video.fill")
                            .font(.title3)
                            .foregroundStyle(.secondary)
                    }

                Text(camera.name)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            .padding(.horizontal, 8)
        }
        .buttonStyle(.plain)
        .fullScreenCover(isPresented: $showFullScreen) {
            CameraFullScreenView(camera: camera)
        }
    }
}

struct CameraFullScreenView: View {
    let camera: RenderedCamera
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            // Full-screen camera snapshot
            RoundedRectangle(cornerRadius: 0)
                .fill(.ultraThinMaterial)
                .overlay {
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
        .onTapGesture {
            dismiss()
        }
    }
}
