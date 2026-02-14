import SwiftUI
import MapKit
import HAWatchCore

struct MapKitCardView: View {
    let nativeMap: RenderedNativeMap
    @State private var showFullScreen = false

    var body: some View {
        Button {
            showFullScreen = true
        } label: {
            Map(initialPosition: .region(MKCoordinateRegion(
                center: CLLocationCoordinate2D(
                    latitude: nativeMap.centerLatitude,
                    longitude: nativeMap.centerLongitude
                ),
                span: MKCoordinateSpan(latitudeDelta: 0.01, longitudeDelta: 0.01)
            ))) {
                ForEach(Array(nativeMap.markers.enumerated()), id: \.offset) { _, marker in
                    Annotation(marker.name, coordinate: CLLocationCoordinate2D(
                        latitude: marker.latitude,
                        longitude: marker.longitude
                    )) {
                        Circle()
                            .fill(.blue)
                            .frame(width: 12, height: 12)
                            .overlay {
                                Text(String(marker.name.prefix(1)))
                                    .font(.system(size: 8, weight: .bold))
                                    .foregroundStyle(.white)
                            }
                    }
                }
            }
            .mapStyle(nativeMap.useSatellite ? .imagery : .standard)
            .frame(height: 120)
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .allowsHitTesting(false)
            .padding(.horizontal, 8)
        }
        .buttonStyle(.plain)
        .fullScreenCover(isPresented: $showFullScreen) {
            MapFullScreenView(nativeMap: nativeMap)
        }
    }
}

struct MapFullScreenView: View {
    let nativeMap: RenderedNativeMap
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        Map(initialPosition: .region(MKCoordinateRegion(
            center: CLLocationCoordinate2D(
                latitude: nativeMap.centerLatitude,
                longitude: nativeMap.centerLongitude
            ),
            span: MKCoordinateSpan(latitudeDelta: 0.005, longitudeDelta: 0.005)
        ))) {
            ForEach(Array(nativeMap.markers.enumerated()), id: \.offset) { _, marker in
                Annotation(marker.name, coordinate: CLLocationCoordinate2D(
                    latitude: marker.latitude,
                    longitude: marker.longitude
                )) {
                    Circle()
                        .fill(.blue)
                        .frame(width: 16, height: 16)
                        .overlay {
                            Text(String(marker.name.prefix(1)))
                                .font(.system(size: 10, weight: .bold))
                                .foregroundStyle(.white)
                        }
                }
            }

            ForEach(Array(nativeMap.zones.enumerated()), id: \.offset) { _, zone in
                MapCircle(
                    center: CLLocationCoordinate2D(
                        latitude: zone.latitude,
                        longitude: zone.longitude
                    ),
                    radius: zone.radius
                )
                .foregroundStyle(.blue.opacity(0.15))
                .stroke(.blue.opacity(0.5), lineWidth: 1)
            }
        }
        .mapStyle(nativeMap.useSatellite ? .imagery : .standard)
        .ignoresSafeArea()
        .onTapGesture { dismiss() }
    }
}
