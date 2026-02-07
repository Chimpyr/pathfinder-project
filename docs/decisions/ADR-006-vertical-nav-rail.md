# ADR-006: Vertical Navigation Rail with Collapsible Sidebar

**Status:** Accepted  
**Date:** 2026-02-07  

---

## Context

The application's UI consisted of a fixed sidebar containing the route-finding form and a map. As the feature set expands (statistics, settings, admin), a more scalable navigation pattern was needed that:

1. Allows quick switching between different feature views
2. Keeps the map visible across all views
3. Maximises map space when the sidebar isn't needed

---

## Decision

Implement a Google Maps-style vertical navigation rail with three key capabilities:

### 1. Navigation Rail

A narrow vertical rail (72px) adjacent to the sidebar containing icon buttons for:
- Routes (default)
- Stats (placeholder)
- Settings (placeholder)
- Admin (links to `/admin/`)

**Rationale:** Icon-based navigation is space-efficient and familiar from Google Maps, VS Code, and Slack.

### 2. Collapsible Panel

A chevron toggle at the top of the rail that collapses both nav rail and sidebar together:

```css
#left-panel.collapsed {
    position: absolute;
    transform: translateX(-100%);
    width: 0;
    pointer-events: none;
}
```

A floating expand button appears on the left edge when collapsed.

**Rationale:** Users exploring the map often want maximum screen space. A single toggle is simpler than separate controls.

### 3. Resizable Sidebar

Drag handle on sidebar's right edge for width adjustment (280px–600px):

```javascript
const MIN_SIDEBAR_WIDTH = 280;
const MAX_SIDEBAR_WIDTH = 600;
```

**Rationale:** Different users have different preferences. Wider sidebars show more route details; narrower ones show more map.

---

## State Persistence

All UI states persist in localStorage with a save-on-change, restore-on-load pattern:

| Key | Value |
|-----|-------|
| `selectedView` | Active view panel ID |
| `panelCollapsed` | Boolean |
| `sidebarWidth` | Pixel integer |

### Selected View

```javascript
// On view switch - save
function switchView(viewId) {
    // ... toggle active states ...
    localStorage.setItem('selectedView', viewId);
}

// On page load - restore
const savedView = localStorage.getItem('selectedView');
if (savedView && document.getElementById(savedView)) {
    switchView(savedView);
}
```

### Collapsed State

```javascript
// On toggle - save
function togglePanelCollapse() {
    const isCollapsed = leftPanel.classList.toggle('collapsed');
    localStorage.setItem('panelCollapsed', isCollapsed);
}

// On page load - restore
const savedCollapsed = localStorage.getItem('panelCollapsed') === 'true';
if (savedCollapsed && leftPanel) {
    leftPanel.classList.add('collapsed');
    expandPanelBtn.classList.remove('hidden');
}
```

### Sidebar Width

```javascript
// After resize finishes - save
function stopResize() {
    const currentWidth = sidebarEl.offsetWidth;
    localStorage.setItem('sidebarWidth', currentWidth);
}

// On page load - restore
const savedWidth = localStorage.getItem('sidebarWidth');
if (savedWidth && sidebarEl) {
    const width = parseInt(savedWidth, 10);
    if (width >= MIN_SIDEBAR_WIDTH && width <= MAX_SIDEBAR_WIDTH) {
        sidebarEl.style.width = `${width}px`;
    }
}
```

**Rationale:** Users expect their layout preferences to survive page refreshes.

---

## Responsive Behaviour

| Viewport | Nav Rail | Sidebar | Collapse |
|----------|----------|---------|----------|
| Desktop (≥1024px) | Vertical, labels | Full width | Available |
| Tablet (768–1023px) | Compact icons | Narrower | Available |
| Mobile (<768px) | Bottom bar | Full overlay | Disabled |

---

## Consequences

### Positive

- Scalable navigation for future features
- Users control their map vs. UI balance
- Preferences persist across sessions
- No breaking changes to existing route functionality

### Negative

- Added 170+ lines of CSS, 140+ lines of JS
- More DOM elements increase page weight slightly

---

## Files Modified

| File | Changes |
|------|---------|
| `templates/index.html` | Added nav rail, view panels, resize handle |
| `static/css/style.css` | Nav rail, collapse, resize styles |
| `static/js/main.js` | View switching, collapse/expand, resize logic |

---

## References

- [Material Design Navigation Rail](https://m3.material.io/components/navigation-rail)
- [Google Maps UI Patterns](https://www.google.com/maps)
