import SwiftUI
import HAWatchCore

struct EntityPictureView: View {
    let url: String
    let baseURL: URL
    let token: String
    var size: CGFloat = 32

    var body: some View {
        AsyncImage(url: resolvedURL) { phase in
            switch phase {
            case .success(let image):
                image
                    .resizable()
                    .scaledToFill()
                    .frame(width: size, height: size)
                    .clipShape(Circle())

            case .failure:
                Image(systemName: "person.crop.circle.fill")
                    .font(.title3)
                    .foregroundStyle(.secondary)

            case .empty:
                ProgressView()
                    .frame(width: size, height: size)

            @unknown default:
                EmptyView()
            }
        }
    }

    private var resolvedURL: URL? {
        if url.hasPrefix("http") {
            return URL(string: url)
        }
        return baseURL.appendingPathComponent(url)
    }
}
