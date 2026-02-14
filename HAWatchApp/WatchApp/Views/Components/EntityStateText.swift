import SwiftUI
import HAWatchCore

struct EntityStateText: View {
    let state: FormattedState

    var body: some View {
        Text(state.text)
            .foregroundStyle(state.color.swiftUIColor)
    }
}

extension StateColor {
    var swiftUIColor: Color {
        switch self {
        case .primary: return .primary
        case .secondary: return .secondary
        case .green: return .green
        case .red: return .red
        case .yellow: return .yellow
        case .blue: return .blue
        case .cyan: return .cyan
        case .orange: return .orange
        case .dim: return .secondary
        }
    }
}
