# WatchOS Home Assistant Dashboard App

## Context

A native watchOS app that renders Home Assistant dashboards by fetching dashboard config from the HA API and mapping HA card types to native SwiftUI elements. This mirrors what `ha-sync render` does for the CLI, but targeting Apple Watch.

The user plans to create a dedicated WatchOS dashboard in the HA UI. The app is standalone for core functionality, with an iPhone companion app for configuration (URL, token, default dashboard selection).

## Architecture

**MVVM + Services**, targeting **watchOS 26** exclusively (Swift 6.2, Xcode 26, SF Symbols 7).

watchOS 26 benefits:
- **Liquid Glass** design language -- translucent, depth-aware UI
- **SF Symbols 7** -- 6,900+ symbols with draw animations and gradients
- **Control Widgets** -- quick-toggle controls from Control Center / Action Button
- **Smart Stack relevance** -- location-aware widget prioritization
- **WidgetKit complications** -- show entity values on watch face, deep-link into app
- **APNs push widget updates** -- near-real-time complication refresh (future: requires HA addon)
- Supported on Apple Watch Series 6+, SE 2nd gen+, all Ultra models

### Platform Split: HAWatchCore (Linux) vs HAWatchApp (Apple)

The bulk of the logic lives in `HAWatchCore`, a pure Swift Package with **no Apple framework dependencies** (no SwiftUI, MapKit, WidgetKit, etc.). It builds and tests on Linux with `swift build` / `swift test`. The Apple-specific layer is a thin shell that maps core data structures to SwiftUI views.

**What's in HAWatchCore (platform-independent):**
- All Codable models (dashboard config, entity state, visibility conditions, settings)
- HA API client (Foundation URLSession -- works on Linux via swift-corelibs-foundation)
- Template service (batch Jinja2 evaluation via REST)
- State cache (batch entity fetch + in-memory cache)
- Auto-entities resolver (filter evaluation: domain search, label lookup, attribute match)
- Icon mapper (MDI name string -> SF Symbol name string -- just a string dictionary, no framework)
- State formatter (entity state -> `FormattedState(text, colorName)` -- colorName as enum, not SwiftUI Color)
- Visibility checker (condition evaluation against cached state)
- Coordinate mapper (GPS bounds -> normalized 0..1 position for image overlay maps)
- **View model tree** -- the core produces a `RenderedView` tree (resolved badges, sections, cards with display text, icon names, colors as enums) that the UI layer renders

**What's in HAWatchApp (Apple-only):**
- SwiftUI views that consume `RenderedView` tree
- MapKit views (Mode 2 standard maps)
- WidgetKit complications + Control Widgets
- WatchConnectivity + CloudKit sync
- Keychain storage
- Authenticated image loading (entity pictures, camera snapshots)

```
HAWatchApp/
  Package.swift                          # Swift Package (HAWatchCore target + test target)

  Sources/HAWatchCore/                   # *** PLATFORM-INDEPENDENT -- builds on Linux ***
    Models/
      DashboardConfig.swift              # Codable: DashboardConfig, ViewConfig, SectionConfig, CardConfig, BadgeConfig
      EntityState.swift                  # Codable: EntityState (state, attributes, last_changed)
      VisibilityCondition.swift          # Enum: state, numeric_state, user, screen, or/and/not
      AppSettings.swift                  # Default dashboard/view, polling interval (Codable, no platform deps)
      RenderedView.swift                 # Output tree: RenderedView, RenderedSection, RenderedCard, RenderedBadge
      FormattedState.swift               # FormattedState(text: String, color: StateColor) -- StateColor is an enum
    Services/
      HAAPIClient.swift                  # REST client (Foundation URLSession) + transient WebSocket
      StateCache.swift                   # In-memory entity state cache, batch fetch via template
      TemplateService.swift              # Jinja2 eval via POST /api/template, batching with ||| separator
      AutoEntitiesResolver.swift         # Filter evaluation (domain search, label lookup, attribute match, not)
      IconMapper.swift                   # MDI name -> SF Symbol name (String->String dict + fallback chain)
      StateFormatter.swift               # Entity state -> FormattedState per domain (port of render.py)
      VisibilityChecker.swift            # Evaluate visibility conditions against cached state
      CoordinateMapper.swift             # GPS bounds -> normalized position for image overlay maps
    Rendering/
      ViewRenderer.swift                 # Orchestrate: fetch states, resolve auto-entities, check visibility, produce RenderedView
      BadgeRenderer.swift                # Resolve badge config -> RenderedBadge (template eval, state lookup)
      CardRenderer.swift                 # Resolve card config -> RenderedCard (dispatch by type)
      SectionRenderer.swift              # Pending-heading logic, visibility, produce RenderedSection

  Tests/HAWatchCoreTests/                # *** RUNS ON LINUX with `swift test` ***
    Models/
      DashboardConfigTests.swift         # Parse real HA JSON fixtures
      VisibilityConditionTests.swift
    Services/
      IconMapperTests.swift              # MDI -> SF Symbol mapping coverage
      StateFormatterTests.swift          # Per-domain formatting
      VisibilityCheckerTests.swift       # Condition evaluation with mock state
      AutoEntitiesResolverTests.swift    # Filter matching logic
      CoordinateMapperTests.swift        # GPS -> pixel math
    Rendering/
      SectionRendererTests.swift         # Pending-heading logic
      ViewRendererTests.swift            # Integration: config -> RenderedView with mock API

  WatchApp/                              # *** APPLE-ONLY (Xcode project) ***
    HAWatchApp.swift                     # Entry point + URL scheme handling
    ContentView.swift                    # Root: settings guard -> default dashboard
    ViewModels/
      DashboardViewModel.swift           # Fetch dashboard list, manage RenderedView, polling
    Views/
      DashboardListView.swift            # NavigationStack list of dashboards
      ViewPageView.swift                 # ScrollView rendering RenderedView tree
      Cards/
        TileCardView.swift               # Render RenderedCard.tile
        HeadingCardView.swift            # Render RenderedCard.heading
        AutoEntitiesCardView.swift       # Render RenderedCard.autoEntities (list of resolved tiles)
        ImageMapCardView.swift           # Mode 1: image + positioned markers (uses CoordinateMapper)
        MapKitCardView.swift             # Mode 2: native MapKit with annotations
        CameraCardView.swift             # Snapshot image (full-screen on tap)
        WeatherCardView.swift            # Current conditions + forecast
        HistoryGraphCardView.swift       # SwiftUI Charts line graph
        LogbookCardView.swift            # Recent state changes list
      Components/
        BadgeView.swift                  # Render RenderedBadge
        EntityIconView.swift             # Image(systemName:) from SF Symbol name string
        EntityStateText.swift            # Text with color from StateColor enum -> SwiftUI Color
        EntityPictureView.swift          # Authenticated AsyncImage (person photos)
        CardFactory.swift                # Switch on RenderedCard type -> appropriate view
      Settings/
        WatchSettingsView.swift          # URL + token input, default dashboard picker
    Platform/
      KeychainService.swift              # Secure token storage
      SettingsSync.swift                 # WatchConnectivity + CloudKit
    Widgets/
      EntityComplication.swift           # WidgetKit accessory families
      ControlToggleWidget.swift          # Control Widget for quick toggles
      ComplicationConfigIntent.swift     # AppIntentConfiguration for entity selection

  iPhoneApp/                             # *** APPLE-ONLY (companion) ***
    SettingsView.swift                   # Full settings UI
    DashboardPickerView.swift            # Browse dashboards, pick default
    ComplicationConfigView.swift         # Configure complication entities
```

## Default Dashboard & Navigation

- **Default dashboard/view** stored in `AppSettings` (persisted via CloudKit, synced via WatchConnectivity)
- On launch: navigate directly to default view (skip dashboard list)
- Dashboard list accessible via back-navigation or settings
- Deep-link URL scheme: `hawatch://dashboard/{id}/view/{view_id}` -- used by complications to jump to specific views
- Views within a dashboard: swipe with `TabView(.verticalPage)`

## iPhone Companion App

The iPhone app provides a richer configuration UI:
- **HA connection**: URL + long-lived access token (synced to Watch via WatchConnectivity)
- **Default dashboard/view picker**: browse available dashboards, select default
- **Complication config**: pick which entity to show on each complication slot
- **Settings sync**: WatchConnectivity for immediate push, CloudKit for persistent storage
- Core watch app still works standalone (can enter URL + token on watch)

## Complications (WidgetKit)

Show entity values directly on the watch face using WidgetKit accessory families:

| Family | Use Case | Example |
|--------|----------|---------|
| `accessoryCircular` | Single entity with icon + value | Thermometer icon + "23°" |
| `accessoryRectangular` | Multiple entities or entity + graph | "Living Room 23° / Humidity 45%" |
| `accessoryInline` | Text-only entity value | "Inside: 23°C" |
| `accessoryCorner` | Gauge-style entity | Battery level arc |

**Configuration:** `AppIntentConfiguration` lets users pick which entity each complication shows. Entity list fetched from HA API, cached. `recommendations()` provides pre-populated suggestions.

**Refresh:** System-controlled timeline (~40-70 refreshes/day). Future: APNs push updates for real-time (requires HA-side automation sending push notifications on state change).

**Deep-link:** Each complication taps into the app at the relevant dashboard/view via URL scheme.

## API Strategy

**REST for data, transient WebSocket for dashboard config only.**

WebSocket is needed because `lovelace/config` (get dashboard) is WebSocket-only. Approach: open WebSocket, auth, fetch config, close. This happens on launch and manual refresh.

For entity states: batch fetch via `POST /api/template` using the same delimiter approach as `render.py:262-298` -- one API call for all entities in the current view.

For Jinja2 templates (mushroom badges): batch all template strings into a single `POST /api/template` call with `|||` separators.

**Polling:** Every 30s in foreground, re-fetch entity states via REST. Background refresh via `WKApplicationRefreshBackgroundTask` for periodic updates when app is suspended.

**Auth:** Bearer token in HTTP headers (REST) + access_token in WebSocket auth message. Token stored in Watch Keychain.

## Card Type Mapping

### Fully Supported

| HA Card | SwiftUI Rendering | Reference |
|---------|-------------------|-----------|
| **tile** | `HStack { SF_Symbol, VStack { name, state } }` -- two side-by-side when `grid_options.columns: 6` | `render.py:575-597` |
| **heading** | Bold uppercase `Text` + SF Symbol + inline badges below | `render.py:599-627` |
| **entity badge** | `HStack { icon, name, state }` with colored state | `render.py:508-545` |
| **mushroom-template-badge** | Content/label from `POST /api/template` eval | `render.py:546-573` |
| **auto-entities** | Resolve filters via template API, render each as tile row | `render.py:671-788` |
| **logbook** | Recent state changes with time-ago | `render.py:790-866` |
| **weather-forecast** | SF Symbol weather icon + temp + horizontal forecast | New |

### Newly Supported (CLI skips these)

| HA Card | SwiftUI Rendering | Notes |
|---------|-------------------|-------|
| **picture-entity** (camera) | Snapshot via `GET /api/camera_proxy/{entity_id}`, full-screen sheet on tap | Auth header required |
| **custom:map-card** | `Map` (MapKit) with satellite imagery + entity annotations. Full-screen on tap | See Map Card section below |
| **history-graph** | `Chart { LineMark }` via `GET /api/history/period` | Compact height |

### Skipped

| HA Card | Reason |
|---------|--------|
| **navbar-card** | Not meaningful on watch |
| **mushroom-chips-card** | Low priority |
| **card_mod styles** | CSS, not applicable |

## Map Card (`custom:map-card`)

The user's `custom:map-card` uses Leaflet with these features:
- **Satellite tiles** (ArcGIS World Imagery)
- **Entity annotations**: person entities with custom colors, sizes, z-index offsets
- **Zone entities**: displayed as icons with custom colors and opacity
- **Image overlays**: custom drone photo overlaid on GPS bounds (via `ha-map-card-image` plugin)
- **focus_entity**: center map on a zone (e.g., `zone.home`)
- **history tracks**: `history_start: 24 hours ago` with gradual opacity

**Two rendering modes depending on card config:**

### Mode 1: Image overlay map (when `ha-map-card-image` plugin present)
When the card uses a custom image overlay (drone photo), skip MapKit entirely and render as a custom image view:
- Load image from HA (authenticated `URLSession` to `/local/...` URL)
- Read GPS bounds from plugin config: `bounds: [[lat1, lon1], [lat2, lon2]]`
- Fetch entity lat/lon from state attributes via template API
- Linear transform GPS coords -> pixel position: `x = (lon - west) / (east - west) * width`, `y = (north - lat) / (north - south) * height`
- SwiftUI `ZStack`: image background + entity markers positioned via `GeometryReader`
- Entity markers: colored circles with entity pictures or initials, matching card config colors/sizes
- Zone markers: SF Symbol icons at zone center coordinates
- Full-screen sheet on tap for zoom/pan
- **Not supported**: gradual opacity history tracks (could approximate with a few discrete opacity steps)

### Mode 2: Standard map (no image overlay)
When the card uses regular map tiles:
- MapKit `Map` with `mapStyle: .imagery` (satellite) or `.standard`
- `Annotation` views at entity lat/lon
- `MapCircle` overlays for zones at center/radius
- `focus_entity`: center map on zone coordinates
- Full-screen sheet on tap with native zoom/pan

## Layout

Watch screen (198-410pt). The 12-column HA grid collapses to **2 effective columns**:

- `grid_options.columns: 6` (half) -> two tiles side by side in `HStack`
- `grid_options.columns: 12` or unset -> full width
- Maps and cameras: full width inline, full-screen sheet on tap
- Views: `ScrollView` within `TabView(.verticalPage)` for swiping between views
- Badges: top of each view page
- Sections: vertical spacing; headings only show if followed by content (matching `render.py:891-926` pending-heading logic)

## Visibility Conditions

Direct port of `render.py:332-391`:
- **state / state_not**: Check cached entity state
- **numeric_state**: above/below on numeric value
- **user**: Check if current HA user matches (resolve via person entity user_id)
- **screen**: Treat watch as mobile (`max-width: 767px` matches, `min-width: 768px` doesn't)
- **or/and/not**: Recursive combinators

## Icons: MDI -> SF Symbols

With SF Symbols 7 (watchOS 26), ~90%+ of ~150 MDI icons have excellent matches. Key mappings:

| Category | Coverage | Examples |
|----------|----------|---------|
| Lighting | 100% | `lightbulb.fill`, `lamp.ceiling.fill`, `lamp.desk.fill`, `lamp.floor.fill` |
| Doors/Windows | 100% | `door.left.hand.open`, `door.garage.closed`, `window.vertical.open` |
| Climate | 95% | `fan.fill`, `thermometer.medium`, `snowflake`, `flame.fill` |
| Weather | 100% | `sun.max.fill`, `cloud.rain.fill`, `cloud.snow.fill`, `wind` |
| Security | 100% | `lock.fill`, `shield.fill`, `bell.fill` |
| Appliances | 95% | `washer.fill`, `refrigerator.fill`, `dishwasher.fill`, `stove.fill` |
| Media | 95% | `tv.fill`, `hifispeaker.fill`, `play.fill`, `music.note` |
| People/Pets | 90% | `person.fill`, `dog.fill`, `cat.fill`, `pawprint.fill` |

**Fallback chain** (matching `render.py:393-413`):
1. Direct MDI name -> SF Symbol lookup
2. Partial match (substring in mapping keys)
3. Device class -> SF Symbol
4. Entity domain -> SF Symbol
5. `circle.fill` as last resort

## State Formatting

Direct port of `render.py:415-506`:

| Domain | State | Display | Color |
|--------|-------|---------|-------|
| person | home | "Home" | .green |
| person | not_home | "Away" | .secondary |
| lock | locked/unlocked | "Locked"/"Unlocked" | .green/.red |
| binary_sensor (door) | on/off | "Open"/"Closed" | .yellow/.green |
| light/switch | on/off | "On"/"Off" | .yellow/.secondary |
| sensor | numeric | Formatted number + unit | nil |
| climate | heat/cool | "Heating"/"Cooling" | .red/.blue |

## Entity Pictures

Person entities: `entity_picture` attribute -> `URLSession` with Bearer auth -> circular clip. Cache in memory.

## Implementation Phases

### Phase 1: HAWatchCore -- Models + Services (Linux, `swift test`)
1. `Package.swift` -- Swift Package with HAWatchCore library + HAWatchCoreTests
2. `DashboardConfig` models -- Codable structs (parse real HA JSON fixtures in tests)
3. `EntityState` + `FormattedState` + `StateColor` enum
4. `AppSettings` -- Codable, no platform deps
5. `IconMapper` -- full MDI -> SF Symbol name dictionary + fallback chain + tests for coverage
6. `StateFormatter` -- port of `render.py:415-506` + tests for every domain
7. `VisibilityChecker` -- port of `render.py:332-391` + tests with mock state
8. `CoordinateMapper` -- GPS bounds -> normalized position + tests

### Phase 2: HAWatchCore -- API + Rendering (Linux, `swift test`)
9. `HAAPIClient` -- REST client (Foundation URLSession) + transient WebSocket
10. `TemplateService` -- batch Jinja2 eval with `|||` separator
11. `StateCache` -- batch entity fetch + in-memory cache
12. `AutoEntitiesResolver` -- filter evaluation (domain, label, attributes, not-conditions)
13. `RenderedView` / `RenderedSection` / `RenderedCard` / `RenderedBadge` -- output tree types
14. `ViewRenderer` + `CardRenderer` + `BadgeRenderer` + `SectionRenderer` -- produce RenderedView from config + state
15. Integration tests: config JSON -> RenderedView with mock API responses

### Phase 3: WatchApp -- SwiftUI Shell (Xcode, watchOS 26 simulator)
16. Xcode project importing HAWatchCore package
17. `TileCardView` + `HeadingCardView` + `BadgeView` + `EntityIconView` + `EntityStateText`
18. `CardFactory` -- switch on RenderedCard type
19. `ViewPageView` -- ScrollView with badges, sections, 2-column grid
20. `DashboardViewModel` -- fetch + render + poll, default dashboard
21. `WatchSettingsView` -- URL + token, `KeychainService`
22. View navigation via `TabView(.verticalPage)` + deep-link URL scheme

### Phase 4: WatchApp -- Complex Cards (Xcode)
23. `AutoEntitiesCardView` (renders resolved tile list from RenderedCard)
24. `ImageMapCardView` -- image + positioned markers using CoordinateMapper
25. `MapKitCardView` -- native MapKit satellite + annotations
26. `CameraCardView` -- snapshot + full-screen sheet
27. `WeatherCardView` -- SF Symbol weather icons + forecast
28. `LogbookCardView` + `HistoryGraphCardView` (SwiftUI Charts)
29. `EntityPictureView` (authenticated image loading)

### Phase 5: iPhone Companion + Complications (Xcode)
30. iPhone `SettingsView` + `DashboardPickerView`
31. `SettingsSync` -- WatchConnectivity + CloudKit
32. `EntityComplication` -- WidgetKit accessory families
33. `ComplicationConfigIntent` -- AppIntent entity picker
34. `ControlToggleWidget` -- Control Widget for quick toggles

### Phase 6: Polish + watchOS 26 Features (Xcode)
35. 30s foreground polling + `WKApplicationRefreshBackgroundTask`
36. Error handling, loading states, connection lost UI
37. **Liquid Glass** styling
38. SF Symbols 7 **draw animations** for state transitions
39. **Smart Stack** widget with location-based relevance

## Verification

### Linux (`swift test` on dev box)
1. **Build**: `swift build` succeeds for HAWatchCore
2. **Models**: Parse real HA dashboard JSON fixtures
3. **Icon mapping**: All ~150 MDI icons resolve to SF Symbol names
4. **State formatting**: Every domain produces correct text + color
5. **Visibility**: Conditions evaluate correctly against mock state
6. **Coordinate mapping**: GPS -> normalized position math is accurate
7. **Auto-entities**: Filters match/exclude correctly with mock data
8. **Rendering**: Config + mock state -> correct RenderedView tree
9. **Section logic**: Pending headings only show when followed by content

### Apple (Xcode watchOS 26 simulator)
10. **Settings**: Enter HA URL + token, validates via `GET /api/config`
11. **iPhone sync**: Settings sync from iPhone to Watch
12. **Default dashboard**: App launches into configured default view
13. **Dashboard fetch**: WebSocket fetches config, renders to RenderedView, displays
14. **Tile rendering**: SF Symbols, names, colored state text
15. **2-column layout**: Side-by-side tiles for `grid_options.columns: 6`
16. **Image map**: Drone photo with positioned entity markers
17. **Complications**: Entity value on watch face, taps into app
18. **Polling**: States refresh, UI updates reactively
