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

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            ForEach(Array(section.items.enumerated()), id: \.offset) { _, item in
                switch item {
                case .heading(let heading):
                    HeadingCardView(heading: heading)

                case .card(let card):
                    CardFactory.makeView(for: card)

                case .spacing:
                    Spacer()
                        .frame(height: 8)
                }
            }
        }
    }
}

// Safe array subscript
extension Array {
    subscript(safe index: Index) -> Element? {
        indices.contains(index) ? self[index] : nil
    }
}
