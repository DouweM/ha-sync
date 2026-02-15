import SwiftUI
import HAWatchCore

struct ViewPageView: View {
    @Bindable var viewModel: DashboardViewModel
    let dashboardId: String?

    var body: some View {
        Group {
            if viewModel.isLoading && viewModel.renderedViews.isEmpty {
                ProgressView("Loading...")
            } else if viewModel.renderedViews.isEmpty {
                Text("No views")
                    .foregroundStyle(.secondary)
            } else {
                TabView(selection: $viewModel.selectedViewIndex) {
                    ForEach(Array(viewModel.renderedViews.enumerated()), id: \.offset) { index, renderedView in
                        SingleViewPage(renderedView: renderedView)
                            .tag(index)
                    }
                }
                .tabViewStyle(.verticalPage)
            }
        }
        .navigationTitle(viewModel.renderedViews.isEmpty ? "Loading" : (viewModel.renderedViews[safe: viewModel.selectedViewIndex]?.title ?? ""))
        .task {
            if viewModel.renderedViews.isEmpty {
                await viewModel.loadDashboard(id: dashboardId)
            }
            viewModel.startPolling()
        }
        .onDisappear {
            viewModel.stopPolling()
        }
    }
}

struct SingleViewPage: View {
    let renderedView: RenderedView

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 4) {
                // Badges
                if !renderedView.badges.isEmpty {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 8) {
                            ForEach(Array(renderedView.badges.enumerated()), id: \.offset) { _, badge in
                                BadgeView(badge: badge)
                            }
                        }
                        .padding(.horizontal)
                    }
                    .padding(.bottom, 4)
                }

                // Sections
                ForEach(Array(renderedView.sections.enumerated()), id: \.offset) { _, section in
                    SectionView(section: section)
                }
            }
            .padding(.vertical, 4)
        }
    }
}

struct SectionView: View {
    let section: RenderedSection

    /// Group consecutive half-width cards into pairs for side-by-side rendering
    private var groupedItems: [SectionItemGroup] {
        var groups: [SectionItemGroup] = []
        var pendingHalfCard: RenderedCard?

        for item in section.items {
            switch item {
            case .heading(let heading):
                if let pending = pendingHalfCard {
                    groups.append(.singleCard(pending))
                    pendingHalfCard = nil
                }
                groups.append(.heading(heading))

            case .card(let card):
                if card.isHalfWidth {
                    if let first = pendingHalfCard {
                        groups.append(.pairedCards(first, card))
                        pendingHalfCard = nil
                    } else {
                        pendingHalfCard = card
                    }
                } else {
                    if let pending = pendingHalfCard {
                        groups.append(.singleCard(pending))
                        pendingHalfCard = nil
                    }
                    groups.append(.singleCard(card))
                }

            case .spacing:
                if let pending = pendingHalfCard {
                    groups.append(.singleCard(pending))
                    pendingHalfCard = nil
                }
                groups.append(.spacing)
            }
        }

        if let pending = pendingHalfCard {
            groups.append(.singleCard(pending))
        }

        return groups
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            ForEach(Array(groupedItems.enumerated()), id: \.offset) { _, group in
                switch group {
                case .heading(let heading):
                    HeadingCardView(heading: heading)

                case .singleCard(let card):
                    CardFactory.makeView(for: card)

                case .pairedCards(let left, let right):
                    HStack(spacing: 2) {
                        CardFactory.makeView(for: left)
                        CardFactory.makeView(for: right)
                    }

                case .spacing:
                    Spacer()
                        .frame(height: 8)
                }
            }
        }
    }
}

private enum SectionItemGroup {
    case heading(RenderedHeading)
    case singleCard(RenderedCard)
    case pairedCards(RenderedCard, RenderedCard)
    case spacing
}

// Safe array subscript
extension Array {
    subscript(safe index: Index) -> Element? {
        indices.contains(index) ? self[index] : nil
    }
}
