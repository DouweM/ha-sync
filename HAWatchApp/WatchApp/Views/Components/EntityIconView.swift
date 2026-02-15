import SwiftUI
import HAWatchCore

struct EntityIconView: View {
    let sfSymbolName: String
    var color: Color?
    var size: Font = .body

    var body: some View {
        Image(systemName: sfSymbolName)
            .font(size)
            .frame(width: size == .body ? 20 : 14)
            .foregroundStyle(color ?? .accentColor)
            .symbolRenderingMode(.hierarchical)
            .contentTransition(.symbolEffect(.replace))
    }
}
