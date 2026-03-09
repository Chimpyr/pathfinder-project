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
    Map["Map View\n(full-screen Leaflet.js)\nid: #map"]:::map

    %% ── Navigation Rail (left edge) ──────────────────────────────
    NavRail["Nav Rail\nid: #nav-rail\n6 buttons"]:::nav
    Map --- NavRail

    %% ── Sidebar Container ────────────────────────────────────────
    Sidebar["Sidebar\nid: #sidebar\nResizable panel"]:::nav
    NavRail --> Sidebar

    %% ── Panel: Finder ────────────────────────────────────────────
    Finder["Finder\ndata-view: finder-view\nid: #finder-view"]:::panel
    Sidebar --> Finder

    ModeToggle{"Routing Mode\n#mode-standard / #mode-loop"}:::sub
    Finder --> ModeToggle

    Standard["Standard Route\nStart + End inputs\nCoords + Weight sliders\n6 criteria: distance, greenness,\nwater, quietness, social, slope"]:::sub
    Loop["Round Trip (Loop)\nStart input only\nDistance slider (1–30 km)\nDirectional bias (N/S/E/W/none)\nVariety level (0–3)\nSmart bearings toggle"]:::sub

    ModeToggle -->|"data-mode: standard"| Standard
    ModeToggle -->|"data-mode: loop"| Loop

    AdvOpts["Advanced Options\n(shared — both modes)\nPrefer paths & trails\nPrefer paved surfaces\nPrefer lit streets\nHeavily avoid unlit"]:::detail
    Standard --> AdvOpts
    Loop --> AdvOpts

    FindBtn["Find Route Button\nid: #find-route-btn"]:::sub
    AdvOpts --> FindBtn

    %% ── Panel: Routes ────────────────────────────────────────────
    Routes["Routes\ndata-view: routes-view\nid: #routes-view"]:::panel
    Sidebar --> Routes

    RouteList["Route Candidate Cards\nDistance, scenic cost, ETA\nAccept / Reject actions\nSave route (if logged in)"]:::sub
    Routes --> RouteList

    %% ── Panel: Saved ─────────────────────────────────────────────
    Saved["Saved\ndata-view: saved-view\nid: #saved-view"]:::panel
    Sidebar --> Saved

    LoginGate{"Logged in?"}:::detail
    Saved --> LoginGate

    LoginPrompt["Sign-in prompt\nid: #saved-login-prompt"]:::detail
    LoginGate -->|"No"| LoginPrompt

    SavedTabs{"Saved Tabs\ndata-saved-tab"}:::sub
    LoginGate -->|"Yes"| SavedTabs

    Pins["Pins Tab\nid: #saved-tab-pins\nList of SavedPin items"]:::sub
    SavedRoutes["Routes Tab\nid: #saved-tab-routes\nList of SavedQuery items"]:::sub

    SavedTabs -->|"pins"| Pins
    SavedTabs -->|"routes"| SavedRoutes

    %% ── Panel: Settings ──────────────────────────────────────────
    Settings["Settings\ndata-view: settings-view\nid: #settings-view"]:::panel
    Sidebar --> Settings

    MapStyle["Map Appearance\nTile layer selector:\nOSM Standard, Carto Light,\nCarto Dark, Carto Voyager"]:::sub
    Overlays["Map Overlays\nStreet Lighting toggle\n(colour pickers, line weight)\nTile Cache visualisation toggle"]:::sub

    Settings --> MapStyle
    Settings --> Overlays

    %% ── Panel: Account ───────────────────────────────────────────
    Account["Account\ndata-view: account-view\nid: #account-view"]:::panel
    Sidebar --> Account

    AuthState{"Auth state?"}:::detail
    Account --> AuthState

    LoginForm["Login / Register forms\nid: #auth-login / #auth-register"]:::sub
    Profile["Logged-in profile\nEmail display, Logout button"]:::sub

    AuthState -->|"Not authenticated"| LoginForm
    AuthState -->|"Authenticated"| Profile

    %% ── External: Admin ──────────────────────────────────────────
    Admin["Admin Panel\nhref: /admin/\n(external link)"]:::external
    NavRail -->|"Admin button\n(opens new page)"| Admin
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
