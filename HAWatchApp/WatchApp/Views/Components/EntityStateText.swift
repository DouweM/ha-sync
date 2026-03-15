import SwiftUI
import HAWatchCore

struct EntityStateText: View {
    let state: FormattedState

    var body: some View {
        Text(state.text)
            .foregroundStyle(state.color.swiftUIColor)
    }
}

extension SemanticColor {
    var swiftUIColor: Color {
        switch self {
        case .primary: return .primary
        case .secondary: return .secondary
        case .inactive: return .secondary
        case .positive: return .green
        case .active: return .yellow
        case .warning: return .yellow
        case .danger: return .red
        case .info: return .cyan
        case .heat: return .red
        case .cool: return .blue
        }
    }
}
