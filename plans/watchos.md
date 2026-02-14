I want to build a native WatchOS app for Home Assistant that renders a HA dashboard configured in the HA UI by mapping HA components/cards to native elements.

It's obviously fine if only a subset works, and if we e.g. always render a button the same way, ignoring things like showing it vertical vs horitzontal.

But visibility should work, icons (if we can map mdi to SF icons), 2-column rendering of side by side buttons, "entity picture"s, ideally headings with badges, badges at the top of the page, auto-entities.

Also map-cards, inline video... I imagine that they would always take up the full width and height of the screen, so if the first item on the page is a map, you'd see only that (with rendered icons?) until you scroll down.

Look at ~/dev/oasys/home/homeassistant/ha-sync/dashboards/welcome/00_oasis.yaml to get an idea of the types of features I use.

The `ha-sync render` CLI command is also very relevant because it similarly renders a subset of HA dashboard format in a different UI environment, 
and it covers what I use on that page (except things like maps and cameras that can't be rendered in in a CLI -- easily at least).
(OF course the CLI uses the local dashboard YAML files, while the app should use the API to fetch the dashboard state, and possibly a similar "compile dashboard to jinja template" approach to render into a format that the app can then render -- so we get all the states and visibility stuff in one go).

If it supported nativgating between dashboards and their views, that'd be cool, but I plan to create a specific dashboard just for WatchOS, managed in the web UI / iOS app, that will then render nicely on WatchOS.

Research how feasible this is, which of the cards I use could be mapped to native (or custom implemented using SwiftUI elements), etc.