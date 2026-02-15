import SwiftUI
import MapKit
import HAWatchCore

struct MapKitCardView: View {
    let nativeMap: RenderedNativeMap
    @Environment(SettingsManager.self) private var settings
    @State private var showFullScreen = false

    var body: some View {
        Button {
            showFullScreen = true
        } label: {
            Map(initialPosition: .region(MKCoordinateRegion(
                center: CLLocationCoordinate2D(
                    latitude: nativeMap.effectiveCenterLatitude,
                    longitude: nativeMap.effectiveCenterLongitude
                ),
                span: MKCoordinateSpan(latitudeDelta: 0.01, longitudeDelta: 0.01)
            ))) {
                ForEach(Array(nativeMap.markers.enumerated()), id: \.offset) { _, marker in
                    Annotation(marker.name, coordinate: CLLocationCoordinate2D(
                        latitude: marker.latitude,
                        longitude: marker.longitude
                    )) {
                        if let pictureURL = marker.entityPictureURL,
                           !pictureURL.isEmpty,
                           let baseURL = settings.appSettings.baseURL {
                            EntityPictureView(
                                url: pictureURL,
                                baseURL: baseURL,
                                token: settings.appSettings.accessToken,
                                size: 16
                            )
                        } else {
                            Circle()
                                .fill(Color.fromHAColorName(marker.colorName))
                                .frame(width: 12, height: 12)
                                .overlay {
                                    Text(String(marker.name.prefix(1)))
                                        .font(.system(size: 8, weight: .bold))
                                        .foregroundStyle(.white)
                                }
                        }
                    }
                }

                ForEach(Array(nativeMap.zones.enumerated()), id: \.offset) { _, zone in
                    let zoneColor = Color.fromHAColorName(zone.colorName)
                    MapCircle(
                        center: CLLocationCoordinate2D(
                            latitude: zone.latitude,
                            longitude: zone.longitude
                        ),
                        radius: zone.radius
                    )
                    .foregroundStyle(zoneColor.opacity(0.15))
                    .stroke(zoneColor.opacity(0.5), lineWidth: 1)
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
    @Environment(SettingsManager.self) private var settings
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        Map(initialPosition: .region(MKCoordinateRegion(
            center: CLLocationCoordinate2D(
                latitude: nativeMap.effectiveCenterLatitude,
                longitude: nativeMap.effectiveCenterLongitude
            ),
            span: MKCoordinateSpan(latitudeDelta: 0.005, longitudeDelta: 0.005)
        ))) {
            ForEach(Array(nativeMap.markers.enumerated()), id: \.offset) { _, marker in
                Annotation(marker.name, coordinate: CLLocationCoordinate2D(
                    latitude: marker.latitude,
                    longitude: marker.longitude
                )) {
                    if let pictureURL = marker.entityPictureURL,
                       !pictureURL.isEmpty,
                       let baseURL = settings.appSettings.baseURL {
                        EntityPictureView(
                            url: pictureURL,
                            baseURL: baseURL,
                            token: settings.appSettings.accessToken,
                            size: 16
                        )
                    } else {
                        Circle()
                            .fill(Color.fromHAColorName(marker.colorName))
                            .frame(width: 16, height: 16)
                            .overlay {
                                Text(String(marker.name.prefix(1)))
                                    .font(.system(size: 10, weight: .bold))
                                    .foregroundStyle(.white)
                            }
                    }
                }
            }

            ForEach(Array(nativeMap.zones.enumerated()), id: \.offset) { _, zone in
                let zoneColor = Color.fromHAColorName(zone.colorName)
                MapCircle(
                    center: CLLocationCoordinate2D(
                        latitude: zone.latitude,
                        longitude: zone.longitude
                    ),
                    radius: zone.radius
                )
                .foregroundStyle(zoneColor.opacity(0.15))
                .stroke(zoneColor.opacity(0.5), lineWidth: 1)
            }
        }
        .mapStyle(nativeMap.useSatellite ? .imagery : .standard)
        .ignoresSafeArea()
        .onTapGesture { dismiss() }
    }
}
