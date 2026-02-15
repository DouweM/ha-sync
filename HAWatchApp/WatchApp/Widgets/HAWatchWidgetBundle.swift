import WidgetKit
import SwiftUI

@main
struct HAWatchWidgetBundle: WidgetBundle {
    var body: some Widget {
        EntityComplicationWidget()
        ControlToggleWidget()
    }
}
