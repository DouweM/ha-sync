import Foundation

/// Renders section configs into RenderedSection output.
/// Implements the pending-heading logic from render.py:891-926.
public struct SectionRenderer: Sendable {
    private let iconMapper: IconMapper
    private let badgeRenderer: BadgeRenderer
    private let cardRenderer: CardRenderer
    private let visibilityChecker: VisibilityChecker

    public init(
        iconMapper: IconMapper = .shared,
        badgeRenderer: BadgeRenderer = BadgeRenderer(),
        cardRenderer: CardRenderer = CardRenderer(),
        visibilityChecker: VisibilityChecker = VisibilityChecker()
    ) {
        self.iconMapper = iconMapper
        self.badgeRenderer = badgeRenderer
        self.cardRenderer = cardRenderer
        self.visibilityChecker = visibilityChecker
    }

    /// Render a section synchronously (for non-template badges and non-auto-entities cards).
    /// For sections that contain auto-entities or mushroom badges, use renderSectionAsync.
    public func renderSection(
        section: SectionConfig,
        stateProvider: (String) -> EntityState?,
        currentUserId: String? = nil
    ) -> RenderedSection? {
        guard visibilityChecker.isVisible(
            conditions: section.visibility,
            stateProvider: { stateProvider($0)?.state ?? "unknown" },
            currentUserId: currentUserId
        ) else { return nil }

        let cards = section.cards ?? []
        var items: [RenderedSectionItem] = []
        var pendingHeading: CardConfig?

        for card in cards {
            let cardType = card.type

            if cardType == "heading", let headingText = card.heading, !headingText.isEmpty {
                let heading = buildHeading(
                    card: card,
                    stateProvider: stateProvider,
                    currentUserId: currentUserId
                )

                guard let heading = heading else { continue }

                if let existingPending = pendingHeading {
                    // Emit the existing pending heading
                    if let existingHeading = buildHeading(
                        card: existingPending,
                        stateProvider: stateProvider,
                        currentUserId: currentUserId
                    ) {
                        items.append(.spacing)
                        items.append(.heading(existingHeading))
                    }
                    pendingHeading = nil
                }

                if heading.badges.isEmpty {
                    // Hold heading -- only emit when content follows
                    pendingHeading = card
                } else {
                    // Heading with badges -- emit immediately
                    items.append(.spacing)
                    items.append(.heading(heading))
                }
                continue
            }

            // Non-heading card
            let renderedCard = renderCardByType(
                card: card,
                stateProvider: stateProvider,
                currentUserId: currentUserId
            )

            if let renderedCard = renderedCard {
                // Emit pending heading before content
                if let pending = pendingHeading {
                    if let heading = buildHeading(
                        card: pending,
                        stateProvider: stateProvider,
                        currentUserId: currentUserId
                    ) {
                        items.append(.spacing)
                        items.append(.heading(heading))
                    }
                    pendingHeading = nil
                }
                items.append(.card(renderedCard))
            }
        }

        guard !items.isEmpty else { return nil }
        return RenderedSection(items: items)
    }

    private func buildHeading(
        card: CardConfig,
        stateProvider: (String) -> EntityState?,
        currentUserId: String?
    ) -> RenderedHeading? {
        guard visibilityChecker.isVisible(
            conditions: card.visibility,
            stateProvider: { stateProvider($0)?.state ?? "unknown" },
            currentUserId: currentUserId
        ) else { return nil }

        guard let text = card.heading, !text.isEmpty else { return nil }

        let iconName: String?
        if let icon = card.icon, !icon.isEmpty {
            iconName = iconMapper.sfSymbolName(for: icon)
        } else {
            iconName = nil
        }

        let badges: [RenderedBadge] = (card.badges ?? []).compactMap { badgeConfig in
            badgeRenderer.renderEntityBadge(
                badge: badgeConfig,
                stateProvider: stateProvider,
                currentUserId: currentUserId
            )
        }

        return RenderedHeading(
            text: text,
            iconName: iconName,
            badges: badges
        )
    }

    private func renderCardByType(
        card: CardConfig,
        stateProvider: (String) -> EntityState?,
        currentUserId: String?
    ) -> RenderedCard? {
        switch card.type {
        case "tile":
            return cardRenderer.renderTile(
                card: card,
                stateProvider: stateProvider,
                currentUserId: currentUserId
            )

        case "heading":
            return nil  // Handled separately

        case "picture-entity":
            return cardRenderer.renderCamera(
                card: card,
                stateProvider: stateProvider
            )

        case "weather-forecast":
            return cardRenderer.renderWeather(
                card: card,
                stateProvider: stateProvider
            )

        case "history-graph":
            return cardRenderer.renderHistoryGraph(
                card: card,
                stateProvider: stateProvider
            )

        case "custom:auto-entities":
            // Auto-entities requires async resolution -- skip in sync render
            return nil

        case "logbook":
            // Logbook requires async data fetch -- skip in sync render
            return nil

        case "custom:map-card":
            // Map requires async data fetch -- skip in sync render
            return nil

        case "custom:navbar-card":
            return nil  // Not meaningful on watch

        default:
            return nil
        }
    }
}
