import SwiftUI

extension Color {
    /// Map a Home Assistant color name string to a SwiftUI Color.
    /// Used by tile cards, map markers, and zone overlays.
    static func fromHAColorName(_ name: String?) -> Color {
        switch name?.lowercased() {
        case "red": return .red
        case "green": return .green
        case "blue", "light-blue": return .blue
        case "yellow", "amber": return .yellow
        case "orange", "deep-orange": return .orange
        case "cyan", "teal": return .cyan
        case "purple": return .purple
        case "pink": return .pink
        default: return .accentColor
        }
    }
}
