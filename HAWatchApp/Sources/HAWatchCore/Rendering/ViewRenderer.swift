import Foundation

/// Orchestrates the full rendering pipeline:
/// fetch states -> resolve auto-entities -> check visibility -> produce RenderedView.
public actor ViewRenderer {
    private let apiClient: HAAPIClient
    private let templateService: TemplateService
    private let stateCache: StateCache
    private let autoEntitiesResolver: AutoEntitiesResolver
    private let iconMapper: IconMapper
    private let stateFormatter: StateFormatter
    private let visibilityChecker: VisibilityChecker
    private let badgeRenderer: BadgeRenderer
    private let cardRenderer: CardRenderer
    private let sectionRenderer: SectionRenderer

    private var currentUserId: String?

    public init(apiClient: HAAPIClient) {
        self.apiClient = apiClient
        let templateService = TemplateService(apiClient: apiClient)
        let stateCache = StateCache(templateService: templateService)

        self.templateService = templateService
        self.stateCache = stateCache
        self.autoEntitiesResolver = AutoEntitiesResolver(
            templateService: templateService,
            stateCache: stateCache
        )
        self.iconMapper = .shared
        self.stateFormatter = .shared
        self.visibilityChecker = VisibilityChecker()
        self.badgeRenderer = BadgeRenderer()
        self.cardRenderer = CardRenderer()
        self.sectionRenderer = SectionRenderer()
    }

    /// Render a complete view config into a RenderedView.
    public func render(
        view: ViewConfig,
        user: String? = nil
    ) async throws -> RenderedView {
        // Resolve user ID if needed
        if let user = user {
            let userIds = try await templateService.fetchUserIds()
            currentUserId = userIds[user.lowercased()]
        }

        // Extract and fetch all entity states
        let entityIds = StateCache.extractEntityIds(from: view)
        try await stateCache.fetchStates(for: entityIds)

        // Take a snapshot of all cached states for synchronous access
        let stateSnapshot = await buildStateSnapshot(entityIds: entityIds)
        let syncStateProvider: @Sendable (String) -> EntityState? = { entityId in
            stateSnapshot[entityId]
        }

        // Render badges
        let badges = await renderBadges(
            badges: view.badges ?? [],
            stateProvider: syncStateProvider
        )

        // Render sections
        var sections: [RenderedSection] = []
        for section in view.sections ?? [] {
            if let rendered = await renderFullSection(
                section: section,
                stateProvider: syncStateProvider
            ) {
                sections.append(rendered)
            }
        }

        return RenderedView(
            title: view.title,
            path: view.path,
            badges: badges,
            sections: sections
        )
    }

    /// Refresh entity states for the current view (for polling).
    public func refreshStates() async throws {
        try await stateCache.refreshAll()
    }

    // MARK: - Private

    private func buildStateSnapshot(entityIds: Set<String>) async -> [String: EntityState] {
        var snapshot: [String: EntityState] = [:]
        for entityId in entityIds {
            if let state = await stateCache.getState(entityId) {
                snapshot[entityId] = state
            }
        }
        return snapshot
    }

    private func renderBadges(
        badges: [BadgeConfig],
        stateProvider: @Sendable (String) -> EntityState?
    ) async -> [RenderedBadge] {
        var rendered: [RenderedBadge] = []

        for badge in badges {
            let badgeType = badge.type ?? "entity"

            if badgeType == "custom:mushroom-template-badge" {
                // Evaluate templates
                var contentResult: String?
                var labelResult: String?

                if let content = badge.content {
                    contentResult = try? await templateService.evaluate(content)
                }
                if let label = badge.label {
                    labelResult = try? await templateService.evaluate(label)
                }

                if let renderedBadge = badgeRenderer.renderMushroomBadge(
                    badge: badge,
                    contentResult: contentResult,
                    labelResult: labelResult,
                    stateProvider: stateProvider,
                    currentUserId: currentUserId
                ) {
                    rendered.append(renderedBadge)
                }
            } else {
                if let renderedBadge = badgeRenderer.renderEntityBadge(
                    badge: badge,
                    stateProvider: stateProvider,
                    currentUserId: currentUserId
                ) {
                    rendered.append(renderedBadge)
                }
            }
        }

        return rendered
    }

    private func renderFullSection(
        section: SectionConfig,
        stateProvider: @Sendable (String) -> EntityState?
    ) async -> RenderedSection? {
        guard visibilityChecker.isVisible(
            conditions: section.visibility,
            stateProvider: { stateProvider($0)?.state ?? "unknown" },
            currentUserId: currentUserId
        ) else { return nil }

        let cards = section.cards ?? []
        var items: [RenderedSectionItem] = []
        var pendingHeading: CardConfig?

        for card in cards {
            if card.type == "heading", let headingText = card.heading, !headingText.isEmpty {
                let heading = await buildHeadingAsync(
                    card: card,
                    stateProvider: stateProvider
                )

                guard let heading = heading else { continue }

                if let existing = pendingHeading {
                    if let h = await buildHeadingAsync(card: existing, stateProvider: stateProvider) {
                        items.append(.spacing)
                        items.append(.heading(h))
                    }
                    pendingHeading = nil
                }

                if heading.badges.isEmpty {
                    pendingHeading = card
                } else {
                    items.append(.spacing)
                    items.append(.heading(heading))
                }
                continue
            }

            let renderedCard = await renderCardAsync(
                card: card,
                stateProvider: stateProvider
            )

            if let renderedCard = renderedCard {
                if let pending = pendingHeading {
                    if let h = await buildHeadingAsync(card: pending, stateProvider: stateProvider) {
                        items.append(.spacing)
                        items.append(.heading(h))
                    }
                    pendingHeading = nil
                }
                items.append(.card(renderedCard))
            }
        }

        guard !items.isEmpty else { return nil }
        return RenderedSection(items: items)
    }

    private func buildHeadingAsync(
        card: CardConfig,
        stateProvider: @Sendable (String) -> EntityState?
    ) async -> RenderedHeading? {
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

        var badges: [RenderedBadge] = []
        for badgeConfig in card.badges ?? [] {
            let badgeType = badgeConfig.type ?? "entity"

            if badgeType == "custom:mushroom-template-badge" {
                var contentResult: String?
                var labelResult: String?
                if let content = badgeConfig.content {
                    contentResult = try? await templateService.evaluate(content)
                }
                if let label = badgeConfig.label {
                    labelResult = try? await templateService.evaluate(label)
                }
                if let badge = badgeRenderer.renderMushroomBadge(
                    badge: badgeConfig,
                    contentResult: contentResult,
                    labelResult: labelResult,
                    stateProvider: stateProvider,
                    currentUserId: currentUserId
                ) {
                    badges.append(badge)
                }
            } else {
                if let badge = badgeRenderer.renderEntityBadge(
                    badge: badgeConfig,
                    stateProvider: stateProvider,
                    currentUserId: currentUserId
                ) {
                    badges.append(badge)
                }
            }
        }

        return RenderedHeading(
            text: text.uppercased(),
            iconName: iconName,
            badges: badges
        )
    }

    private func renderCardAsync(
        card: CardConfig,
        stateProvider: @Sendable (String) -> EntityState?
    ) async -> RenderedCard? {
        switch card.type {
        case "tile":
            return cardRenderer.renderTile(
                card: card,
                stateProvider: stateProvider,
                currentUserId: currentUserId
            )

        case "custom:auto-entities":
            guard let filter = card.filter else { return nil }
            let cardConfig = card.card
            // Skip if nested card type is map or logbook
            if let nestedType = cardConfig?.type,
               nestedType == "custom:map-card" || nestedType == "logbook" {
                return nil
            }

            let resolved = (try? await autoEntitiesResolver.resolve(filter: filter)) ?? []
            // Re-snapshot state after auto-entities resolution (new entities may have been cached)
            let freshSnapshot = await buildAutoEntitiesSnapshot(resolved: resolved, stateProvider: stateProvider)
            return cardRenderer.renderAutoEntities(
                resolvedEntities: resolved,
                stateProvider: { freshSnapshot[$0] }
            )

        case "logbook":
            return await renderLogbookCard(card: card, stateProvider: stateProvider)

        case "picture-entity":
            return cardRenderer.renderCamera(card: card, stateProvider: stateProvider)

        case "weather-forecast":
            return cardRenderer.renderWeather(card: card, stateProvider: stateProvider)

        case "history-graph":
            return cardRenderer.renderHistoryGraph(card: card, stateProvider: stateProvider)

        case "custom:map-card":
            // Map rendering requires coordinate data -- return placeholder
            return nil

        case "custom:navbar-card":
            return nil

        default:
            return nil
        }
    }

    private func buildAutoEntitiesSnapshot(
        resolved: [(entityId: String, options: AutoEntitiesOptions)],
        stateProvider: (String) -> EntityState?
    ) async -> [String: EntityState] {
        var snapshot: [String: EntityState] = [:]
        for (entityId, _) in resolved {
            if let state = await stateCache.getState(entityId) {
                snapshot[entityId] = state
            } else if let state = stateProvider(entityId) {
                snapshot[entityId] = state
            }
        }
        return snapshot
    }

    private func renderLogbookCard(
        card: CardConfig,
        stateProvider: (String) -> EntityState?
    ) async -> RenderedCard? {
        var entityIds: [String] = []
        if let target = card.target?.entityId {
            entityIds = target
        } else if let entities = card.entities {
            entityIds = entities
        }

        guard !entityIds.isEmpty else { return nil }

        // Fetch logbook data via template
        let lines = entityIds.map { eid in
            """
            \(eid)|||{{ states("\(eid)") }}|||{{ state_attr("\(eid)", "friendly_name") | default("", true) | replace("\\n", " ") }}|||{{ as_timestamp(states.\(eid).last_changed) | default(0) }}
            """
        }
        let template = lines.joined(separator: "\n")

        guard let output = try? await templateService.evaluate(template) else { return nil }

        var entries: [(Date, String, String, String)] = []
        let now = Date()

        for line in output.split(separator: "\n") {
            let parts = line.split(separator: "|||", omittingEmptySubsequences: false)
                .map { $0.trimmingCharacters(in: .whitespaces) }
            guard parts.count >= 4 else { continue }

            let entityId = parts[0]
            let state = parts[1]
            let name = parts[2].isEmpty
                ? entityId.split(separator: ".").dropFirst().joined(separator: ".").replacingOccurrences(of: "_", with: " ").capitalized
                : parts[2]
            let timestampStr = parts[3]

            guard !state.isEmpty, state != "unavailable", state != "unknown",
                  let timestamp = Double(timestampStr), timestamp > 0
            else { continue }

            let date = Date(timeIntervalSince1970: timestamp)
            entries.append((date, name, state, entityId))
        }

        entries.sort { $0.0 > $1.0 }

        let logbookEntries = entries.prefix(5).compactMap { (lastChanged, name, state, entityId) -> LogbookEntry? in
            let formatted = stateFormatter.format(
                entityId: entityId,
                state: state,
                deviceClass: stateProvider(entityId)?.deviceClass ?? ""
            )
            guard !formatted.text.isEmpty else { return nil }

            let delta = now.timeIntervalSince(lastChanged)
            let timeAgo: String
            if delta >= 86400 {
                timeAgo = "\(Int(delta / 86400))d ago"
            } else if delta >= 3600 {
                timeAgo = "\(Int(delta / 3600))h ago"
            } else if delta >= 60 {
                timeAgo = "\(Int(delta / 60))m ago"
            } else {
                timeAgo = "just now"
            }

            return LogbookEntry(name: name, state: formatted, timeAgo: timeAgo)
        }

        return cardRenderer.renderLogbook(entries: logbookEntries)
    }
}
