/**
 * Shared State Management
 */

// Geocoding / Location State
export const startState = {
  lat: null,
  lon: null,
  address: null,
  isGeocoding: false,
};
export const endState = {
  lat: null,
  lon: null,
  address: null,
  isGeocoding: false,
};

// Multi-route state (Standard Mode)
export const routeState = {
  routes: null, // API response data
  selected: "balanced", // Currently highlighted route type
  visibility: {
    baseline: true,
    extremist: true,
    balanced: true,
  },
  duplicates: {}, // Track duplicate routes
};

// Multi-loop state (Round Trip Mode)
export const loopState = {
  loops: null,
  selectedId: null,
  visibility: {},
  demoPayload: null,
  demoStartPoint: null,
};

// Application Mode
export let appState = {
  routingMode: "standard", // 'standard' or 'loop'
  selectedDirection: "none",
  loopDemoMode: false,
};

/**
 * Reset route and loop state.
 */
export function resetRouteState() {
  routeState.routes = null;
  routeState.selected = "balanced";
  routeState.visibility = { baseline: true, extremist: true, balanced: true };
  routeState.duplicates = {};

  loopState.loops = null;
  loopState.selectedId = null;
  loopState.visibility = {};
  loopState.demoPayload = null;
  loopState.demoStartPoint = null;

  // Note: UI updates should be handled by the caller/subscribers
}

export function setRoutingMode(mode) {
  appState.routingMode = mode;
}

export function setSelectedDirection(direction) {
  appState.selectedDirection = direction;
}

export function setLoopDemoMode(enabled) {
  appState.loopDemoMode = Boolean(enabled);
}
