import SwiftUI
import Charts
import HAWatchCore

struct HistoryGraphCardView: View {
    let historyGraph: RenderedHistoryGraph

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(historyGraph.name)
                .font(.caption2)
                .foregroundStyle(.secondary)
                .padding(.horizontal, 8)

            if historyGraph.dataPoints.isEmpty {
                Text("No data")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
                    .frame(height: 60)
                    .frame(maxWidth: .infinity)
            } else {
                Chart(Array(historyGraph.dataPoints.enumerated()), id: \.offset) { _, point in
                    LineMark(
                        x: .value("Time", point.timestamp),
                        y: .value("Value", point.value)
                    )
                    .foregroundStyle(.blue)
                    .interpolationMethod(.catmullRom)

                    AreaMark(
                        x: .value("Time", point.timestamp),
                        y: .value("Value", point.value)
                    )
                    .foregroundStyle(.blue.opacity(0.1))
                    .interpolationMethod(.catmullRom)
                }
                .chartXAxis(.hidden)
                .chartYAxis {
                    AxisMarks(position: .trailing) { _ in
                        AxisValueLabel()
                            .font(.system(size: 8))
                    }
                }
                .frame(height: 60)
                .padding(.horizontal, 8)
            }
        }
        .padding(.vertical, 6)
        .glassCardBackground()
    }
}
