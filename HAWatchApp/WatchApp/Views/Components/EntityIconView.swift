import SwiftUI
import HAWatchCore

struct EntityIconView: View {
    let sfSymbolName: String
    var color: Color?
    var size: Font = .body

    var body: some View {
        Image(systemName: sfSymbolName)
            .font(size)
            .foregroundStyle(color ?? .accentColor)
            .symbolRenderingMode(.hierarchical)
    }
}
