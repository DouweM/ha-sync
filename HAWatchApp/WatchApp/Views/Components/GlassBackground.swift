import SwiftUI

/// Liquid Glass background modifier for watchOS 26+
struct GlassCardBackground: ViewModifier {
    var cornerRadius: CGFloat = 12

    func body(content: Content) -> some View {
        content
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: cornerRadius))
            .glassEffect(.regular, in: RoundedRectangle(cornerRadius: cornerRadius))
    }
}

struct GlassCapsuleBackground: ViewModifier {
    func body(content: Content) -> some View {
        content
            .background(.regularMaterial, in: Capsule())
            .glassEffect(.regular, in: Capsule())
    }
}

extension View {
    func glassCardBackground(cornerRadius: CGFloat = 12) -> some View {
        modifier(GlassCardBackground(cornerRadius: cornerRadius))
    }

    func glassCapsuleBackground() -> some View {
        modifier(GlassCapsuleBackground())
    }
}
