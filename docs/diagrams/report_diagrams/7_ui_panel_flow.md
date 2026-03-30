# 7. UI Page / Panel Flow — Mermaid Reference Source

> **Note:** This diagram is a **reference artefact** for the author's manual wireframe production. It is not the final report figure — it provides an accurate structural map of the single-page UI navigation to review against the live application before producing the polished wireframe manually.

**Source:** [`app/templates/index.html`](../../app/templates/index.html)  
**Nav-rail buttons:** Lines [53–77](../../app/templates/index.html#L53)  
**View panels:** `finder-view` ([L88](../../app/templates/index.html#L88)), `routes-view` ([L497](../../app/templates/index.html#L497)), `saved-view` ([L570](../../app/templates/index.html#L570)), `settings-view` ([L648](../../app/templates/index.html#L648)), `account-view` ([L855](../../app/templates/index.html#L855))

```mermaid
flowchart TD
    classDef map fill:#009E73,stroke:#000,stroke-width:2px,color:#FFF
    classDef nav fill:#56B4E9,stroke:#000,stroke-width:2px,color:#000
    classDef panel fill:#0072B2,stroke:#000,stroke-width:2px,color:#FFF
    classDef sub fill:#E69F00,stroke:#000,stroke-width:2px,color:#000
    classDef external fill:#D55E00,stroke:#000,stroke-width:2px,color:#FFF
    classDef detail fill:#CC79A7,stroke:#000,stroke-width:2px,color:#000

    %% ── Map View (always visible background) ─────────────────────
    Map["Map View (full-screen Leaflet.js) id: #map"]:::map

    %% ── Navigation Rail (left edge) ──────────────────────────────
    NavRail["Nav Rail id: #nav-rail 6 buttons"]:::nav
    Map --- NavRail

    %% ── Sidebar Container ────────────────────────────────────────
    Sidebar["Sidebar id: #sidebar Resizable panel"]:::nav
    NavRail --> Sidebar

    %% ── Panel: Finder ────────────────────────────────────────────
    Finder["Finder data-view: finder-view id: #finder-view"]:::panel
    Sidebar --> Finder

    ModeToggle{"Routing Mode #mode-standard / #mode-loop"}:::sub
    Finder --> ModeToggle

    Standard["Standard Route Start + End inputs Coords + Weight sliders 6 criteria: distance, greenness, water, quietness, social, slope"]:::sub
    Loop["Round Trip (Loop) Start input only Distance slider (1–30 km) Directional bias (N/S/E/W/none) Variety level (0–3) Smart bearings toggle"]:::sub

    ModeToggle -->|"data-mode: standard"| Standard
    ModeToggle -->|"data-mode: loop"| Loop

    AdvOpts["Advanced Options (shared — both modes) Prefer paths & trails Prefer paved surfaces Prefer lit streets Heavily avoid unlit"]:::detail
    Standard --> AdvOpts
    Loop --> AdvOpts

    FindBtn["Find Route Button id: #find-route-btn"]:::sub
    AdvOpts --> FindBtn

    %% ── Panel: Routes ────────────────────────────────────────────
    Routes["Routes data-view: routes-view id: #routes-view"]:::panel
    Sidebar --> Routes

    RouteList["Route Candidate Cards Distance, scenic cost, ETA Accept / Reject actions Save route (if logged in)"]:::sub
    Routes --> RouteList

    %% ── Panel: Saved ─────────────────────────────────────────────
    Saved["Saved data-view: saved-view id: #saved-view"]:::panel
    Sidebar --> Saved

    LoginGate{"Logged in?"}:::detail
    Saved --> LoginGate

    LoginPrompt["Sign-in prompt id: #saved-login-prompt"]:::detail
    LoginGate -->|"No"| LoginPrompt

    SavedTabs{"Saved Tabs data-saved-tab"}:::sub
    LoginGate -->|"Yes"| SavedTabs

    Pins["Pins Tab id: #saved-tab-pins List of SavedPin items"]:::sub
    SavedRoutes["Routes Tab id: #saved-tab-routes List of SavedQuery items"]:::sub

    SavedTabs -->|"pins"| Pins
    SavedTabs -->|"routes"| SavedRoutes

    %% ── Panel: Settings ──────────────────────────────────────────
    Settings["Settings data-view: settings-view id: #settings-view"]:::panel
    Sidebar --> Settings

    MapStyle["Map Appearance Tile layer selector: OSM Standard, Carto Light, Carto Dark, Carto Voyager"]:::sub
    Overlays["Map Overlays Street Lighting toggle (colour pickers, line weight) Tile Cache visualisation toggle"]:::sub

    Settings --> MapStyle
    Settings --> Overlays

    %% ── Panel: Account ───────────────────────────────────────────
    Account["Account data-view: account-view id: #account-view"]:::panel
    Sidebar --> Account

    AuthState{"Auth state?"}:::detail
    Account --> AuthState

    LoginForm["Login / Register forms id: #auth-login / #auth-register"]:::sub
    Profile["Logged-in profile Email display, Logout button"]:::sub

    AuthState -->|"Not authenticated"| LoginForm
    AuthState -->|"Authenticated"| Profile

    %% ── External: Admin ──────────────────────────────────────────
    Admin["Admin Panel href: /admin/ (external link)"]:::external
    NavRail -->|"Admin button (opens new page)"| Admin
```

## Cross-Reference: `data-view` IDs

| Nav Button | `data-view`           | Panel `id`         | HTML Line |
| ---------- | --------------------- | ------------------ | --------- |
| Finder     | `finder-view`         | `#finder-view`     | L88       |
| Routes     | `routes-view`         | `#routes-view`     | L497      |
| Saved      | `saved-view`          | `#saved-view`      | L570      |
| Settings   | `settings-view`       | `#settings-view`   | L648      |
| Account    | `account-view`        | `#account-view`    | L855      |
| Admin      | _(none — `<a href>`)_ | External `/admin/` | L76       |
