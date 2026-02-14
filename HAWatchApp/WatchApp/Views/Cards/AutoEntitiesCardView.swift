import SwiftUI
import HAWatchCore

struct AutoEntitiesCardView: View {
    let autoEntities: RenderedAutoEntities

    var body: some View {
        VStack(spacing: 2) {
            ForEach(Array(autoEntities.tiles.enumerated()), id: \.offset) { _, tile in
                TileCardView(tile: tile)
            }
        }
    }
}
