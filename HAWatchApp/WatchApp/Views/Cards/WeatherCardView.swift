import SwiftUI
import HAWatchCore

struct WeatherCardView: View {
    let weather: RenderedWeather

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            // Current conditions
            HStack(spacing: 8) {
                Image(systemName: weather.iconName)
                    .font(.title2)
                    .symbolRenderingMode(.multicolor)

                VStack(alignment: .leading) {
                    Text(weather.temperature)
                        .font(.title3)
                        .fontWeight(.medium)
                    Text(weather.condition)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }

            // Forecast
            if !weather.forecast.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 12) {
                        ForEach(Array(weather.forecast.enumerated()), id: \.offset) { _, item in
                            VStack(spacing: 2) {
                                Text(item.day)
                                    .font(.system(size: 9))
                                    .foregroundStyle(.secondary)
                                Image(systemName: item.iconName)
                                    .font(.caption2)
                                    .symbolRenderingMode(.multicolor)
                                Text(item.tempHigh)
                                    .font(.system(size: 10))
                                if let low = item.tempLow {
                                    Text(low)
                                        .font(.system(size: 9))
                                        .foregroundStyle(.secondary)
                                }
                            }
                        }
                    }
                }
            }
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 12))
    }
}
