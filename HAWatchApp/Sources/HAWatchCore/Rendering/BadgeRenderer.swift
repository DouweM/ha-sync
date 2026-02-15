import Foundation

/// Renders badge configs into RenderedBadge output.
/// Port of render.py:508-573.
public struct BadgeRenderer: Sendable {
    private let iconMapper: IconMapper
    private let stateFormatter: StateFormatter
    private let visibilityChecker: VisibilityChecker

    public init(
        iconMapper: IconMapper = .shared,
        stateFormatter: StateFormatter = .shared,
        visibilityChecker: VisibilityChecker = VisibilityChecker()
    ) {
        self.iconMapper = iconMapper
        self.stateFormatter = stateFormatter
        self.visibilityChecker = visibilityChecker
    }

    /// Render an entity badge.
    public func renderEntityBadge(
        badge: BadgeConfig,
        stateProvider: (String) -> EntityState?,
        currentUserId: String? = nil
    ) -> RenderedBadge? {
        // Check visibility
        guard visibilityChecker.isVisible(
            conditions: badge.visibility,
            stateProvider: { stateProvider($0)?.state ?? "unknown" },
            currentUserId: currentUserId
        ) else { return nil }

        let badgeType = badge.type ?? "entity"

        if badgeType == "entity" {
            return renderPlainEntityBadge(badge: badge, stateProvider: stateProvider)
        }

        return nil
    }

    /// Render a mushroom-template-badge (requires async template evaluation).
    public func renderMushroomBadge(
        badge: BadgeConfig,
        contentResult: String?,
        labelResult: String?,
        iconResult: String? = nil,
        pictureResult: String? = nil,
        stateProvider: (String) -> EntityState?,
        currentUserId: String? = nil
    ) -> RenderedBadge? {
        guard visibilityChecker.isVisible(
            conditions: badge.visibility,
            stateProvider: { stateProvider($0)?.state ?? "unknown" },
            currentUserId: currentUserId
        ) else { return nil }

        // Use evaluated icon template if available, otherwise use static icon
        let effectiveIcon: String?
        if let evaluated = iconResult, !evaluated.isEmpty {
            effectiveIcon = evaluated
        } else if let icon = badge.icon, !icon.contains("{") {
            effectiveIcon = icon
        } else {
            effectiveIcon = badge.icon
        }

        let iconName = iconMapper.sfSymbolName(
            for: effectiveIcon,
            entityId: badge.entity
        )

        var name = ""
        var state: FormattedState?

        if let content = contentResult, !content.isEmpty {
            name = content
            let color: StateColor
            // Use explicit badge color if provided
            if let badgeColor = badge.color?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(),
               !badgeColor.isEmpty {
                color = stateColorFromString(badgeColor)
            } else {
                let lower = content.lowercased()
                if lower == "home" || lower == "oasis" {
                    color = .green
                } else if lower == "away" || lower == "not_home" {
                    color = .dim
                } else {
                    color = .cyan
                }
            }
            state = FormattedState(text: content, color: color)
        }

        if let labelText = labelResult, !labelText.isEmpty {
            if name.isEmpty {
                name = labelText
            }
        }

        guard !name.isEmpty else { return nil }

        // Resolve picture URL from template evaluation
        let pictureURL: String?
        if let evaluated = pictureResult, !evaluated.isEmpty {
            pictureURL = evaluated
        } else {
            pictureURL = nil
        }

        return RenderedBadge(
            iconName: iconName,
            name: name,
            state: state,
            entityId: badge.entity,
            entityPictureURL: pictureURL
        )
    }

    private func stateColorFromString(_ color: String) -> StateColor {
        switch color {
        case "red": return .red
        case "green": return .green
        case "blue", "light-blue": return .blue
        case "yellow", "amber": return .yellow
        case "orange", "deep-orange": return .orange
        case "cyan", "teal": return .cyan
        case "purple", "pink": return .cyan
        case "grey", "dark-grey", "blue-grey", "brown", "indigo": return .dim
        default: return .cyan
        }
    }

    private func renderPlainEntityBadge(
        badge: BadgeConfig,
        stateProvider: (String) -> EntityState?
    ) -> RenderedBadge? {
        guard let entityId = badge.entity else { return nil }
        guard let entityState = stateProvider(entityId) else { return nil }

        let showIcon = badge.showIcon ?? true
        let showState = badge.showState ?? true

        let iconName: String? = showIcon ? iconMapper.sfSymbolName(
            for: badge.icon ?? entityState.icon,
            entityId: entityId,
            deviceClass: entityState.deviceClass
        ) : nil

        let displayName = badge.name ?? entityState.displayName

        var formatted: FormattedState?
        if !(badge.stateContent?.isName ?? false) && showState {
            formatted = stateFormatter.format(
                entityId: entityId,
                state: entityState.state,
                deviceClass: entityState.deviceClass,
                unit: entityState.unit
            )
            if formatted?.text.isEmpty == true {
                formatted = nil
            }
        }

        guard !displayName.isEmpty || formatted != nil else { return nil }

        return RenderedBadge(
            iconName: iconName,
            name: displayName,
            state: formatted,
            entityId: entityId
        )
    }
}
