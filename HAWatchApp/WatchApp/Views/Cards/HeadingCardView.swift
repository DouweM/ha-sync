import SwiftUI
import HAWatchCore

struct HeadingCardView: View {
    let heading: RenderedHeading

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 4) {
                if let iconName = heading.iconName {
                    EntityIconView(sfSymbolName: iconName, size: .caption)
                }
                Text(heading.text)
                    .font(.caption)
                    .fontWeight(.bold)
                    .foregroundStyle(.secondary)
                    .textCase(.uppercase)
            }
            .padding(.horizontal, 8)

            if !heading.badges.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 6) {
                        ForEach(Array(heading.badges.enumerated()), id: \.offset) { _, badge in
                            BadgeView(badge: badge)
                        }
                    }
                    .padding(.horizontal, 8)
                }
            }
        }
        .padding(.top, 4)
    }
}
