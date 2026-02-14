import SwiftUI
import HAWatchCore

enum CardFactory {
    @ViewBuilder
    static func makeView(for card: RenderedCard) -> some View {
        switch card {
        case .tile(let tile):
            TileCardView(tile: tile)

        case .autoEntities(let autoEntities):
            AutoEntitiesCardView(autoEntities: autoEntities)

        case .logbook(let logbook):
            LogbookCardView(logbook: logbook)

        case .weather(let weather):
            WeatherCardView(weather: weather)

        case .camera(let camera):
            CameraCardView(camera: camera)

        case .imageMap(let imageMap):
            ImageMapCardView(imageMap: imageMap)

        case .nativeMap(let nativeMap):
            MapKitCardView(nativeMap: nativeMap)

        case .historyGraph(let historyGraph):
            HistoryGraphCardView(historyGraph: historyGraph)
        }
    }
}
