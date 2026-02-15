# watchOS 26 Complications & Widgets Research for Home Assistant Dashboard App

## Executive Summary

This research covers watchOS 26 complications, WidgetKit integration, and iPhone companion app patterns for building a Home Assistant dashboard app. Key findings:

- **watchOS 26** introduced major improvements: push updates via APNs, third-party Control Center widgets, and enhanced Smart Stack
- **Complications** use WidgetKit (not ClockKit) with multiple families supporting dynamic text, numbers, and SF Symbols
- **Refresh rates** are system-controlled (~15 mins for widgets, ~10-15 mins for complications), but push updates enable real-time data
- **Configuration** uses AppIntent with entity selection
- **Data sync** between iPhone/Watch uses WatchConnectivity (not App Groups)

---

## 1. Complication Families in watchOS 26

### Available Families

Starting in watchOS 9 (continued in watchOS 26), complications are organized into several families:

- **Circular/Corner**: Positioned around watch face edges, ideal for compact data (battery, date, status)
- **Rectangular**: Large rectangular space for charts, multiple text lines, rich data display
- **Inline**: Text-only slot appearing on many faces (accessoryInline family)
- **Accessory families** (iOS 16/watchOS 9+):
  - `accessoryCircular`: Small circular widgets
  - `accessoryRectangular`: Multiple lines of text or small graphs
  - `accessoryCorner`: watchOS-specific, mixes small circle content with gauges and text
  - `accessoryInline`: Text-only, various sizes

### Complication Support by Face

- Support varies significantly: 0 to 8 complications per face
- Infograph and Modular Ultra support up to 8
- Minimalist faces (Flow, Artist, Flux) have zero complication support
- watchOS 26 includes 67 watch faces total (4 new: Exactograph, Flow, Faubourg)

**Sources:**
- [Every watchOS 26 Face: Complete Guide](https://the5krunner.com/2025/11/03/watchos-26-apple-watch-faces-guide/)
- [Apple HIG: Complications](https://developers.apple.com/design/human-interface-guidelines/components/system-experiences/complications/)

---

## 2. WidgetKit Integration on watchOS 26

### WidgetKit Overview

- Complications have been **reimagined with WidgetKit** since watchOS 9, replacing ClockKit
- WidgetKit embraces SwiftUI and allows code sharing between iOS Home Screen widgets and watchOS complications
- Write once, deploy across iOS and watchOS platforms

### Key Improvements in watchOS 26

**Push Updates via APNs:**
- NEW in watchOS 26: Send push updates to widgets using APNs
- Widget push updates supported on all WidgetKit platforms
- Server can send push notification to APNs → WidgetKit reloads widgets
- Critical for real-time Home Assistant sensor updates

**Smart Stack Relevance:**
- Relevant widgets appear in Smart Stack when contextually appropriate (routine, location, time)
- Multiple instances can show simultaneously (e.g., overlapping calendar events)

**Update Methods:**
- Timelines: Good for regularly updating data
- App-driven changes: Use `reloadAllTimelines()`
- External/server changes: Use push updates via APNs

**Sources:**
- [What's new in watchOS 26 - WWDC25](https://developer.apple.com/videos/play/wwdc2025/334/)
- [What's new in widgets - WWDC25](https://developer.apple.com/videos/play/wwdc2025/278/)
- [Complications and widgets: Reloaded](https://wwdcnotes.com/documentation/wwdcnotes/wwdc22-10050-complications-and-widgets-reloaded/)

---

## 3. Dynamic Text/Numbers in Complications

### Yes - Full Support

Complications can display **dynamic text and numbers** (e.g., "23°C" from sensor entities):

- **Text API** is family-aware: default font size changes per complication family
- **Date formatters** work great on watch faces with relative, offset, and timer styles
- Formatters are automatically kept up-to-date by the watch face
- Support for multiple lines of text in rectangular families
- Gauges and progress indicators available

### Implementation

- Use SwiftUI `Text` views with dynamic data
- WidgetKit timeline provides entries at specific intervals
- Combine with push updates for real-time sensor data

**Sources:**
- [Go further with Complications in WidgetKit - WWDC22](https://developer.apple.com/videos/play/wwdc2022/10051/)
- [Creating accessory widgets and watch complications](https://developer.apple.com/documentation/widgetkit/creating-accessory-widgets-and-watch-complications)

---

## 4. SF Symbols Support

### Yes - Full Support

SF Symbols work well in complications:

- **Thoughtful iconography** helps distinguish your widget/app
- SF Symbols commonly used in front of widgets to represent content type
- Circular families can mix SF Symbol icons with text/gauges
- Corner family can combine small circle (icon) with text/gauges

### Best Practices

- Choose SF Symbols that represent app function
- Helps set your complication apart on watch face
- Consider using relevant symbols for different entity types (thermometer for temp, lightbulb for lights, etc.)

**Sources:**
- [watchOS With SwiftUI by Tutorials, Chapter 8](https://www.kodeco.com/books/watchos-with-swiftui-by-tutorials/v2.0/chapters/8-complications)
- [Getting Started With watchOS 9 Complications](https://medium.com/better-programming/getting-started-with-watchos-9-complications-in-widgetkit-88dbf08fa1c1)

---

## 5. Deep Linking into the App

### Implementation with WidgetKit

**Challenges:**
- Developers commonly face challenges implementing deep links with WidgetKit complications
- Goal: Open specific dashboard/view when tapping a complication

**Approach:**
- Use WidgetKit's URL-based navigation
- Pass data from complication to detect which was tapped
- Navigate to specific view/dashboard based on URL scheme
- Implement URL handling in watchOS app to parse destination

**Current State:**
- WidgetKit supports deep linking through URL schemes
- Developer forums show active discussion on implementation patterns
- Less straightforward than ClockKit's previous approach

**For Home Assistant App:**
- Define URL scheme: `ha://dashboard/{dashboard_id}/view/{view_id}`
- Handle in app's SceneDelegate or SwiftUI App lifecycle
- Parse URL to navigate to correct dashboard/view

**Sources:**
- [How can I make it behave like deeplink when watchOS](https://developer.apple.com/forums/thread/716608)
- [Widget kit deep link - Apple Developer Forums](https://developer.apple.com/forums/thread/652578)
- [Complications(Widgets) For WatchOS — SwiftUI](https://lyvennithasasikumar.medium.com/complications-widgets-for-watchos-swiftui-99bf176231a8)

---

## 6. Entity Configuration Approach

### AppIntent Configuration

**Primary Method:**
- Use **AppIntentConfiguration** for configurable widgets (new to watchOS, supported in watchOS 26)
- Allows widgets to be configured with specific entities

**Implementation:**

1. **EntityQuery Structure:**
   - `entities(for identifiers:)` - filter entities
   - `defaultResult()` - return default entity for widget

2. **Recommendations on watchOS:**
   - Use `recommendations()` method to provide predefined choices
   - Shows in watchOS widget gallery
   - Example: Pre-configured widget for each room/zone in Home Assistant

3. **Configuration UI:**
   - Users see predefined entity choices in widget gallery
   - Can add multiple instances with different entities
   - Each widget instance maintains its own configuration

**For Home Assistant:**
- Define entity types (sensor, light, switch, etc.)
- Provide recommendations based on entity type
- Allow user to pick specific entity from their HA instance

**Sources:**
- [Build widgets for the Smart Stack on Apple Watch - WWDC23](https://developer.apple.com/videos/play/wwdc2023/10029/)
- [Adding Configuration Options to a WidgetKit Widget](https://www.answertopia.com/swiftui/adding-configuration-options-to-a-widgetkit-widget/)
- [Explore enhancements to App Intents - WWDC23](https://developer.apple.com/videos/play/wwdc2023/10103/)

---

## 7. Complication Refresh Rates

### System-Controlled Refresh

**Widget Budget:**
- Typically 40-70 refreshes per day
- Corresponds to reloading every **15-60 minutes**
- No direct developer control - system-defined schedule
- Limited to conserve battery and system resources

**watchOS Complications:**
- Can update **4 times per hour** (~every 10-25 minutes)
- With standard WidgetKit APIs, timeline expires after 15 minutes
- Watch face complications can usually update at 15-min frequency

### Push Updates (NEW in watchOS 26)

**Game Changer for Real-Time Data:**
- Send push notifications via APNs to trigger widget reload
- Not limited by timeline budget
- Ideal for Home Assistant sensor updates when state changes
- Server (HA instance) can push updates when entity state changes

**Implementation Strategy:**
- Use timelines for periodic updates (every 15 mins)
- Use push updates for critical/real-time changes
- Combine both for optimal user experience

**Sources:**
- [Keeping a widget up to date](https://developer.apple.com/documentation/widgetkit/keeping-a-widget-up-to-date)
- [How can widget be updated every ha…](https://developer.apple.com/forums/thread/733081)
- [Updating watchOS apps with timelines](https://developer.apple.com/documentation/watchos-apps/updating-watchos-apps-with-timelines)
- [What's new in widgets - WWDC25](https://developer.apple.com/videos/play/wwdc2025/278/)

---

## 8. iPhone Companion App Configuration

### Data Sync Methods

**WatchConnectivity (Primary Method):**
- **CRITICAL:** App Groups are **no longer applicable for watchOS**
- Use WatchConnectivity framework for iPhone ↔ Watch communication
- Best practices:
  - Activate WCSession as early as possible in app lifecycle
  - Makes app available to receive data from counterpart immediately
  - Works when devices within Bluetooth range or same Wi-Fi network
  - Interactive messaging: 97% delivery rate within 1 second

**CloudKit (Alternative):**
- For storing databases in iCloud, shared across all user devices
- Median sync delays below 10ms
- Good for user settings, dashboard configs, entity preferences
- Automatic sync based on network availability

**Best Approach for HA App:**
- **WatchConnectivity** for real-time settings changes
- **CloudKit** for persistent user preferences (dashboard selections, entity favorites)
- iPhone app sends configuration changes to Watch immediately
- Watch can request settings from iPhone on launch

### Configuration Scenarios

**Configuring Complications from iPhone:**
- User selects entity in iPhone app
- Send via WatchConnectivity to Watch
- Watch updates widget configuration
- Reload widget timeline with new entity

**Limitations:**
- App Groups no longer work for Watch apps
- Must use WatchConnectivity or CloudKit for data sharing

**Sources:**
- [There and back again: Data transfer on Apple Watch](https://wwdcnotes.com/documentation/wwdcnotes/wwdc21-10003-there-and-back-again-data-transfer-on-apple-watch/)
- [Top Data Synchronization Techniques for Watch and iPhone Apps](https://moldstud.com/articles/p-top-data-synchronization-techniques-for-watch-and-iphone-apps)
- [Communication between an iOS app and a companion watchOS app](https://medium.com/trade-me/communication-between-an-ios-app-and-a-companion-watchos-app-8320cb96651b)

---

## 9. Control Widgets in watchOS 26

### New Feature: Controls

**What are Controls:**
- Built with WidgetKit
- Enable quick actions without opening app
- Can launch app to specific view
- Available starting in watchOS 26

### Placement Options

Users can place controls in:
1. **Control Center** (main use case)
2. **Smart Stack**
3. **Action button** on Apple Watch Ultra

### Third-Party Support (NEW)

- watchOS 26 allows **third-party widgets in Control Center**
- Developers can plug widgets directly alongside system controls (Wi-Fi, Battery, Focus)
- Surface relevant actions or data from third-party apps

### iPhone Controls on Watch

**Cross-Device Feature:**
- Add almost any control from iPhone Control Center to Watch
- Configure via Watch app on iPhone (easier than on-watch method)
- Fully customizable layout

### Implementation for HA App

**Ideal Use Cases:**
- Toggle lights/switches
- Trigger scenes
- Adjust thermostats
- Execute scripts
- Quick access to frequently used actions

**Development:**
- Build using WidgetKit
- Define interactive elements
- Handle actions in app
- Support deep linking to dashboard if needed

**Sources:**
- [watchOS 26 could introduce third-party Control Center widgets](https://appleinsider.com/articles/25/06/05/watchos-26-could-introduce-third-party-control-center-widgets)
- [watchOS 26 lets you use Control Center toggles from your iPhone](https://www.idownloadblog.com/2025/06/16/watchos-26-iphone-controls-apple-watch-control-center-action-button-smart-stack-widget/)
- [What's new in watchOS 26 - WWDC25](https://developer.apple.com/videos/play/wwdc2025/334/)

---

## 10. Default Dashboard Pattern

### Best Practices

**User Selection:**
- Allow user to select "default dashboard" in iPhone companion app
- Store preference in CloudKit for cross-device sync
- Alternative: Store in UserDefaults and sync via WatchConnectivity

**Implementation Flow:**

1. **iPhone App:**
   - Settings screen with dashboard picker
   - User selects default dashboard/view
   - Save to CloudKit or send via WatchConnectivity

2. **Watch App Launch:**
   - Read default dashboard preference
   - Navigate to that dashboard on launch
   - Fallback to first dashboard if none set

3. **Deep Linking:**
   - Complication/widget tap can override default
   - Navigate to specific dashboard/view from URL

**Storage Strategy:**
```
Preference: Default Dashboard ID
Sync Method: CloudKit (persistent) + WatchConnectivity (immediate)
Fallback: First available dashboard
```

**User Experience:**
- First-time setup: Prompt user to select default dashboard
- Settings: Easy way to change default
- Per-complication: Each complication can link to different dashboard
- Launch behavior: Always show default unless deep-linked

---

## Key Recommendations for Home Assistant Watch App

### Architecture

1. **Complications:**
   - Use WidgetKit with accessory families
   - Support circular (single entity), rectangular (multiple entities), inline (text)
   - Display dynamic sensor data with SF Symbols
   - Configure via AppIntent with entity selection

2. **Real-Time Updates:**
   - Implement APNs push updates (watchOS 26 feature)
   - HA server pushes update when entity state changes
   - Fallback to 15-min timeline refresh

3. **Controls:**
   - Build Control Center widgets for quick actions
   - Support toggling lights, switches, scenes
   - Use WidgetKit for development

4. **Data Sync:**
   - WatchConnectivity for real-time iPhone ↔ Watch communication
   - CloudKit for persistent user preferences
   - Store dashboard configs, entity favorites, default dashboard

5. **Navigation:**
   - URL scheme for deep linking: `ha://dashboard/{id}/view/{view_id}`
   - Handle in app to navigate to specific dashboard
   - Default dashboard configurable in iPhone app

6. **Configuration UX:**
   - iPhone app: Primary configuration interface
   - WatchConnectivity: Immediate sync to Watch
   - Widget gallery: Show entity recommendations
   - Allow multiple complication instances with different entities

### Technical Stack

- **Language:** Swift + SwiftUI
- **Complications:** WidgetKit
- **Data Sync:** WatchConnectivity + CloudKit
- **Push Updates:** APNs for widget updates
- **Configuration:** AppIntent with EntityQuery
- **Deep Linking:** URL schemes handled in app

---

## Complete Source List

1. [What's new in watchOS 26 - WWDC25](https://developer.apple.com/videos/play/wwdc2025/334/)
2. [What's new in watchOS 26 | Documentation](https://wwdcnotes.com/documentation/wwdcnotes/wwdc25-334-whats-new-in-watchos-26/)
3. [WWDC 2025 - WidgetKit in iOS 26](https://forums.sobergroup.com/forum/services/website-development/9778-wwdc-2025-widgetkit-in-ios-26-a-complete-guide-to-modern-widget-development)
4. [Complications and widgets: Reloaded | Documentation](https://wwdcnotes.com/documentation/wwdcnotes/wwdc22-10050-complications-and-widgets-reloaded/)
5. [Apple WWDC 2025 Keynote](https://www.abt.com/blog/apple-wwdc-2025)
6. [What's new in widgets - WWDC25](https://developer.apple.com/videos/play/wwdc2025/278/)
7. [Go further with Complications in WidgetKit - WWDC22](https://developer.apple.com/videos/play/wwdc2022/10051/)
8. [Complications and widgets: Reloaded - WWDC22](https://developer.apple.com/videos/play/wwdc2022/10050/)
9. [Apple's watchOS 26 is available now](https://www.wareable.com/apple/apple-watchos-26-announcement-new-features-wwdc)
10. [Every watchOS 26 Face: Complete Guide](https://the5krunner.com/2025/11/03/watchos-26-apple-watch-faces-guide/)
11. [Complications - HIG](https://developers.apple.com/design/human-interface-guidelines/components/system-experiences/complications/)
12. [Apple Watch Complications | Figma](https://www.figma.com/community/file/1144262140809155120/apple-watch-complications)
13. [Mastering WatchOS Complications](https://ciandt.com/au/en-au/article/mastering-watchos-complications)
14. [watchOS With SwiftUI by Tutorials, Chapter 8](https://www.kodeco.com/books/watchos-with-swiftui-by-tutorials/v2.0/chapters/8-complications)
15. [watchOS 26 could introduce third-party Control Center widgets](https://appleinsider.com/articles/25/06/05/watchos-26-could-introduce-third-party-control-center-widgets)
16. [watchOS 26 lets you use Control Center toggles from your iPhone](https://www.idownloadblog.com/2025/06/16/watchos-26-iphone-controls-apple-watch-control-center-action-button-smart-stack-widget/)
17. [17 new features to check out in watchOS 26](https://www.idownloadblog.com/2025/09/19/watchos-26-top-features/)
18. [Apple Watch to get third-party widget support](https://www.newsbytesapp.com/news/science/apple-s-watchos-26-to-bring-3rd-party-widgets-to-control-center/story)
19. [Exclusive: watchOS 26 to offer third-party Control Center widgets](https://9to5mac.com/2025/06/05/exclusive-apple-prepping-support-for-third-party-control-center-widgets-in-watchos-26/)
20. [watchOS 26 is now available](https://9to5mac.com/2025/09/15/watchos-26-is-now-available-heres-whats-new-for-apple-watch/)
21. [This New watchOS 26 Feature Lets You Add Third-Party Controls](https://www.gotechtor.com/watchos-26-custom-controls-wwdc-2025/)
22. [All New watchOS 26 Features for Apple Watch](https://www.igeeksblog.com/watchos-26-features/)
23. [watchOS 26 delivers more personalized ways](https://www.apple.com/newsroom/2025/06/watchos-26-delivers-more-personalized-ways-to-stay-active-and-connected/)
24. [watchOS](https://mvolkmann.github.io/blog/swift/watchOS/?v=1.1.1)
25. [Communication between an iOS app and a companion watchOS app](https://medium.com/trade-me/communication-between-an-ios-app-and-a-companion-watchos-app-8320cb96651b)
26. [Keeping a widget up to date](https://developer.apple.com/documentation/widgetkit/keeping-a-widget-up-to-date)
27. [How can widget be updated every ha…](https://developer.apple.com/forums/thread/733081)
28. [How to Update or Refresh a Widget?](https://swiftsenpai.com/development/refreshing-widget/)
29. [Updating watchOS apps with timelines](https://developer.apple.com/documentation/watchos-apps/updating-watchos-apps-with-timelines)
30. [Creating accessory widgets and watch complications](https://developer.apple.com/documentation/widgetkit/creating-accessory-widgets-and-watch-complications)
31. [Getting Started With watchOS 9 Complications](https://medium.com/better-programming/getting-started-with-watchos-9-complications-in-widgetkit-88dbf08fa1c1)
32. [How can I make it behave like deeplink when watchOS](https://developer.apple.com/forums/thread/716608)
33. [Complications(Widgets) For WatchOS — SwiftUI](https://lyvennithasasikumar.medium.com/complications-widgets-for-watchos-swiftui-99bf176231a8)
34. [Widget kit deep link](https://developer.apple.com/forums/thread/652578)
35. [iOS Widgets with WidgetKit, Intents & Live Activities](https://medium.com/@ritika_verma/ios-widgets-with-widgetkit-intents-live-activities-31d8e64f070f)
36. [Build widgets for the Smart Stack on Apple Watch - WWDC23](https://developer.apple.com/videos/play/wwdc2023/10029/)
37. [Adding Configuration Options to a WidgetKit Widget](https://www.answertopia.com/swiftui/adding-configuration-options-to-a-widgetkit-widget/)
38. [Explore enhancements to App Intents - WWDC23](https://developer.apple.com/videos/play/wwdc2023/10103/)
39. [Migrating Widget Configurations to use AppIntent](https://crunchybagel.com/migrating-widget-configurations-to-use-appintent/)
40. [There and back again: Data transfer on Apple Watch](https://wwdcnotes.com/documentation/wwdcnotes/wwdc21-10003-there-and-back-again-data-transfer-on-apple-watch/)
41. [Top Data Synchronization Techniques for Watch and iPhone Apps](https://moldstud.com/articles/p-top-data-synchronization-techniques-for-watch-and-iphone-apps)
42. [Keeping your watchOS content up to date](https://developer.apple.com/documentation/watchos-apps/keeping-your-watchos-app-s-content-up-to-date)
