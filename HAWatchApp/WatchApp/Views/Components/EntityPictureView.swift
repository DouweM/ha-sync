import SwiftUI
import HAWatchCore

struct EntityPictureView: View {
    let url: String
    let baseURL: URL
    let token: String
    var size: CGFloat = 32

    @State private var imageData: Data?
    @State private var loadFailed = false

    var body: some View {
        Group {
            if let imageData = imageData,
               let uiImage = UIImage(data: imageData) {
                Image(uiImage: uiImage)
                    .resizable()
                    .scaledToFill()
                    .frame(width: size, height: size)
                    .clipShape(Circle())
            } else if loadFailed {
                Image(systemName: "person.crop.circle.fill")
                    .font(size > 28 ? .title3 : .caption)
                    .foregroundStyle(.secondary)
            } else {
                ProgressView()
                    .frame(width: size, height: size)
            }
        }
        .task {
            await loadImage()
        }
    }

    private func loadImage() async {
        let client = HAAPIClient(baseURL: baseURL, token: token)
        do {
            imageData = try await client.fetchImage(path: url)
        } catch {
            loadFailed = true
        }
    }
}
