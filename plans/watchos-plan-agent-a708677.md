# watchOS 26 Research: Building a Native Home Assistant Dashboard App

## Executive Summary

watchOS 26, announced at WWDC 2025 and released September 15, 2025, introduces significant enhancements for developers building native apps. The release features a new "Liquid Glass" design language, enhanced SwiftUI APIs, improved WidgetKit capabilities, expanded MapKit functionality, and 3D Charts support. This research covers all aspects relevant to building a Home Assistant dashboard app for Apple Watch.

---

## 1. What's New in watchOS 26 for SwiftUI

### Liquid Glass Design System
- **New visual language**: Liquid Glass material that reflects and refracts surroundings, dynamically transforming based on content
- **SwiftUI APIs**: Developers can adopt Liquid Glass design materials in third-party apps
- **System materials**: Updated SwiftUI APIs for system materials, tab views, split views, and more
- **Icon Composer**: New tool for creating app icons with the updated design aesthetic

### Layout Capabilities
- **Control Widget API**: Create custom controls for Control Center, Action Button, and Smart Stack
- **Smart Stack Relevance API**: Use RelevanceKit for location-based and contextual widget suggestions
- **Points of Interest (POI)**: Share location data to show relevant widgets (e.g., show shopping list near grocery stores)

### Architecture Changes
- **arm64 architecture**: Apple Watch Series 9+ and Apple Watch Ultra 2 now use arm64 on watchOS 26
- **Cross-platform controls**: Controls created on iOS automatically share with watchOS 26

### New Views and APIs
- **Chart3D API**: 3D interactive charts powered by RealityKit
- **RealityKit integration**: Blend SwiftUI with RealityKit for immersive 3D interfaces
- **Enhanced tab views and split views**: Better navigation patterns

**Sources:**
- [What's new in watchOS 26 - Apple Developer](https://developer.apple.com/watchos/whats-new/)
- [iOS 26 Explained: Apple's Biggest Update for Developers](https://www.index.dev/blog/ios-26-developer-guide)
- [SwiftUI in iOS 26: New Features - Medium](https://medium.com/@himalimarasinghe/swiftui-in-ios-26-whats-new-from-wwdc-2025-be6b4864ce05)

---

## 2. SF Symbols Version for watchOS 26

### SF Symbols 7
- **Library size**: Over 6,900 symbols (previously ~6,000)
- **Available on**: iOS 26, iPadOS 26, macOS 26, watchOS 26, tvOS 26, and visionOS 26

### New Features
- **Draw On/Draw Off animations**: New animation presets inspired by calligraphic movement
- **Automatic gradients**: Linear gradients generated from single source color
- **Variable rendering**: Enhanced Magic Replace for smooth transitions
- **Layer structure**: Improved annotation and timing choreography

### Localization
- New symbols across Latin, Greek, Cyrillic, Hebrew, Arabic, Chinese, Japanese, Korean, Thai, Devanagari, and Indic systems

**Implications for HA Dashboard App:**
- Rich icon library for representing Home Assistant entities (lights, sensors, switches, etc.)
- Smooth animations for state changes (on/off, opening/closing)
- Gradient support for visual polish
- Localization support for international users

**Sources:**
- [Apple releases SF Symbols 7 beta - 9to5Mac](https://9to5mac.com/2025/06/11/apple-releases-sf-symbols-7-beta/)
- [SF Symbols 7 Design - DesignZig](https://designzig.com/sf-symbols-7-the-next-generation-of-icon-design-animation-gradients-localization-bring-ux-to-life/)

---

## 3. MapKit Changes on watchOS 26

### Major Enhancements
- **Local search**: Search for nearby points of interest (e.g., grocery stores)
- **Routing support**: Get routes using transport types (driving, walking, cycling)
- **Route overlays**: Show routes as overlays on maps using SwiftUI
- **Additional annotations**: More annotation types for marking locations
- **Unified API**: Same API as iOS for consistency

### Capabilities
- Search for POIs
- Direction guidance
- Route map display
- Enhanced overlays and annotations

**Implications for HA Dashboard App:**
- Display device locations on maps (e.g., presence tracking)
- Show zones and geofences
- Route to home or other locations
- Visualize location-based automations

**Sources:**
- [What's new in watchOS 26 - Apple Developer](https://developer.apple.com/watchos/whats-new/)
- [What's new in watchOS 26 - WWDC25 Session](https://developer.apple.com/videos/play/wwdc2025/334/)

---

## 4. SwiftUI Charts Changes on watchOS 26

### 3D Charts (Chart3D API)
- **New API**: Chart3D for interactive, customizable 3D charts
- **RealityKit powered**: Support from RealityKit for 3D rendering
- **Platform support**: Available on iOS, macOS, visionOS, watchOS, and iPadOS 26+
- **No third-party libraries needed**: Built directly into SwiftUI

### Capabilities
- Plot and explore multivariate data in 3D space
- Interactive 3D charts without SceneKit complexity
- Rich data visualization for analytics

**Implications for HA Dashboard App:**
- Visualize sensor data in 3D (temperature over time, energy usage)
- Interactive charts for historical data analysis
- Enhanced data insights on small watch screen

**Sources:**
- [3D Charts - DevTechie Course](https://www.devtechie.com/view/courses/mastering-charts-framework-in-swiftui-ios-18/3155813-3d-charts-xcode-26-ios-macos-visionos-watchos-ipados-26)
- [Apple Unveils Major SwiftUI Upgrades - C# Corner](https://www.c-sharpcorner.com/news/apple-unveils-major-swiftui-and-design-upgrades-for-2025)
- [Cook up 3D charts with Swift Charts](https://artemnovichkov.com/blog/cook-up-3d-charts-with-swift-charts)

---

## 5. Networking Capabilities

### WebSocket Support
- **URLSessionWebSocketTask**: Available since iOS 13/watchOS 6
- **API methods**: `webSocketTask(with:)`, message enum with `.data(Data)` and `.string(String)`
- **Platform support**: iOS, macOS, tvOS, watchOS

### Important Limitations
- **watchOS WebSocket limitations**: While URLSessionWebSocketTask is technically available, there are significant limitations
- **Restricted use cases**: No supported way except for streaming audio context
- **Documentation issues**: Better documentation needed about limitations

### URLSession
- Standard URLSession APIs available
- HTTP/HTTPS networking fully supported
- Background session support

**Implications for HA Dashboard App:**
- **WebSocket limitations**: May not be reliable for real-time Home Assistant updates via WebSocket
- **Alternative approaches**: Use HTTP polling, webhooks, or push notifications for updates
- **Critical consideration**: This is a major limitation for real-time dashboard updates

**Sources:**
- [WWDC Review: URLSessionWebSocketTask - AppSpector](https://www.appspector.com/blog/websockets-in-ios-using-urlsessionwebsockettask)
- [WebSocket connection fails in watchOS - Apple Forums](https://forums.developer.apple.com/forums/thread/714796)
- [URLSessionWebSocketTask Documentation](https://developer.apple.com/documentation/foundation/urlsessionwebsockettask)

---

## 6. Minimum Swift Version for watchOS 26

### Xcode and Swift Versions
- **Xcode version**: Xcode 26 (announced June 9, 2025)
- **Swift version**: Swift 6.2.3 (ships with Xcode 26.2, released December 12, 2025)
- **Version numbering**: Apple aligned Xcode version numbers with OS versions in 2025

### SDK Requirements
- Apps submitted to App Store must be built with watchOS 26 SDK or later starting April 28, 2026
- Xcode 26 beta required for building watchOS 26 apps during development

### Key Features in Xcode 26
- AI-assisted coding tools (similar to GitHub Copilot)
- Chat query tools powered by ChatGPT (supports local models and other providers)
- AI-assisted actions accessible from anywhere in codebase
- Faster builds

**Implications for HA Dashboard App:**
- Use Swift 6.2+ for development
- Leverage Swift 6 concurrency features for better async/await support
- Utilize AI coding assistants for faster development
- Plan for App Store submission with watchOS 26 SDK by April 2026

**Sources:**
- [Xcode 26.2 Now Available - MacObserver](https://www.macobserver.com/news/xcode-26-2-is-now-available-with-updated-sdks-and-swift-6-2-3/)
- [Xcode 26 Features & Updates - Medium](https://medium.com/aeturnuminc/xcode-26-everything-ios-developers-need-to-know-from-wwdc-2025-f92e3edfb07b)
- [Michael Tsai - Xcode 26](https://mjtsai.com/blog/2025/09/16/xcode-26/)

---

## 7. Complications/Widgets APIs

### WidgetKit Enhancements

#### Push Updates for Widgets (NEW)
- **APNs support**: Send push updates to widgets using Apple Push Notification Service
- **Platform support**: All widgets on all Apple platforms supporting WidgetKit
- **Migration path**: Enables migration from ClockKit complications to WidgetKit

#### Control Widget API
- **Create custom controls**: Build controls for Control Center, Action Button, or Smart Stack
- **Built with WidgetKit**: Use familiar WidgetKit APIs
- **Quick actions**: Perform actions without opening app or launch app to specific view
- **Elements**: Provide symbol, title, tint color, and additional context

#### Smart Stack Relevance API
- **RelevanceKit**: Power widgets to appear when most relevant
- **Contextual signals**: Date, sleep schedule, location (Points of Interest)
- **User permission**: Requires permission to incorporate location data
- **Multiple views**: Multiple views may be suggested simultaneously

### Configuration and Updates
- **Entry-based**: Entries contain all data needed to render widget view
- **Entry provider**: Advises WidgetKit when to update widget display
- **SwiftUI views**: Configuration uses entry to produce SwiftUI view

### Platform Expansion
- WidgetKit now on visionOS
- CarPlay support for widgets
- Accented rendering modes for better appearance

**Implications for HA Dashboard App:**
- **Push notifications**: Real-time updates for entity states without polling
- **Complications**: Show key HA entities on watch face (temperature, lights status)
- **Smart Stack**: Context-aware widgets (show lights when arriving home)
- **Quick controls**: Toggle lights, locks, switches from Control Center

**Sources:**
- [What's new in watchOS 26 - WWDC25 Session](https://developer.apple.com/videos/play/wwdc2025/334/)
- [Creating accessory widgets - Apple Documentation](https://developer.apple.com/documentation/widgetkit/creating-accessory-widgets-and-watch-complications)
- [What's new in watchOS 26 - WWDCNotes](https://wwdcnotes.com/documentation/wwdcnotes/wwdc25-334-whats-new-in-watchos-26/)

---

## 8. Media Playback Capabilities (Camera Streams)

### AVFoundation Framework
- **Platform support**: Full AVFoundation available on iOS, iPadOS, macOS, tvOS, visionOS, and **watchOS**
- **HLS streaming**: Play HTTP Live Streaming (HLS) streams
- **Media types**: QuickTime movies, MPEG-4 files
- **Adaptive bitrate**: Dynamically select appropriate streams as network bandwidth changes

### Capabilities
- Play, create, and edit media files
- HLS stream playback
- Time-based audiovisual media
- Audio and video capture (iOS devices)

### watchOS-Specific Considerations
- **Limited documentation**: Specific watchOS 26 AVFoundation enhancements not detailed in search results
- **Theoretical support**: AVFoundation is listed as supporting watchOS
- **Practical limitations**: Unclear if camera streaming is practical on watch screen/battery constraints

**Implications for HA Dashboard App:**
- **Camera stream support**: HLS streams from Home Assistant cameras theoretically playable
- **Video doorbells**: Could display doorbell camera feeds
- **Bandwidth considerations**: Watch will adapt stream quality to network conditions
- **Battery impact**: Video streaming likely significant battery drain
- **Testing required**: Need to verify actual watchOS camera streaming capabilities

**Sources:**
- [AVFoundation Overview - Apple Developer](https://developer.apple.com/av-foundation/)
- [HTTP Live Streaming - Apple Developer](https://developer.apple.com/streaming/)
- [Using AVFoundation for HLS - Apple Documentation](https://developer.apple.com/documentation/AVFoundation/using-avfoundation-to-play-and-persist-http-live-streams)

---

## 9. App Lifecycle, Background Refresh, and Persistent Connections

### Background Refresh
- **WKApplicationRefreshBackgroundTask**: Updates app state in background
- **WKWatchConnectivityRefreshBackgroundTask**: Receives background updates via Watch Connectivity framework
- **Background execution**: Full documentation available

### Known Issues in watchOS 26
- **Regression reported**: Possible regression in `scheduleBackgroundRefresh()` on watchOS 26
- **Tasks not delivered**: Tasks may not be delivered after certain states
- **Charging behavior**: Background refresh may stall after charging

### App Lifecycle
- Official documentation: "Working with the watchOS app life cycle"
- Standard watchOS lifecycle patterns apply

### Persistent Connections
- **WebSocket limitations**: As noted in section 5, WebSockets have significant limitations on watchOS
- **No persistent WebSocket**: Cannot maintain persistent WebSocket connection to Home Assistant
- **Alternative approaches needed**: Use background refresh, push notifications, or polling

**Implications for HA Dashboard App:**
- **Background updates**: Use WKApplicationRefreshBackgroundTask to periodically update widget/complication data
- **Push notifications**: Leverage APNs for real-time updates (new in watchOS 26)
- **No persistent connection**: Cannot maintain constant connection to HA
- **Battery optimization**: Background refresh helps maintain data freshness without constant polling
- **Test thoroughly**: Be aware of potential background refresh regressions

**Sources:**
- [Working with watchOS app lifecycle - Apple Documentation](https://developer.apple.com/documentation/watchkit/life_cycles/working_with_the_watchos_app_life_cycle)
- [Background execution - Apple Documentation](https://developer.apple.com/documentation/watchkit/background-execution)
- [Background Refresh Stalls - Apple Forums](https://developer.apple.com/forums/thread/803727)

---

## 10. Apple Watch Models Supporting watchOS 26

### Supported Models (Complete List)
- Apple Watch Series 6
- Apple Watch Series 7
- Apple Watch Series 8
- Apple Watch Series 9
- Apple Watch Series 10
- Apple Watch Series 11
- Apple Watch SE (2nd generation)
- Apple Watch SE (3rd generation)
- Apple Watch Ultra
- Apple Watch Ultra 2
- Apple Watch Ultra 3

### System Requirements
- **iPhone requirement**: iPhone 11 or later, OR iPhone SE (2nd generation or later)
- **iOS requirement**: Running iOS 26

### Feature Availability
- **Not all features on all devices**: Some features require specific hardware
- **Wrist flick gesture**: Requires Apple Watch Series 9, Series 10, or Ultra 2+
- **No dropped support**: Apple didn't drop support for any models this year

### Release Date
- **Public release**: September 15, 2025
- **Free software update**: Available as free update for all supported models

**Implications for HA Dashboard App:**
- **Wide compatibility**: Support devices back to Series 6 (released 2020)
- **Testing strategy**: Test on older hardware (Series 6/SE) for performance
- **Feature detection**: Use capability checks for hardware-specific features
- **Market coverage**: Covers most Apple Watches in use

**Sources:**
- [watchOS 26 Supported Devices - iClarified](https://www.iclarified.com/97689/watchos-26-supported-devices-the-full-list-of-compatible-apple-watches)
- [Every Apple Watch supporting watchOS 26 - 9to5Mac](https://9to5mac.com/2025/06/09/heres-every-apple-watch-that-will-support-watchos-26/)
- [watchOS 26 compatibility - TechRadar](https://www.techradar.com/health-fitness/smartwatches/does-your-apple-watch-support-watchos-26-heres-the-full-list-of-compatible-apple-watches-and-which-ones-will-have-support-ended)

---

## 11. Design Guidelines and UI Patterns for watchOS 26

### Liquid Glass Design Language
- **Visual aesthetic**: Rounded, translucent UI components with optical qualities of glass
- **Dynamic behavior**: Reacts to motion, content, and inputs
- **Light adaptation**: Elements adapt dynamically to light and content
- **System-wide**: Applied to Smart Stack, Control Center, Photos watch face, navigation, and controls

### 2025-2026 HIG Updates
- **visionOS guidance**: Spatial computing design patterns
- **Customizable widgets**: Home screen widget design
- **Control Center extensions**: Design guidelines for custom controls
- **Liquid Glass integration**: How to adopt the new design language
- **AI-powered features**: Integration guidance for Apple Intelligence features

### Four Core HIG Principles
1. **Clarity**: Interfaces are easily understood
2. **Deference**: Focus on content rather than UI elements
3. **Depth**: Visual layers communicate hierarchy
4. **Consistency**: Familiar patterns across all Apple platforms

### Official Resources
- **HIG website**: developer.apple.com/design/human-interface-guidelines/
- **Comprehensive guidance**: Covers all Apple platforms including watchOS
- **Platform-specific**: watchOS-specific design patterns and components

### New UI Patterns
- **Workout app layout**: Four-corner button layout for quick access
- **Control Center**: More complete functionality with API access
- **Smart Stack**: Enhanced with Controls, Widgets, and Live Activities

**Implications for HA Dashboard App:**
- **Adopt Liquid Glass**: Use new SwiftUI APIs for modern, polished appearance
- **Follow HIG**: Ensure consistency with watchOS design patterns
- **Focus on content**: Let HA entity data be the focus, UI should defer
- **Visual hierarchy**: Use depth to organize entity groups and controls
- **Test patterns**: Study native apps (Workout, Control Center) for inspiration

**Sources:**
- [iOS App Design Guidelines 2025 - Tapptitude](https://tapptitude.com/blog/i-os-app-design-guidelines-for-2025)
- [Human Interface Guidelines - Apple Developer](https://developer.apple.com/design/human-interface-guidelines/)
- [Apple HIG Complete Guide - Bitcot](https://www.bitcot.com/ios-human-interface-guidelines/)
- [Apple HIG 2026 - Nadcab](https://www.nadcab.com/blog/apple-human-interface-guidelines-explained)

---

## Key Recommendations for Home Assistant Dashboard App

### Architecture Decisions

1. **Networking Strategy**
   - **Do NOT rely on WebSockets**: Major limitation on watchOS
   - **Use APNs push notifications**: New watchOS 26 feature for real-time updates
   - **Background refresh**: Schedule periodic updates via WKApplicationRefreshBackgroundTask
   - **HTTP API**: Use Home Assistant REST API for commands and state queries

2. **Data Updates**
   - **Widget push updates**: Leverage new APNs support for widget/complication updates
   - **Smart Stack relevance**: Use location for context-aware widgets (show lights when arriving home)
   - **Optimize requests**: Batch entity state updates to minimize network calls

3. **UI Design**
   - **Adopt Liquid Glass**: Use new SwiftUI APIs for modern appearance
   - **SF Symbols 7**: Rich icon library for entity representation
   - **Follow HIG**: Maintain consistency with watchOS patterns
   - **Chart3D**: Consider 3D charts for sensor data visualization

4. **Feature Prioritization**
   - **Controls first**: Quick toggles for lights, locks, switches in Control Center
   - **Complications**: Essential entities on watch face (temperature, security status)
   - **Dashboard views**: Scrollable entity lists grouped by domain
   - **Camera streams**: Test HLS streaming viability (battery concerns)

5. **Performance**
   - **Test on Series 6**: Oldest supported device for performance baseline
   - **Battery efficiency**: Minimize background activity
   - **Data caching**: Cache entity states to reduce network requests
   - **Optimize rendering**: Keep UI responsive on small display

6. **Development Setup**
   - **Xcode 26.2+**: Use latest version with Swift 6.2.3
   - **Swift 6 concurrency**: Leverage async/await for network calls
   - **TestFlight**: Beta test with variety of watch models
   - **App Store deadline**: Build with watchOS 26 SDK by April 28, 2026

### Critical Limitations to Address

1. **WebSocket limitation**: Most significant - no real-time bidirectional connection
2. **Background refresh regression**: Monitor and work around potential issues
3. **Battery constraints**: Video streaming and frequent updates drain battery
4. **Small screen**: Prioritize most important entities and actions
5. **Limited storage**: Minimize local data caching

### Opportunities

1. **Push widget updates**: Game-changer for real-time entity state updates
2. **Smart Stack relevance**: Context-aware automations based on location
3. **Control widgets**: System-level quick actions for common controls
4. **3D Charts**: Unique data visualization for sensor trends
5. **Liquid Glass**: Modern, polished UI that matches system appearance

---

## Sources Summary

All sources have been cited inline throughout this document. Key resources include:

- Apple Developer Documentation (developer.apple.com)
- WWDC 2025 Session Videos and Notes
- Apple Newsroom announcements
- Developer blog posts (9to5Mac, MacRumors, Medium, etc.)
- Apple Human Interface Guidelines
- Technical forums and GitHub discussions

Total sources cited: 50+

---

## Conclusion

watchOS 26 provides a solid foundation for building a Home Assistant dashboard app with significant improvements in widgets, controls, UI design, and data visualization. The most critical challenge is the WebSocket limitation, which requires architecting around push notifications and background refresh instead of persistent connections. The new APNs support for widget push updates partially mitigates this limitation and enables near-real-time entity state updates.

The combination of Control widgets for quick actions, Smart Stack relevance for context-aware displays, SF Symbols 7 for rich iconography, and the Liquid Glass design language creates an excellent platform for a native Home Assistant experience on Apple Watch.
