# Comprehensive HAWatchApp Spec Compliance & Quality Plan

## Context

The HAWatchApp is a native watchOS Home Assistant dashboard renderer. HAWatchCore (the platform-independent Swift library) is solid — 151 tests pass, all 7 previously documented bugs are fixed, and the rendering pipeline is complete. However, a thorough review of the Apple-side implementation (SwiftUI views, widgets, navigation, etc.) against the spec at `plans/watchos-plan.md` reveals ~15 functional gaps ranging from critical (broken deep-linking, missing tap actions) to moderate (missing widget bundle, incomplete polling). This plan addresses every gap to bring the app to full spec compliance.

**Spec**: `plans/watchos-plan.md` (architecture), `plans/watchos-plan-agent-*.md` (platform research)
**Implementation**: `HAWatchApp/` directory — `Sources/HAWatchCore/` (library) + `WatchApp/` (Apple UI) + `iPhoneApp/` (companion)

---

## Execution Strategy

This plan is large. **Use parallel subagents aggressively**:
- Group independent workstreams into concurrent subagents
- Each workstream below is tagged with a letter (A-G) — workstreams with no dependencies between them can run in parallel
- After each workstream completes, run `swift test` in `HAWatchApp/` to verify HAWatchCore tests still pass
- The Apple-side code can't be compiled on Linux, but can be syntax-checked and reviewed

---

## Workstream A: Entity Tap Actions (Critical)

**Problem**: Tiles render entities but tapping does nothing. Users expect to tap a light tile to toggle it, a lock to lock/unlock, etc.

**Files to modify**:
- `WatchApp/Views/Cards/TileCardView.swift` — add tap handler
- `WatchApp/ViewModels/DashboardViewModel.swift` — add `toggleEntity(entityId:)` method

**Approach**:
1. Add an `apiClient` accessor or pass it via environment so tile views can call services
2. Wrap TileCardView content in a `Button` that calls `HAAPIClient.callService()`
3. Reuse the toggle logic from `ToggleEntityIntent` in `ControlToggleWidget.swift:37-49` (check state, call turn_on/turn_off)
4. For non-toggleable entities (sensors, weather), make the tile non-interactive (no button)
5. After toggling, refresh the entity state and update the rendered view
6. Domains that support toggling: `light`, `switch`, `fan`, `input_boolean`, `lock`, `cover`, `climate`, `script`, `scene`, `automation`
7. For `script`/`scene`: call `turn_on` only (no toggle)
8. Add a brief haptic feedback on tap (WKInterfaceDevice.current().play(.click))

**Existing code to reuse**:
- `HAAPIClient.callService()` at `Sources/HAWatchCore/Services/HAAPIClient.swift`
- `ToggleEntityIntent.perform()` logic at `WatchApp/Widgets/ControlToggleWidget.swift:25-51`
- `StateFormatter` domain list at `Sources/HAWatchCore/Services/StateFormatter.swift`

---

## Workstream B: Deep-Link & Default Dashboard Navigation (Critical)

**Problem**: Deep-link environment values (`deepLinkDashboardId`, `deepLinkViewPath`) are set in `HAWatchApp.swift` but never consumed. Default dashboard loads data but doesn't navigate to the view page.

**Files to modify**:
- `WatchApp/ContentView.swift` — pass deep-link values
- `WatchApp/Views/DashboardListView.swift` — consume deep-link + auto-navigate to default dashboard
- `WatchApp/ViewModels/DashboardViewModel.swift` — add method to select view by path

**Approach**:
1. In `DashboardListView`, read `deepLinkDashboardId` and `deepLinkViewPath` from environment
2. When `defaultDashboardId` or deep-link dashboard ID is set, use a `@State var navigationPath` to programmatically push to `ViewPageView`
3. In `DashboardViewModel`, add `selectView(byPath:)` that sets `selectedViewIndex` based on the view path matching `renderedViews[i].path`
4. After loading the dashboard, if a view path is specified (from deep-link or settings), auto-select that view index

**Key references**:
- `HAWatchApp.swift:41-57` — deep-link parsing
- `DashboardListView.swift:47-52` — current default dashboard handling
- `RenderedView` has a `path` field for matching

---

## Workstream C: Polling & State Refresh (Critical)

**Problem**: `DashboardViewModel.startPolling()` only re-renders the view that was selected when polling started. If the user swipes to a different view, the display goes stale.

**Files to modify**:
- `WatchApp/ViewModels/DashboardViewModel.swift` — fix polling to track current view

**Approach**:
1. In the polling loop, always read the current `selectedViewIndex` (not a captured value)
2. Re-render the currently visible view, not the one captured at poll start
3. The current code already accesses `self.selectedViewIndex` inside the loop — but verify it's not captured by closure. Looking at the code, it accesses `self.selectedViewIndex` which should be live. However, the `[weak self]` capture means `self` access is correct. **Verify this works correctly.**
4. Consider: also invalidate other views when polling triggers, so they re-render when swiped to. Add a `staleViews: Set<Int>` tracker, and re-render views lazily when they become visible.

---

## Workstream D: Widget Extension Fixes (Critical)

**Problem**: Multiple widget issues — no WidgetBundle, static control widget, incomplete corner complication.

**Files to modify**:
- `WatchApp/Widgets/` — add WidgetBundle, fix ControlToggleWidget, add corner complication view

### D1: Add WidgetBundle
Create `WatchApp/Widgets/HAWatchWidgetBundle.swift`:
```swift
@main
struct HAWatchWidgetBundle: WidgetBundle {
    var body: some Widget {
        EntityComplicationWidget()
        ControlToggleWidget()
    }
}
```
**Important**: Remove `@main` from any individual widget struct if present. The bundle is the entry point.

### D2: Make ControlToggleWidget Configurable
- Change `StaticControlConfiguration` to `AppIntentConfiguration` with an entity parameter
- Create a `ControlToggleIntent` (or reuse `ToggleEntityIntent` with `WidgetConfigurationIntent` conformance) that lets users pick which entity to toggle
- Show the entity icon and name dynamically instead of generic "Toggle" / power icon

### D3: Corner Complication as Gauge
- Add `CornerComplicationView` that renders a `Gauge` for numeric entities (battery, temperature)
- For non-numeric entities, fall back to circular view
- Use `widgetLabel` for the entity name text along the curve

---

## Workstream E: Error Handling & UI States (Moderate)

**Problem**: ViewPageView has no error state or retry. Camera/map views silently fail. No offline banner.

**Files to modify**:
- `WatchApp/Views/ViewPageView.swift` — add error/retry
- `WatchApp/ViewModels/DashboardViewModel.swift` — track connection state
- `WatchApp/Views/Cards/CameraCardView.swift` — add error state
- `WatchApp/Views/Cards/ImageMapCardView.swift` — add error state

**Approach**:
1. In `ViewPageView`, show error message + retry button when `viewModel.error` is set (mirror DashboardListView's error handling pattern)
2. Add a `connectionState` enum to DashboardViewModel: `.connected`, `.disconnected`, `.reconnecting`
3. When a poll fails, set state to `.disconnected` and show a subtle banner at the top
4. On reconnect, auto-refresh
5. For CameraCardView and ImageMapCardView: show an error icon/text if image load fails (instead of perpetual ProgressView spinner)
6. Add timeout handling — if load takes > 10s, show error state

---

## Workstream F: View Polish & Spec Alignment (Moderate)

These are smaller fixes to match the spec exactly. Can be done as one batch.

**Files to modify**: Various view files

### F1: Heading Uppercase
`WatchApp/Views/Cards/HeadingCardView.swift:13` — add `.textCase(.uppercase)` to heading Text

### F2: Map Inline Zones
`WatchApp/Views/Cards/MapKitCardView.swift` — add `MapCircle` zones to the inline preview (currently only in fullscreen). Copy the `ForEach` zone block from `MapFullScreenView` (lines 77-88) into the inline `Map` content.

### F3: Map Marker Entity Pictures
`WatchApp/Views/Cards/MapKitCardView.swift` and `ImageMapCardView.swift` — replace plain circles with entity picture overlays where available. Check if `MapMarker` has a `pictureURL` field in `RenderedView.swift`; if so, use `EntityPictureView` inside the marker annotation. If not, add the field to `RenderedView.MapMarker` and populate it in `CardRenderer`/`ViewRenderer`.

### F4: Avoid Creating Redundant API Clients
`CameraCardView.swift:49` and `ImageMapCardView.swift:78` each create a new `HAAPIClient`. Instead, pass the API client (or settings) through environment and reuse a shared instance. Add `HAAPIClient` or a lightweight image-loading service to the environment.

### F5: Badge Entity Pictures
Verify that `BadgeView` renders `entityPictureURL` when present. Check if `RenderedBadge.entityPictureURL` is properly consumed in `WatchApp/Views/Components/BadgeView.swift`.

---

## Workstream G: Test Coverage (Moderate)

**Files to create/modify**:
- `Tests/HAWatchCoreTests/Rendering/ViewRendererTests.swift` — NEW: integration test
- Verify all 151 existing tests still pass

### G1: ViewRenderer Integration Test
The spec explicitly calls for this. Create a test that:
1. Builds a mock `ViewConfig` with a mix of card types (tiles, auto-entities, headings, badges)
2. Uses a mock/stub API client (protocol-based or inject responses)
3. Runs `ViewRenderer.render(view:)`
4. Asserts the output `RenderedView` tree has correct structure

**Challenge**: ViewRenderer depends on HAAPIClient (an actor). Either:
- Extract a protocol `HAAPIClientProtocol` and inject a mock, OR
- Create a minimal test that uses known template responses

### G2: Run Existing Tests
```bash
cd HAWatchApp && swift test
```
Verify all 151 tests pass. Fix any regressions introduced by the above changes.

---

## Workstream H: watchOS 26 SDK Bump & Features

**Problem**: The spec targets watchOS 26 / Swift 6.2 / Xcode 26 with Liquid Glass, SF Symbols 7, and RelevanceKit. Project currently targets watchOS 11.0 / Swift 6.0 / Xcode 16.0.

### H1: Version Bump
**Files to modify**:
- `HAWatchApp/project.yml` — update deployment targets and Swift version
- `HAWatchApp/Package.swift` — update swift-tools-version

Changes:
- `project.yml`: `watchOS: "26.0"`, `iOS: "26.0"`, `xcodeVersion: "26.0"`, `SWIFT_VERSION: "6.2"`
- `Package.swift`: `// swift-tools-version: 6.2`
- Update all `deploymentTarget` entries for watchOS and iOS targets

### H2: Liquid Glass Design
**Files to modify**: All view files using `.ultraThinMaterial`
- `TileCardView.swift` — replace `.ultraThinMaterial` background with `.glassEffect()` or Liquid Glass material
- `BadgeView.swift` — same
- `WeatherCardView.swift` — same
- `LogbookCardView.swift` — same
- `HistoryGraphCardView.swift` — same
- `CameraCardView.swift` — loading placeholder
- `ImageMapCardView.swift` — loading placeholder

**Research needed**: The exact SwiftUI API for Liquid Glass may be `.glassEffect()`, `.glass` material, or a new material type. The implementing session should web-search for "watchOS 26 SwiftUI Liquid Glass material API" to find the correct modifier. The spec research doc (`plans/watchos-plan-agent-a708677.md`) has details on the design language but may not have exact API names.

### H3: SF Symbols 7 Animations
**Files to modify**:
- `WatchApp/Views/Components/EntityIconView.swift` — add symbol transition effects
- `WatchApp/Views/Cards/TileCardView.swift` — animate icon on state change

Approach:
- Use `.symbolEffect(.bounce)` on toggle actions
- Use `.contentTransition(.symbolEffect(.replace))` when entity state changes
- Weather icons: use `.symbolEffect(.variableColor)` for animated weather
- Research exact watchOS 26 symbol effect APIs

### H4: Smart Stack RelevanceKit
**Files to modify**:
- `WatchApp/Widgets/EntityComplication.swift` — add relevance hints
- Potentially new file for relevance configuration

Approach:
- Import `RelevanceKit` (if available as separate framework) or use WidgetKit relevance APIs
- Add location-based relevance: show "home" entities when at home GPS coordinates
- Add time-based relevance: show morning dashboard during AM hours
- This is a nice-to-have — implement basic relevance first, don't over-engineer

### H5: APNs Push Widget Updates (Future / Optional)
- Requires a Home Assistant addon to send APNs on state change
- Flag with TODO comment in `EntityComplication.swift` for future implementation
- Do NOT implement the addon, just add the client-side APNs handler placeholder

---

## Execution Order

```
Phase 0 — Sequential (do this FIRST):
  └── Subagent 0: Workstream H1 (Version Bump) — all other work depends on correct SDK target

Phase 1 — Parallel:
  ├── Subagent 1: Workstream A (Entity Tap Actions) + F4 (shared API client)
  ├── Subagent 2: Workstream B (Deep-Link Nav) + C (Polling Fix)
  └── Subagent 3: Workstream D (Widget Fixes)

Phase 2 — Parallel:
  ├── Subagent 4: Workstream E (Error Handling) + F1-F3, F5 (View Polish)
  └── Subagent 5: Workstream H2-H3 (Liquid Glass + SF Symbols 7 animations)

Phase 3 — Parallel:
  ├── Subagent 6: Workstream H4 (Smart Stack RelevanceKit)
  └── Subagent 7: Workstream G (Tests) — verify all changes

Phase 4 — Sequential:
  └── Final review: Read all modified files, run `swift test`, verify checklist
```

---

## Verification

1. **HAWatchCore tests**: `cd HAWatchApp && swift test` — all tests must pass
2. **Code review**: Read modified files to verify no compile errors (we can't build watchOS on Linux, but Swift syntax should be valid)
3. **Manual checklist** after changes:
   - [ ] project.yml targets watchOS 26.0 / iOS 26.0 / Swift 6.2
   - [ ] Package.swift uses swift-tools-version: 6.2
   - [ ] Tiles have tap actions for toggleable domains (light, switch, fan, cover, lock, input_boolean, script, scene, automation)
   - [ ] Deep-link URL `hawatch://dashboard/x/view/y` navigates correctly
   - [ ] Default dashboard auto-navigates to ViewPageView (not stuck on list)
   - [ ] Polling refreshes the currently visible view (not a stale captured index)
   - [ ] WidgetBundle registers both EntityComplicationWidget and ControlToggleWidget
   - [ ] ControlToggleWidget allows entity selection (not static)
   - [ ] Corner complication shows gauge for numeric entities
   - [ ] ViewPageView shows error + retry on failure
   - [ ] Camera/map views show error state on image load failure (not perpetual spinner)
   - [ ] Headings are uppercase
   - [ ] MapKit inline view shows zone circles
   - [ ] Views use Liquid Glass materials instead of .ultraThinMaterial
   - [ ] Entity icons have SF Symbols 7 transition animations on state change
   - [ ] Smart Stack relevance hints configured for complications
   - [ ] ViewRendererTests integration test exists and passes
   - [ ] All 151+ HAWatchCore tests pass

---

## Files Reference

### HAWatchCore (read-only context — don't modify unless adding test protocol)
- `Sources/HAWatchCore/Services/HAAPIClient.swift` — REST+WS client (408 lines)
- `Sources/HAWatchCore/Services/StateFormatter.swift` — domain formatting (188 lines)
- `Sources/HAWatchCore/Models/RenderedView.swift` — output tree (335 lines)
- `Sources/HAWatchCore/Rendering/ViewRenderer.swift` — orchestrator (838 lines)
- `Sources/HAWatchCore/Rendering/CardRenderer.swift` — card dispatch (212 lines)

### Apple-Side (primary modification targets)
- `WatchApp/HAWatchApp.swift` — app entry, deep-link, background refresh
- `WatchApp/ContentView.swift` — root conditional view
- `WatchApp/ViewModels/DashboardViewModel.swift` — state management
- `WatchApp/Views/DashboardListView.swift` — dashboard navigation
- `WatchApp/Views/ViewPageView.swift` — view pagination
- `WatchApp/Views/Cards/TileCardView.swift` — entity tiles (needs tap action)
- `WatchApp/Views/Cards/MapKitCardView.swift` — native map (needs inline zones)
- `WatchApp/Views/Cards/CameraCardView.swift` — camera snapshots (needs error state)
- `WatchApp/Views/Cards/ImageMapCardView.swift` — image overlay (needs error state)
- `WatchApp/Views/Cards/HeadingCardView.swift` — heading (needs uppercase)
- `WatchApp/Widgets/ControlToggleWidget.swift` — control widget (needs configurable entity)
- `WatchApp/Widgets/EntityComplication.swift` — complications (needs corner gauge)
- `WatchApp/Widgets/ComplicationConfigIntent.swift` — intent config

### New Files
- `WatchApp/Widgets/HAWatchWidgetBundle.swift` — widget bundle registration
- `Tests/HAWatchCoreTests/Rendering/ViewRendererTests.swift` — integration test

---

## Notes for the Implementing Session

- **Web search** for exact Liquid Glass and SF Symbols 7 APIs — the spec research docs have conceptual info but may lack exact SwiftUI modifier names
- **Don't modify HAWatchCore models/services** unless absolutely necessary (e.g., adding a `pictureURL` field to `MapMarker`). The core is well-tested and stable.
- **Can't compile watchOS on Linux** — verify changes by reading them carefully and running `swift test` for the core library. Syntax errors in Apple-only views won't be caught until Xcode build.
- **Use `#if canImport(WatchKit)`** for any haptic feedback or watch-specific APIs to keep the code buildable in test environments
- The user's HA instance is at `https://homeassistant.oasys.lol` with token in `.env` — useful for manual testing with `ha-sync render` but do NOT run destructive commands
