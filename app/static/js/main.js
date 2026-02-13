/**
 * Main Application JavaScript
 *
 * Handles dual-input mode: text addresses AND map click coordinates.
 * Features instant geocoding preview when typing addresses.
 *
 * @author ScenicPathFinder
 */

// ============================================================================
// Theme Toggle Logic
// ============================================================================
const themeToggle = document.getElementById("theme-toggle");
const html = document.documentElement;

if (
  localStorage.theme === "dark" ||
  (!("theme" in localStorage) &&
    window.matchMedia("(prefers-color-scheme: dark)").matches)
) {
  html.classList.add("dark");
} else {
  html.classList.remove("dark");
}

themeToggle.addEventListener("click", () => {
  html.classList.toggle("dark");
  localStorage.theme = html.classList.contains("dark") ? "dark" : "light";
});

// ============================================================================
// UI Element References
// ============================================================================
const routeForm = document.getElementById("route-form");
const startInput = document.getElementById("start-input");
const endInput = document.getElementById("end-input");
const startCoordsDisplay = document.getElementById("start-coords");
const endCoordsDisplay = document.getElementById("end-coords");
const clearStartBtn = document.getElementById("clear-start");
const clearEndBtn = document.getElementById("clear-end");
const clearAllBtn = document.getElementById("clear-all-btn");
const findRouteBtn = document.getElementById("find-route-btn");
const btnText = document.getElementById("btn-text");
const btnSpinner = document.getElementById("btn-spinner");
const errorMsg = document.getElementById("error-message");
const routeStats = document.getElementById("route-stats");
const statDistance = document.getElementById("stat-distance");
const statTime = document.getElementById("stat-time");
const statPace = document.getElementById("stat-pace");
const debugInfo = document.getElementById("debug-info");
const debugContent = document.getElementById("debug-content");
const instructionBanner = document.getElementById("instruction-banner");
const instructionText = document.getElementById("instruction-text");

// Scenic routing preferences
const useScenicToggle = document.getElementById("use-scenic-routing");
const scenicSliders = document.getElementById("scenic-sliders");
const weightQuietness = document.getElementById("weight-quietness");
const weightGreenness = document.getElementById("weight-greenness");
const weightWater = document.getElementById("weight-water");
const weightSocial = document.getElementById("weight-social");
const weightFlatness = document.getElementById("weight-flatness");
const weightDistance = document.getElementById("weight-distance");
const weightNature = document.getElementById("weight-nature");
const groupNatureToggle = document.getElementById("group-nature-toggle");

// Loop/Round Trip mode elements
const modeStandardBtn = document.getElementById("mode-standard");
const modeLoopBtn = document.getElementById("mode-loop");
const endLocationGroup = document.getElementById("end-location-group");
const loopDistanceGroup = document.getElementById("loop-distance-group");
const loopDistanceSlider = document.getElementById("loop-distance-slider");
const loopDistanceValue = document.getElementById("loop-distance-value");
const longLoopWarning = document.getElementById("long-loop-warning");
const longLoopWarningText = document.getElementById("long-loop-warning-text");
const directionalBiasControl = document.getElementById(
  "directional-bias-control",
);
const preferPedestrianToggle = document.getElementById(
  "prefer-pedestrian-toggle",
);
const preferPavedToggle = document.getElementById("prefer-paved-toggle");
const preferLitToggle = document.getElementById("prefer-lit-toggle");
const avoidUnsafeToggle = document.getElementById("avoid-unsafe-toggle");
const varietyLevelSlider = document.getElementById("variety-level-slider");
const varietyLevelValue = document.getElementById("variety-level-value");

// Routing mode state: 'standard' or 'loop'
let routingMode = "standard";
let selectedDirection = "none";

// ============================================================================
// Route Variety Slider Handler
// ============================================================================
if (varietyLevelSlider && varietyLevelValue) {
  const varietyLabels = ["Off", "Low", "Med", "High"];
  varietyLevelSlider.addEventListener("input", () => {
    const level = parseInt(varietyLevelSlider.value);
    varietyLevelValue.textContent = varietyLabels[level] || level;
  });
}

// ============================================================================
// Scenic Routing Toggle Handler
// ============================================================================
useScenicToggle.addEventListener("change", () => {
  const enabled = useScenicToggle.checked;
  if (enabled) {
    scenicSliders.classList.remove("opacity-50", "pointer-events-none");
  } else {
    scenicSliders.classList.add("opacity-50", "pointer-events-none");
  }
});

// Slider value display updates (only for range inputs)
[
  weightDistance,
  weightQuietness,
  weightGreenness,
  weightWater,
  weightNature,
].forEach((slider) => {
  if (slider) {
    slider.addEventListener("input", () => {
      const valueSpan = document.getElementById(`${slider.id}-value`);
      if (valueSpan) valueSpan.textContent = slider.value;
    });
  }
});

// ============================================================================
// Group Nature Toggle Handler
// ============================================================================
if (groupNatureToggle) {
  groupNatureToggle.addEventListener("change", () => {
    const grouped = groupNatureToggle.checked;
    const greeneryGroup = document.getElementById("greenery-slider-group");
    const waterGroup = document.getElementById("water-slider-group");
    const natureGroup = document.getElementById("nature-slider-group");

    if (grouped) {
      // Hide individual Greenery + Water sliders, show Nature slider
      if (greeneryGroup) greeneryGroup.classList.add("hidden");
      if (waterGroup) waterGroup.classList.add("hidden");
      if (natureGroup) natureGroup.classList.remove("hidden");
    } else {
      // Show individual Greenery + Water sliders, hide Nature slider
      if (greeneryGroup) greeneryGroup.classList.remove("hidden");
      if (waterGroup) waterGroup.classList.remove("hidden");
      if (natureGroup) natureGroup.classList.add("hidden");
    }

    console.log(`[App] Group Nature: ${grouped ? "ON" : "OFF"}`);
  });
}

// ============================================================================
// Routing Mode Toggle (Standard / Round Trip)
// ============================================================================

/**
 * Switch routing mode between 'standard' and 'loop'.
 * @param {string} mode - 'standard' or 'loop'
 */
function setRoutingMode(mode) {
  routingMode = mode;

  // Update button active states
  if (mode === "standard") {
    modeStandardBtn.classList.add("active");
    modeLoopBtn.classList.remove("active");
    endLocationGroup.classList.remove("hidden");
    loopDistanceGroup.classList.add("hidden");
    btnText.textContent = "Find Route";
  } else {
    modeStandardBtn.classList.remove("active");
    modeLoopBtn.classList.add("active");
    endLocationGroup.classList.add("hidden");
    loopDistanceGroup.classList.remove("hidden");
    btnText.textContent = "Find Loop";
  }

  // Update instruction banner for the mode
  updateInstructions();

  console.log(`[App] Routing mode: ${mode}`);
}

// Mode toggle button click handlers
if (modeStandardBtn) {
  modeStandardBtn.addEventListener("click", () => setRoutingMode("standard"));
}
if (modeLoopBtn) {
  modeLoopBtn.addEventListener("click", () => setRoutingMode("loop"));
}

// ============================================================================
// Loop Distance Slider Handler
// ============================================================================

/**
 * Update loop distance warning tier based on slider value.
 * Tiers: 15-20km amber, 20-25km orange, 25-30km red.
 */
function updateLoopDistanceWarning(distanceKm) {
  if (!longLoopWarning) return;

  if (distanceKm > 25) {
    longLoopWarning.classList.remove("hidden");
    longLoopWarning.className =
      "p-3 rounded-lg border transition-all loop-warning-red";
    longLoopWarningText.innerHTML =
      "<strong>Very long route!</strong> Distances over 25 km will take significantly longer and may timeout.";
  } else if (distanceKm > 20) {
    longLoopWarning.classList.remove("hidden");
    longLoopWarning.className =
      "p-3 rounded-lg border transition-all loop-warning-orange";
    longLoopWarningText.innerHTML =
      "<strong>Long route.</strong> Distances over 20 km may take longer to calculate.";
  } else if (distanceKm > 15) {
    longLoopWarning.classList.remove("hidden");
    longLoopWarning.className =
      "p-3 rounded-lg border transition-all loop-warning-amber";
    longLoopWarningText.textContent =
      "Routes over 15 km may take longer to calculate.";
  } else {
    longLoopWarning.classList.add("hidden");
  }
}

if (loopDistanceSlider) {
  loopDistanceSlider.addEventListener("input", () => {
    const val = parseFloat(loopDistanceSlider.value);
    loopDistanceValue.textContent = `${val.toFixed(1)} km`;
    updateLoopDistanceWarning(val);
  });
}

// ============================================================================
// Directional Bias Compass Handlers
// ============================================================================

const directionBtns = document.querySelectorAll(".direction-btn");

directionBtns.forEach((btn) => {
  btn.addEventListener("click", () => {
    // Remove active from all
    directionBtns.forEach((b) => {
      b.classList.remove("active");
    });

    // Set active on clicked button
    btn.classList.add("active");
    selectedDirection = btn.dataset.direction;

    console.log(`[App] Direction bias: ${selectedDirection}`);
  });
});

// ============================================================================
// Cached Tiles Debug Toggle Handler
// ============================================================================
const showCachedTilesToggle = document.getElementById("show-cached-tiles");
const tileCountSpan = document.getElementById("tile-count");

// Track tiles used in the current route for highlighting
let routeUsedTileIds = [];

/**
 * Refresh the tile overlay display.
 * Called when toggle is checked or after route completion.
 */
async function refreshTileOverlay() {
  if (!showCachedTilesToggle || !showCachedTilesToggle.checked) {
    return;
  }

  try {
    const response = await fetch("/api/cached-tiles");
    const data = await response.json();

    if (data.tiles && data.tiles.length > 0) {
      // Pass highlighted tiles (used in current route)
      mapController.displayCachedTiles(data.tiles, routeUsedTileIds);

      const usedCount = routeUsedTileIds.length;
      tileCountSpan.textContent =
        usedCount > 0
          ? `(${data.tiles.length} cached, ${usedCount} used)`
          : `(${data.tiles.length} tiles, ${data.tile_size_km}km)`;
    } else {
      tileCountSpan.textContent = "(no tiles cached)";
      mapController.clearTileLayers();
    }
  } catch (err) {
    console.error("Failed to fetch cached tiles:", err);
    tileCountSpan.textContent = "(error)";
  }
}

if (showCachedTilesToggle) {
  showCachedTilesToggle.addEventListener("change", async () => {
    if (showCachedTilesToggle.checked) {
      await refreshTileOverlay();
    } else {
      // Hide tiles
      mapController.clearTileLayers();
      tileCountSpan.textContent = "";
    }
  });

  // Initial check (handles soft reloads where browser keeps checkbox state)
  if (showCachedTilesToggle.checked) {
    refreshTileOverlay();
  }
}

/**
 * Get scenic weights from sliders and toggles.
 * Sliders use 0-5 scale, toggles use 0 (off) or 5 (max).
 * Returns null if scenic routing is disabled.
 */
function getScenicWeights() {
  if (!useScenicToggle.checked) return null;

  const isNatureGrouped = groupNatureToggle && groupNatureToggle.checked;

  let greennessVal, waterVal;

  if (isNatureGrouped) {
    // Group Nature ON: use Nature slider for greenness, set water to 0
    greennessVal = parseInt(weightNature.value);
    waterVal = 0;
  } else {
    // Group Nature OFF: use individual sliders
    greennessVal = parseInt(weightGreenness.value);
    waterVal = parseInt(weightWater.value);
  }

  // Social and Flat are toggles: checked = 5 (max), unchecked = 0
  const socialVal = weightSocial && weightSocial.checked ? 5 : 0;
  const slopeVal = weightFlatness && weightFlatness.checked ? 5 : 0;

  return {
    distance: parseInt(weightDistance.value),
    quietness: parseInt(weightQuietness.value),
    greenness: greennessVal,
    water: waterVal,
    social: socialVal,
    slope: slopeVal,
  };
}

// ============================================================================
// State Management
// ============================================================================
let startState = { lat: null, lon: null, address: null, isGeocoding: false };
let endState = { lat: null, lon: null, address: null, isGeocoding: false };

// Multi-route state
let routeState = {
  routes: null, // API response data (multi-route mode)
  selected: "balanced", // Currently highlighted route type
  visibility: {
    baseline: true,
    extremist: true,
    balanced: true,
  },
};

// Multi-loop state
let loopState = {
  loops: null,
  selected: null,
  visibility: {},
};

// Route display names and colours
const ROUTE_CONFIG = {
  baseline: {
    name: "Baseline",
    subtitle: "Shortest",
    colour: "#6B7280",
    icon: "📏",
  },
  extremist: {
    name: "Extremist",
    subtitle: "Max Scenic",
    colour: "#EF4444",
    icon: "🌿",
  },
  balanced: {
    name: "Balanced",
    subtitle: "Your Mix",
    colour: "#3B82F6",
    icon: "⚖️",
  },
};

// Debounce timers
let startGeocodeTimer = null;
let endGeocodeTimer = null;
const GEOCODE_DEBOUNCE_MS = 800;

/**
 * Format coordinates for display.
 */
function formatCoords(lat, lon) {
  return `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
}

/**
 * Update instruction banner based on current state and routing mode.
 */
function updateInstructions() {
  const hasStart = startState.lat !== null;
  const hasEnd = endState.lat !== null;

  if (startState.isGeocoding || endState.isGeocoding) {
    instructionBanner.classList.remove("hidden");
    instructionText.innerHTML =
      '<i class="fas fa-spinner fa-spin mr-1"></i> Looking up address...';
    instructionBanner.className =
      "mx-6 mt-4 p-3 bg-yellow-50 dark:bg-yellow-900/30 border border-yellow-200 dark:border-yellow-800 rounded-lg";
  } else if (routingMode === "loop") {
    // Loop mode: only need start point
    if (!hasStart) {
      instructionBanner.classList.remove("hidden");
      instructionText.innerHTML =
        '<i class="fas fa-sync-alt mr-1"></i> Set your <strong>starting point</strong> for the loop (type or click map)';
      instructionBanner.className =
        "mx-6 mt-4 p-3 bg-blue-50 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-800 rounded-lg";
    } else {
      instructionBanner.classList.remove("hidden");
      instructionText.innerHTML =
        '<i class="fas fa-check-circle mr-1 text-green-500"></i> Start set! Adjust distance & direction, then click <strong>Find Loop</strong>';
      instructionBanner.className =
        "mx-6 mt-4 p-3 bg-green-50 dark:bg-green-900/30 border border-green-200 dark:border-green-800 rounded-lg";
    }
  } else if (!hasStart && !hasEnd) {
    instructionBanner.classList.remove("hidden");
    instructionText.innerHTML =
      "Type addresses below or click the map to set points";
    instructionBanner.className =
      "mx-6 mt-4 p-3 bg-blue-50 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-800 rounded-lg";
  } else if (hasStart && !hasEnd) {
    instructionBanner.classList.remove("hidden");
    instructionText.innerHTML =
      "Now set your <strong>end point</strong> (type or click)";
    instructionBanner.className =
      "mx-6 mt-4 p-3 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-lg";
  } else if (!hasStart && hasEnd) {
    instructionBanner.classList.remove("hidden");
    instructionText.innerHTML =
      "Now set your <strong>start point</strong> (type or click)";
    instructionBanner.className =
      "mx-6 mt-4 p-3 bg-green-50 dark:bg-green-900/30 border border-green-200 dark:border-green-800 rounded-lg";
  } else {
    // Both points set - hide banner as it's no longer needed
    instructionBanner.classList.add("hidden");
    return;
  }
}

/**
 * Show/hide clear buttons based on input content.
 */
function updateClearButtons() {
  clearStartBtn.classList.toggle("hidden", !startInput.value);
  clearEndBtn.classList.toggle("hidden", !endInput.value);
}

/**
 * Update coordinate display below inputs.
 */
function updateCoordsDisplay() {
  if (startState.lat !== null) {
    startCoordsDisplay.textContent = `📍 ${formatCoords(startState.lat, startState.lon)}`;
    startCoordsDisplay.classList.remove("hidden");
  } else {
    startCoordsDisplay.classList.add("hidden");
  }

  if (endState.lat !== null) {
    endCoordsDisplay.textContent = `📍 ${formatCoords(endState.lat, endState.lon)}`;
    endCoordsDisplay.classList.remove("hidden");
  } else {
    endCoordsDisplay.classList.add("hidden");
  }
}

// ============================================================================
// Debug Edge Preview Rendering
// ============================================================================

/**
 * Render edge preview in debug info panel.
 *
 * Shows first 5 edges with their feature values prominently,
 * using emoji indicators and a compact grid layout.
 *
 * @param {Array} edges - Array of edge feature objects from API.
 */
function renderEdgePreview(edges) {
  const container = document.getElementById("edge-preview-container");
  if (!container || !edges || edges.length === 0) {
    if (container) container.classList.add("hidden");
    return;
  }

  let html =
    '<h5 class="font-semibold mb-2 text-gray-700 dark:text-gray-300">Edge Features (First 5):</h5>';
  html += '<div class="space-y-3">';

  edges.forEach((edge, idx) => {
    // Determine gradient direction indicator
    let gradientIcon = "➡️";
    if (edge.uphill_gradient > 1) gradientIcon = "⬆️";
    else if (edge.downhill_gradient > 1) gradientIcon = "⬇️";

    // Format elevation change
    const elevChange =
      edge.to_elevation && edge.from_elevation
        ? (edge.to_elevation - edge.from_elevation).toFixed(1)
        : null;
    const elevSign = elevChange > 0 ? "+" : "";

    html += `
            <div class="p-3 bg-white dark:bg-gray-700 rounded-lg border border-gray-200 dark:border-gray-600 shadow-sm">
                <!-- Header: Edge number, highway type, length -->
                <div class="flex justify-between items-center mb-2 pb-2 border-b border-gray-100 dark:border-gray-600">
                    <span class="font-semibold text-sm text-gray-800 dark:text-gray-200">#${idx + 1} ${edge.highway}</span>
                    <span class="text-xs text-gray-500 dark:text-gray-400">${edge.length_m}m</span>
                </div>
                
                <!-- Normalised Scores (0-1, lower = better) -->
                <div class="mb-2">
                    <div class="text-xs text-gray-500 dark:text-gray-400 mb-1">Normalised Scores (0=best, 1=worst):</div>
                    <div class="grid grid-cols-5 gap-2 text-xs">
                        <div class="text-center" title="Greenness (0=green)">
                            <span class="text-green-600 dark:text-green-400">🌿</span>
                            <div class="font-mono ${edge.norm_green !== null && edge.norm_green < 0.3 ? "text-green-600 font-bold" : ""}">${edge.norm_green ?? "-"}</div>
                        </div>
                        <div class="text-center" title="Water proximity (0=near)">
                            <span class="text-blue-600 dark:text-blue-400">💧</span>
                            <div class="font-mono ${edge.norm_water !== null && edge.norm_water < 0.3 ? "text-blue-600 font-bold" : ""}">${edge.norm_water ?? "-"}</div>
                        </div>
                        <div class="text-center" title="Social/POIs (0=near)">
                            <span class="text-amber-600 dark:text-amber-400">🏛️</span>
                            <div class="font-mono ${edge.norm_social !== null && edge.norm_social < 0.3 ? "text-amber-600 font-bold" : ""}">${edge.norm_social ?? "-"}</div>
                        </div>
                        <div class="text-center" title="Quietness (0=quiet)">
                            <span class="text-purple-600 dark:text-purple-400">🔇</span>
                            <div class="font-mono ${edge.norm_quiet !== null && edge.norm_quiet < 0.3 ? "text-purple-600 font-bold" : ""}">${edge.norm_quiet ?? "-"}</div>
                        </div>
                        <div class="text-center" title="Slope difficulty (0=easy)">
                            <span class="text-red-600 dark:text-red-400">⛰️</span>
                            <div class="font-mono ${edge.norm_slope !== null && edge.norm_slope < 0.3 ? "text-red-600 font-bold" : ""}">${edge.norm_slope ?? "-"}</div>
                        </div>
                    </div>
                </div>
                
                <!-- Elevation Data -->
                <div class="pt-2 border-t border-gray-100 dark:border-gray-600">
                    <div class="text-xs text-gray-500 dark:text-gray-400 mb-1">Elevation:</div>
                    <div class="flex justify-between text-xs">
                        <span title="From → To elevation">
                            ${gradientIcon} ${edge.from_elevation ?? "?"}m → ${edge.to_elevation ?? "?"}m
                            ${elevChange !== null ? `<span class="${elevChange > 0 ? "text-red-500" : "text-green-500"}">(${elevSign}${elevChange}m)</span>` : ""}
                        </span>
                        <span title="Tobler cost (1.0=flat, >1=slower)" class="font-mono ${edge.slope_time_cost > 1.2 ? "text-red-500 font-bold" : edge.slope_time_cost < 0.95 ? "text-green-500 font-bold" : ""}">
                            ⏱️ ${edge.slope_time_cost ?? "1.0"}×
                        </span>
                    </div>
                </div>
            </div>
        `;
  });

  html += "</div>";
  container.innerHTML = html;
  container.classList.remove("hidden");
}

// ============================================================================
// Geocoding Functions
// ============================================================================

/**
 * Geocode an address and place marker.
 * @param {string} address - The address to geocode.
 * @param {string} type - 'start' or 'end'.
 */
async function geocodeAddress(address, type) {
  if (!address || address.length < 3) return;

  // Check if it looks like coordinates already
  if (address.match(/^-?\d+\.\d+,\s*-?\d+\.\d+$/)) return;

  const state = type === "start" ? startState : endState;
  state.isGeocoding = true;
  updateInstructions();

  try {
    const response = await fetch("/api/geocode", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ address }),
    });

    const data = await response.json();

    if (response.ok && data.lat && data.lon) {
      // Update state
      state.lat = data.lat;
      state.lon = data.lon;
      state.address = address;

      // Place marker on map
      if (type === "start") {
        mapController.setStartPoint(data.lat, data.lon);
      } else {
        mapController.setEndPoint(data.lat, data.lon);
      }

      console.log(
        `[Geocode] ${type}: '${address}' -> ${data.lat}, ${data.lon}`,
      );
    } else {
      console.warn(`[Geocode] Failed for ${type}: ${data.error}`);
    }
  } catch (err) {
    console.error(`[Geocode] Error for ${type}:`, err);
  } finally {
    state.isGeocoding = false;
    updateInstructions();
    updateCoordsDisplay();
  }
}

/**
 * Debounced geocode for start input.
 */
function debounceStartGeocode() {
  if (startGeocodeTimer) clearTimeout(startGeocodeTimer);
  startGeocodeTimer = setTimeout(() => {
    geocodeAddress(startInput.value.trim(), "start");
  }, GEOCODE_DEBOUNCE_MS);
}

/**
 * Debounced geocode for end input.
 */
function debounceEndGeocode() {
  if (endGeocodeTimer) clearTimeout(endGeocodeTimer);
  endGeocodeTimer = setTimeout(() => {
    geocodeAddress(endInput.value.trim(), "end");
  }, GEOCODE_DEBOUNCE_MS);
}

// ============================================================================
// Map Controller Initialisation
// ============================================================================
const mapController = new MapController("map", {
  center: [51.4545, -2.5879], // Bristol
  zoom: 13,

  onStartSet: (lat, lon) => {
    startState = { lat, lon, address: null, isGeocoding: false };
    // Only update input if it's currently empty or contains coords
    if (
      !startInput.value ||
      startInput.value.match(/^-?\d+\.\d+,\s*-?\d+\.\d+$/)
    ) {
      startInput.value = formatCoords(lat, lon);
    }
    updateClearButtons();
    updateCoordsDisplay();
    updateInstructions();
  },

  onEndSet: (lat, lon) => {
    endState = { lat, lon, address: null, isGeocoding: false };
    if (!endInput.value || endInput.value.match(/^-?\d+\.\d+,\s*-?\d+\.\d+$/)) {
      endInput.value = formatCoords(lat, lon);
    }
    updateClearButtons();
    updateCoordsDisplay();
    updateInstructions();
  },

  onMarkersReady: () => {
    updateInstructions();
  },

  onMarkersCleared: () => {
    startState = { lat: null, lon: null, address: null, isGeocoding: false };
    endState = { lat: null, lon: null, address: null, isGeocoding: false };
    startInput.value = "";
    endInput.value = "";
    updateClearButtons();
    updateCoordsDisplay();
    updateInstructions();
    routeStats.classList.add("hidden");
    errorMsg.classList.add("hidden");
    resetRouteState();
  },
});

// ============================================================================
// Text Input Handlers - Debounced Geocoding
// ============================================================================
startInput.addEventListener("input", () => {
  updateClearButtons();
  const value = startInput.value.trim();

  if (!value) {
    // Cleared input - reset state
    startState = { lat: null, lon: null, address: null, isGeocoding: false };
    if (mapController.startMarker) {
      mapController.map.removeLayer(mapController.startMarker);
      mapController.startMarker = null;
    }
    updateCoordsDisplay();
    updateInstructions();
  } else if (!value.match(/^-?\d+\.\d+,\s*-?\d+\.\d+$/)) {
    // User typed an address - trigger debounced geocode
    debounceStartGeocode();
  }
});

endInput.addEventListener("input", () => {
  updateClearButtons();
  const value = endInput.value.trim();

  if (!value) {
    endState = { lat: null, lon: null, address: null, isGeocoding: false };
    if (mapController.endMarker) {
      mapController.map.removeLayer(mapController.endMarker);
      mapController.endMarker = null;
    }
    updateCoordsDisplay();
    updateInstructions();
  } else if (!value.match(/^-?\d+\.\d+,\s*-?\d+\.\d+$/)) {
    debounceEndGeocode();
  }
});

// ============================================================================
// Clear Button Handlers
// ============================================================================
clearStartBtn.addEventListener("click", () => {
  startInput.value = "";
  startState = { lat: null, lon: null, address: null, isGeocoding: false };
  if (mapController.startMarker) {
    mapController.map.removeLayer(mapController.startMarker);
    mapController.startMarker = null;
  }
  updateClearButtons();
  updateCoordsDisplay();
  updateInstructions();
});

clearEndBtn.addEventListener("click", () => {
  endInput.value = "";
  endState = { lat: null, lon: null, address: null, isGeocoding: false };
  if (mapController.endMarker) {
    mapController.map.removeLayer(mapController.endMarker);
    mapController.endMarker = null;
  }
  updateClearButtons();
  updateCoordsDisplay();
  updateInstructions();
});

clearAllBtn.addEventListener("click", () => {
  mapController.clear();
});

// ============================================================================
// Form Submission Handler
// ============================================================================
routeForm.addEventListener("submit", async (e) => {
  e.preventDefault();

  // Dispatch to correct handler based on routing mode
  if (routingMode === "loop") {
    await handleLoopSubmit();
  } else {
    await handleStandardSubmit();
  }
});

/**
 * Handle standard (A-to-B) route submission.
 */
async function handleStandardSubmit() {
  // Validate that we have coordinates for both points
  if (!startState.lat || !endState.lat) {
    errorMsg.textContent = "Please set both start and end locations.";
    errorMsg.classList.remove("hidden");
    return;
  }

  // Build request payload - always use coordinates now
  const payload = {
    start_lat: startState.lat,
    start_lon: startState.lon,
    end_lat: endState.lat,
    end_lon: endState.lon,
  };

  // Add scenic routing weights if enabled
  const scenicWeights = getScenicWeights();
  if (scenicWeights) {
    payload.use_wsm = true;
    payload.weights = scenicWeights;

    // Add combine_nature flag if Group Nature is enabled
    if (groupNatureToggle && groupNatureToggle.checked) {
      payload.combine_nature = true;
    }

    console.log(
      "[App] Scenic routing enabled with weights:",
      scenicWeights,
      "combine_nature:",
      !!payload.combine_nature,
    );
  }

  // UI Loading State
  setLoadingState("Calculating...");

  try {
    const response = await fetch("/api/route", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify(payload),
    });

    const data = await response.json();

    // Handle async processing (202 Accepted)
    if (response.status === 202 && data.status === "processing") {
      console.log("[App] Graph building in progress, starting polling...");
      await pollForTaskCompletion(data.task_id, payload);
      return;
    }

    // Handle sync success (200 OK)
    if (response.ok) {
      handleRouteSuccess(data);
    } else {
      errorMsg.textContent = data.error || "An error occurred.";
      errorMsg.classList.remove("hidden");
    }
  } catch (err) {
    console.error("[App] Network error:", err);
    errorMsg.textContent = "Network error. Please try again.";
    errorMsg.classList.remove("hidden");
  } finally {
    clearLoadingState();
  }
}

/**
 * Handle loop/round-trip route submission.
 */
async function handleLoopSubmit() {
  // Loop mode only needs start point
  if (!startState.lat) {
    errorMsg.textContent = "Please set a starting location for your loop.";
    errorMsg.classList.remove("hidden");
    return;
  }

  const distanceKm = parseFloat(loopDistanceSlider.value);

  // Build loop request payload
  const payload = {
    start_lat: startState.lat,
    start_lon: startState.lon,
    distance_km: distanceKm,
    directional_bias: selectedDirection,
    variety_level: varietyLevelSlider ? parseInt(varietyLevelSlider.value) : 0,
    prefer_pedestrian: preferPedestrianToggle
      ? preferPedestrianToggle.checked
      : false,
    prefer_paved: preferPavedToggle ? preferPavedToggle.checked : false,
    prefer_lit: preferLitToggle ? preferLitToggle.checked : false,
    avoid_unsafe_roads: avoidUnsafeToggle ? avoidUnsafeToggle.checked : false,
  };

  // Add scenic routing weights if enabled
  const scenicWeights = getScenicWeights();
  if (scenicWeights) {
    payload.use_wsm = true;
    payload.weights = scenicWeights;

    if (groupNatureToggle && groupNatureToggle.checked) {
      payload.combine_nature = true;
    }

    console.log(
      "[App] Loop with scenic weights:",
      scenicWeights,
      "direction:",
      selectedDirection,
    );
  }

  // UI Loading State
  setLoadingState("Calculating loop...");

  try {
    const response = await fetch("/api/loop", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify(payload),
    });

    const data = await response.json();

    // Handle async processing (202 Accepted)
    if (response.status === 202 && data.status === "processing") {
      console.log("[App] Graph building for loop in progress, polling...");
      await pollForLoopTaskCompletion(data.task_id, payload);
      return;
    }

    // Handle success
    if (response.ok && data.success) {
      handleLoopRouteSuccess(data);
    } else {
      errorMsg.textContent = data.error || "Failed to calculate loop route.";
      errorMsg.classList.remove("hidden");
    }
  } catch (err) {
    console.error("[App] Loop network error:", err);
    errorMsg.textContent = "Network error. Please try again.";
    errorMsg.classList.remove("hidden");
  } finally {
    clearLoadingState();
  }
}

/**
 * Handle successful loop route response.
 * Supports both multi-loop (new) and legacy single-loop responses.
 */
function handleLoopRouteSuccess(data) {
  console.log("[App] Loop route received:", data);

  // Multi-loop response (new format)
  if (data.multi_loop && data.loops && data.loops.length > 0) {
    handleMultiLoopSuccess(data);
    return;
  }

  // Legacy single-loop fallback
  if (data.route_coords && data.route_coords.length > 0) {
    mapController.displayRoute(data.route_coords);
  }

  const routeOptions = document.getElementById("route-options");
  if (routeOptions) routeOptions.classList.add("hidden");

  if (data.stats) {
    statDistance.textContent = data.stats.distance_km;
    statTime.textContent = data.stats.time_min;
    statPace.textContent = data.stats.pace_kmh || "5.0";
    routeStats.classList.remove("hidden");
  }

  buildLoopInfoPanel(data);
  handleLoopWarning(data);
  mapController.clearDebugLayers();
  updateTileOverlay(data);
}

/**
 * Handle multi-loop response — display multiple loop candidates.
 */
function handleMultiLoopSuccess(data) {
  console.log(
    `[App] Multi-loop mode — displaying ${data.loops.length} loop candidates`,
  );

  // Initialise loop state
  loopState.loops = data.loops;
  loopState.selected = data.loops[0]?.id || null;
  loopState.visibility = {};
  data.loops.forEach((loop) => {
    loopState.visibility[loop.id] = true;
  });

  // Display all loops on map
  mapController.displayMultipleLoops(data.loops);

  // Render loop option cards (reuses route-options container)
  renderLoopOptions(data);

  // Update stats for first (best) loop
  if (data.stats) {
    statDistance.textContent = data.stats.distance_km;
    statTime.textContent = data.stats.time_min;
    statPace.textContent = data.stats.pace_kmh || "5.0";
    routeStats.classList.remove("hidden");
  }

  buildLoopInfoPanel(data);
  handleLoopWarning(data);
  mapController.clearDebugLayers();
  updateTileOverlay(data);

  // Scroll to loop options
  const routeOptions = document.getElementById("route-options");
  if (routeOptions) {
    setTimeout(() => {
      routeOptions.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }, 300);
  }
}

/**
 * Render loop option cards with toggle visibility and selection.
 */
function renderLoopOptions(data) {
  const container = document.getElementById("route-options-list");
  const routeOptions = document.getElementById("route-options");
  if (!container || !routeOptions) return;

  let html = "";

  for (const loop of data.loops) {
    const isSelected = loopState.selected === loop.id;
    const isVisible = loopState.visibility[loop.id] !== false;

    const devSign = loop.deviation_percent >= 0 ? "+" : "";
    const devClass =
      Math.abs(loop.deviation_percent) <= 10
        ? "text-green-600 dark:text-green-400"
        : Math.abs(loop.deviation_percent) <= 20
          ? "text-yellow-600 dark:text-yellow-400"
          : "text-red-600 dark:text-red-400";

    html += `
      <div class="route-option-card ${isSelected ? "selected" : ""}"
           data-loop-id="${loop.id}"
           onclick="selectLoop('${loop.id}')">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <button class="route-visibility-toggle"
                    onclick="toggleLoopVisibility(event, '${loop.id}')"
                    title="Toggle visibility">
              <i class="fas ${isVisible ? "fa-eye" : "fa-eye-slash"} text-gray-400 hover:text-gray-600"></i>
            </button>
            <span class="route-colour-dot" style="background-color: ${loop.colour}"></span>
            <div>
              <span class="font-medium text-gray-700 dark:text-gray-200">${loop.label}</span>
            </div>
          </div>
          ${isSelected ? '<i class="fas fa-check text-primary-500"></i>' : ""}
        </div>
        <div class="text-xs text-gray-500 dark:text-gray-400 mt-1 ml-8 flex gap-3">
          <span>${loop.distance_km} km</span>
          <span>${loop.time_min} min</span>
          <span class="${devClass}">${devSign}${loop.deviation_percent}%</span>
        </div>
      </div>
    `;
  }

  container.innerHTML = html;
  routeOptions.classList.remove("hidden");
  console.log(`[App] Rendered ${data.loops.length} loop option cards`);
}

/**
 * Toggle loop candidate visibility on the map.
 */
function toggleLoopVisibility(event, loopId) {
  event.stopPropagation();
  loopState.visibility[loopId] = !loopState.visibility[loopId];
  mapController.setLoopVisibility(loopId, loopState.visibility[loopId]);
  if (loopState.loops) {
    renderLoopOptions({ loops: loopState.loops });
  }
}

/**
 * Select a loop candidate — highlight it and update stats.
 */
function selectLoop(loopId) {
  loopState.selected = loopId;
  mapController.highlightLoop(loopId);
  if (loopState.loops) {
    renderLoopOptions({ loops: loopState.loops });
  }
  // Update stats for selected loop
  const loop = loopState.loops?.find((l) => l.id === loopId);
  if (loop) {
    statDistance.textContent = loop.distance_km;
    statTime.textContent = loop.time_min;
  }
}

window.toggleLoopVisibility = toggleLoopVisibility;
window.selectLoop = selectLoop;

/**
 * Build the loop info metadata panel.
 */
function buildLoopInfoPanel(data) {
  const loopMeta = data.loop_metadata || {};
  const statsContainer = document.getElementById("route-stats");
  let loopInfoEl = document.getElementById("loop-route-info");

  if (!loopInfoEl) {
    loopInfoEl = document.createElement("div");
    loopInfoEl.id = "loop-route-info";
    loopInfoEl.className =
      "p-4 bg-white dark:bg-gray-700 rounded-lg shadow-sm border border-gray-200 dark:border-gray-600";
    statsContainer.appendChild(loopInfoEl);
  }

  const dirLabel =
    loopMeta.directional_bias && loopMeta.directional_bias !== "none"
      ? loopMeta.directional_bias.charAt(0).toUpperCase() +
        loopMeta.directional_bias.slice(1)
      : "None";

  const budgetDev = loopMeta.budget_deviation
    ? `${(loopMeta.budget_deviation * 100).toFixed(1)}%`
    : "N/A";

  const algLabel = loopMeta.algorithm || "?";
  const numCandidates = loopMeta.num_candidates || "?";

  loopInfoEl.innerHTML = `
    <h3 class="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3 flex items-center">
      <i class="fas fa-sync-alt mr-2 text-blue-500"></i>Loop Details
    </h3>
    <div class="space-y-2 text-sm">
      <div class="flex justify-between items-center">
        <span class="text-gray-500 dark:text-gray-400">Target Distance</span>
        <span class="font-medium">${loopMeta.target_distance_km || data.target_distance_km || "?"} km</span>
      </div>
      <div class="flex justify-between items-center">
        <span class="text-gray-500 dark:text-gray-400">Best Match</span>
        <span class="font-medium">${data.stats?.distance_km || loopMeta.actual_distance_km || "?"} km</span>
      </div>
      <div class="flex justify-between items-center">
        <span class="text-gray-500 dark:text-gray-400">Deviation</span>
        <span class="loop-stats-badge budget">${budgetDev}</span>
      </div>
      <div class="flex justify-between items-center">
        <span class="text-gray-500 dark:text-gray-400">Direction</span>
        <span class="loop-stats-badge direction"><i class="fas fa-compass mr-1"></i>${dirLabel}</span>
      </div>
      <div class="flex justify-between items-center">
        <span class="text-gray-500 dark:text-gray-400">Algorithm</span>
        <span class="text-xs font-mono text-gray-500">${algLabel}</span>
      </div>
      <div class="flex justify-between items-center">
        <span class="text-gray-500 dark:text-gray-400">Candidates</span>
        <span class="text-xs font-mono text-gray-500">${numCandidates}</span>
      </div>
    </div>
  `;
  loopInfoEl.classList.remove("hidden");
}

function handleLoopWarning(data) {
  if (data.warning) {
    errorMsg.textContent = data.warning;
    errorMsg.className =
      "mt-6 p-4 bg-yellow-50 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-400 rounded-lg border border-yellow-200 dark:border-yellow-800 text-sm";
    errorMsg.classList.remove("hidden");
  }
}

function updateTileOverlay(data) {
  if (data.tiles_required && Array.isArray(data.tiles_required)) {
    routeUsedTileIds = data.tiles_required;
    refreshTileOverlay();
  } else {
    routeUsedTileIds = [];
  }
}

/**
 * Poll for loop task completion (async graph build).
 */
async function pollForLoopTaskCompletion(taskId, originalPayload) {
  const startTime = Date.now();
  let pollCount = 0;

  const poll = async () => {
    pollCount++;
    const elapsed = Date.now() - startTime;

    if (elapsed > MAX_POLL_TIME_MS) {
      errorMsg.textContent = "Loop route calculation timed out.";
      errorMsg.classList.remove("hidden");
      clearLoadingState();
      return;
    }

    try {
      const response = await fetch(`/api/task/${taskId}`);
      const data = await response.json();

      if (data.status === "complete") {
        setLoadingState("Graph ready, calculating loop...");
        await retryLoopRequest(originalPayload);
        return;
      }

      if (data.status === "failed") {
        errorMsg.textContent = data.error || "Graph building failed.";
        errorMsg.classList.remove("hidden");
        clearLoadingState();
        return;
      }

      const mins = Math.floor(elapsed / 60000);
      const secs = Math.floor((elapsed % 60000) / 1000);
      setLoadingState(
        `Building graph for loop... ${mins}:${secs.toString().padStart(2, "0")}`,
      );

      setTimeout(poll, POLL_INTERVAL_MS);
    } catch (err) {
      setTimeout(poll, POLL_INTERVAL_MS);
    }
  };

  poll();
}

/**
 * Retry loop request after graph build.
 */
async function retryLoopRequest(payload) {
  try {
    const response = await fetch("/api/loop", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify(payload),
    });

    const data = await response.json();

    if (response.ok && data.success) {
      handleLoopRouteSuccess(data);
    } else {
      errorMsg.textContent = data.error || "Loop route calculation failed.";
      errorMsg.classList.remove("hidden");
    }
  } catch (err) {
    errorMsg.textContent = "Failed to calculate loop route after graph build.";
    errorMsg.classList.remove("hidden");
  } finally {
    clearLoadingState();
  }
}

// ============================================================================
// Async Task Polling
// ============================================================================
const POLL_INTERVAL_MS = 2000; // Poll every 2 seconds
const MAX_POLL_TIME_MS = 300000; // 5 minute timeout

/**
 * Poll for task completion and then retry the route request.
 *
 * @param {string} taskId - The Celery task ID.
 * @param {object} originalPayload - The original route request payload.
 */
async function pollForTaskCompletion(taskId, originalPayload) {
  const startTime = Date.now();
  let pollCount = 0;

  const poll = async () => {
    pollCount++;
    const elapsed = Date.now() - startTime;

    // Timeout check
    if (elapsed > MAX_POLL_TIME_MS) {
      console.error("[App] Task polling timeout");
      errorMsg.innerHTML = `
                Graph building timed out after 5 minutes. 
                <button onclick="retryWithSync()" class="underline text-blue-600">Retry with sync mode</button>
            `;
      errorMsg.classList.remove("hidden");
      clearLoadingState();
      return;
    }

    try {
      const response = await fetch(`/api/task/${taskId}`);
      const data = await response.json();

      console.log(`[App] Task poll #${pollCount}: ${data.status}`);

      if (data.status === "complete") {
        // Graph is ready, retry the route request
        setLoadingState("Graph ready, calculating route...");
        await retryRouteRequest(originalPayload);
        return;
      }

      if (data.status === "failed") {
        errorMsg.textContent = data.error || "Graph building failed.";
        errorMsg.classList.remove("hidden");
        clearLoadingState();
        return;
      }

      // Still processing - update UI and continue polling
      const mins = Math.floor(elapsed / 60000);
      const secs = Math.floor((elapsed % 60000) / 1000);
      setLoadingState(
        `Building graph... ${mins}:${secs.toString().padStart(2, "0")}`,
      );

      // Schedule next poll
      setTimeout(poll, POLL_INTERVAL_MS);
    } catch (err) {
      console.error("[App] Poll error:", err);
      // Continue polling on network errors
      setTimeout(poll, POLL_INTERVAL_MS);
    }
  };

  // Start polling
  poll();
}

/**
 * Retry the route request after graph build completion.
 */
async function retryRouteRequest(payload) {
  try {
    const response = await fetch("/api/route", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify(payload),
    });

    const data = await response.json();

    if (response.ok) {
      handleRouteSuccess(data);
    } else {
      errorMsg.textContent = data.error || "Route calculation failed.";
      errorMsg.classList.remove("hidden");
    }
  } catch (err) {
    console.error("[App] Retry error:", err);
    errorMsg.textContent = "Failed to calculate route after graph build.";
    errorMsg.classList.remove("hidden");
  } finally {
    clearLoadingState();
  }
}

/**
 * Handle successful route response.
 * Detects multi-route vs single-route API responses.
 */
function handleRouteSuccess(data) {
  // Detect multi-route response (has 'routes' object)
  if (data.routes) {
    handleMultiRouteSuccess(data);
    return;
  }

  // Single-route mode (legacy)
  // Display route on map
  if (data.route_coords && data.route_coords.length > 0) {
    mapController.displayRoute(data.route_coords);
  }

  // Update Stats
  if (data.stats) {
    statDistance.textContent = data.stats.distance_km;
    statTime.textContent = data.stats.time_min;
    statPace.textContent = data.stats.pace_kmh;
    routeStats.classList.remove("hidden");
  }

  // Hide route options for single-route mode
  const routeOptions = document.getElementById("route-options");
  if (routeOptions) routeOptions.classList.add("hidden");

  // Display edge features on map (only for short routes)
  if (data.edge_features && data.edge_features.length > 0) {
    mapController.displayEdgeFeatures(data.edge_features);
  } else {
    mapController.clearDebugLayers();
  }

  // Update Debug Info panel
  if (data.debug_info) {
    if (data.debug_info.edge_preview) {
      renderEdgePreview(data.debug_info.edge_preview);
    }
    debugContent.textContent = JSON.stringify(data.debug_info, null, 2);
    debugInfo.classList.remove("hidden");
  } else {
    debugInfo.classList.add("hidden");
    const edgePreviewContainer = document.getElementById(
      "edge-preview-container",
    );
    if (edgePreviewContainer) edgePreviewContainer.classList.add("hidden");
  }

  // Extract tiles used for this route and refresh overlay
  if (data.tiles_required && Array.isArray(data.tiles_required)) {
    routeUsedTileIds = data.tiles_required;
    refreshTileOverlay();
  } else {
    routeUsedTileIds = [];
  }
}

/**
 * Handle multi-route response (3 distinct paths).
 */
function handleMultiRouteSuccess(data) {
  console.log("[App] Multi-route mode - displaying 3 routes");

  // Store routes in state
  routeState.routes = data.routes;
  routeState.selected = "balanced";
  routeState.visibility = { baseline: true, extremist: true, balanced: true };

  // Detect duplicate routes (same distance = likely same route)
  routeState.duplicates = detectDuplicateRoutes(data.routes);

  // Display all routes on map
  mapController.displayMultipleRoutes(data.routes);

  // Render route option cards
  renderRouteOptions(data.routes);

  // Update stats to show selected route
  updateStatsForRoute(routeState.selected);

  // Show route stats panel
  routeStats.classList.remove("hidden");

  // Auto-scroll to Route Options panel so user sees it
  const routeOptions = document.getElementById("route-options");
  if (routeOptions) {
    setTimeout(() => {
      routeOptions.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }, 300);
  }

  // Extract tiles used for this route and refresh overlay
  if (data.tiles_required && Array.isArray(data.tiles_required)) {
    routeUsedTileIds = data.tiles_required;
    console.log(
      `[App] Route used ${routeUsedTileIds.length} tile(s): ${routeUsedTileIds.join(", ")}`,
    );
    refreshTileOverlay(); // Refresh to show highlighted tiles
  } else {
    routeUsedTileIds = [];
  }

  // Hide debug info for multi-route (too complex)
  debugInfo.classList.add("hidden");
  mapController.clearDebugLayers();
}

/**
 * Detect duplicate routes by comparing distances.
 * Returns a map of route types to their duplicates.
 */
function detectDuplicateRoutes(routes) {
  const duplicates = {};
  const routeTypes = Object.keys(routes).filter((k) => routes[k]);

  for (let i = 0; i < routeTypes.length; i++) {
    for (let j = i + 1; j < routeTypes.length; j++) {
      const typeA = routeTypes[i];
      const typeB = routeTypes[j];
      const distA = routes[typeA]?.stats?.distance_km;
      const distB = routes[typeB]?.stats?.distance_km;

      // Compare distances (same distance = duplicate)
      if (distA && distB && distA === distB) {
        duplicates[typeB] = typeA;
        console.log(`[App] Duplicate detected: ${typeB} same as ${typeA}`);
      }
    }
  }

  return duplicates;
}

/**
 * Render route option cards in the sidebar.
 */
function renderRouteOptions(routes) {
  const container = document.getElementById("route-options-list");
  const routeOptions = document.getElementById("route-options");

  if (!container || !routeOptions) return;

  let html = "";

  // Order: balanced first (selected by default), then baseline, then extremist
  const orderedTypes = ["balanced", "baseline", "extremist"];

  for (const type of orderedTypes) {
    const routeData = routes[type];
    const config = ROUTE_CONFIG[type];
    if (!config || !routeData) continue;

    const isSelected = routeState.selected === type;
    const isVisible = routeState.visibility[type];
    const isDuplicate = routeState.duplicates?.[type];

    const distanceKm = routeData.stats?.distance_km || "?";
    const timeMin = routeData.stats?.time_min || "?";

    // Duplicate badge
    const duplicateBadge = isDuplicate
      ? `<span class="route-duplicate-badge">Same as ${ROUTE_CONFIG[isDuplicate]?.name || isDuplicate}</span>`
      : "";

    html += `
            <div class="route-option-card ${isSelected ? "selected" : ""} ${isDuplicate ? "is-duplicate" : ""}" 
                 data-route-type="${type}"
                 onclick="selectRoute('${type}')">
                <div class="flex items-center justify-between">
                    <div class="flex items-center gap-2">
                        <button class="route-visibility-toggle" 
                                onclick="toggleRouteVisibility(event, '${type}')"
                                title="Toggle visibility">
                            <i class="fas ${isVisible ? "fa-eye" : "fa-eye-slash"} text-gray-400 hover:text-gray-600"></i>
                        </button>
                        <span class="route-colour-dot" style="background-color: ${config.colour}"></span>
                        <div>
                            <span class="font-medium text-gray-700 dark:text-gray-200">${config.name}</span>
                            <span class="text-xs text-gray-400 ml-1">(${config.subtitle})</span>
                            ${duplicateBadge}
                        </div>
                    </div>
                    ${isSelected ? '<i class="fas fa-check text-primary-500"></i>' : ""}
                </div>
                <div class="text-xs text-gray-500 dark:text-gray-400 mt-1 ml-8">
                    ${distanceKm} km • ${timeMin} min
                </div>
            </div>
        `;
  }

  container.innerHTML = html;
  routeOptions.classList.remove("hidden");

  console.log(
    "[App] Rendered route options for",
    Object.keys(routes).length,
    "routes",
  );
}

/**
 * Toggle visibility of a route.
 */
function toggleRouteVisibility(event, routeType) {
  event.stopPropagation(); // Don't trigger card click

  routeState.visibility[routeType] = !routeState.visibility[routeType];
  mapController.setRouteVisibility(routeType, routeState.visibility[routeType]);

  // Re-render cards to update icons
  if (routeState.routes) {
    renderRouteOptions(routeState.routes);
  }
}

/**
 * Select a route as the primary/highlighted route.
 */
function selectRoute(routeType) {
  routeState.selected = routeType;
  mapController.highlightRoute(routeType);

  // Re-render cards to update selection
  if (routeState.routes) {
    renderRouteOptions(routeState.routes);
  }

  // Update stats display
  updateStatsForRoute(routeType);
}

/**
 * Update the stats panel to show the selected route's data.
 */
function updateStatsForRoute(routeType) {
  const routeData = routeState.routes?.[routeType];
  if (!routeData?.stats) return;

  statDistance.textContent = routeData.stats.distance_km;
  statTime.textContent = routeData.stats.time_min;
  statPace.textContent = routeData.stats.pace_kmh;
}

/**
 * Reset route state when markers are cleared.
 */
function resetRouteState() {
  routeState.routes = null;
  routeState.selected = "balanced";
  routeState.visibility = { baseline: true, extremist: true, balanced: true };

  loopState.loops = null;
  loopState.selected = null;
  loopState.visibility = {};

  const routeOptions = document.getElementById("route-options");
  if (routeOptions) routeOptions.classList.add("hidden");

  // Also hide loop route info
  const loopInfoEl = document.getElementById("loop-route-info");
  if (loopInfoEl) loopInfoEl.classList.add("hidden");

  mapController.clearLoopLayers();
}

// Expose functions globally for onclick handlers
window.toggleRouteVisibility = toggleRouteVisibility;
window.selectRoute = selectRoute;

/**
 * Set loading state on the UI.
 */
function setLoadingState(message) {
  btnText.textContent = message;
  btnSpinner.classList.remove("hidden");
  findRouteBtn.disabled = true;
  errorMsg.classList.add("hidden");
  routeStats.classList.add("hidden");
}

/**
 * Clear loading state.
 */
function clearLoadingState() {
  btnText.textContent = routingMode === "loop" ? "Find Loop" : "Find Route";
  btnSpinner.classList.add("hidden");
  findRouteBtn.disabled = false;
}

/**
 * Retry with synchronous mode (fallback for timeout).
 * Exposed globally for onclick handler.
 */
window.retryWithSync = async function () {
  errorMsg.classList.add("hidden");
  setLoadingState("Retrying (sync mode)...");

  if (routingMode === "loop") {
    // Retry loop request
    const payload = {
      start_lat: startState.lat,
      start_lon: startState.lon,
      distance_km: parseFloat(loopDistanceSlider.value),
      directional_bias: selectedDirection,
      variety_level: varietyLevelSlider
        ? parseInt(varietyLevelSlider.value)
        : 0,
      prefer_pedestrian: preferPedestrianToggle
        ? preferPedestrianToggle.checked
        : false,
      prefer_paved: preferPavedToggle ? preferPavedToggle.checked : false,
      prefer_lit: preferLitToggle ? preferLitToggle.checked : false,
      avoid_unsafe_roads: avoidUnsafeToggle ? avoidUnsafeToggle.checked : false,
      force_sync: true,
    };

    const scenicWeights = getScenicWeights();
    if (scenicWeights) {
      payload.use_wsm = true;
      payload.weights = scenicWeights;
      if (groupNatureToggle && groupNatureToggle.checked) {
        payload.combine_nature = true;
      }
    }

    await retryLoopRequest(payload);
    return;
  }

  const payload = {
    start_lat: startState.lat,
    start_lon: startState.lon,
    end_lat: endState.lat,
    end_lon: endState.lon,
    force_sync: true, // Hint to server (if supported)
  };

  // Add scenic weights
  const scenicWeights = getScenicWeights();
  if (scenicWeights) {
    payload.use_wsm = true;
    payload.weights = scenicWeights;

    if (groupNatureToggle && groupNatureToggle.checked) {
      payload.combine_nature = true;
    }
  }

  await retryRouteRequest(payload);
};

// ============================================================================
// Keyboard Shortcuts
// ============================================================================
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    mapController.clear();
    // Also close mobile sidebar on Escape
    const sidebar = document.getElementById("sidebar");
    if (sidebar) sidebar.classList.remove("mobile-open");
  }
});

// ============================================================================
// Navigation Rail View Switching
// ============================================================================
const navRailBtns = document.querySelectorAll(".nav-rail-btn");
const viewPanels = document.querySelectorAll(".view-panel");
const sidebar = document.getElementById("sidebar");
const mobileSidebarClose = document.getElementById("mobile-sidebar-close");

/**
 * Switch to a different view panel.
 * @param {string} viewId - The ID of the view to switch to (e.g., 'route-view').
 */
function switchView(viewId) {
  // Update nav rail button states
  navRailBtns.forEach((btn) => {
    if (btn.dataset.view === viewId) {
      btn.classList.add("active");
    } else {
      btn.classList.remove("active");
    }
  });

  // Update view panel visibility
  viewPanels.forEach((panel) => {
    if (panel.id === viewId) {
      panel.dataset.active = "true";
      panel.classList.remove("hidden");
    } else {
      panel.dataset.active = "false";
      panel.classList.add("hidden");
    }
  });

  // On mobile: open sidebar overlay when switching views
  if (window.innerWidth < 768 && sidebar) {
    sidebar.classList.add("mobile-open");
  }

  // Save selection to localStorage
  localStorage.setItem("selectedView", viewId);

  console.log(`[Nav] Switched to view: ${viewId}`);
}

// Nav rail button click handlers
navRailBtns.forEach((btn) => {
  btn.addEventListener("click", () => {
    const viewId = btn.dataset.view;
    if (viewId) {
      switchView(viewId);
    }
  });
});

// Mobile sidebar close button
if (mobileSidebarClose) {
  mobileSidebarClose.addEventListener("click", () => {
    if (sidebar) sidebar.classList.remove("mobile-open");
  });
}

// Close mobile sidebar when clicking outside (on the map)
document.getElementById("map")?.addEventListener("click", () => {
  if (window.innerWidth < 768 && sidebar) {
    sidebar.classList.remove("mobile-open");
  }
});

// Restore saved view on load
const savedView = localStorage.getItem("selectedView");
if (savedView && document.getElementById(savedView)) {
  switchView(savedView);
}

// Theme toggle handlers for placeholder views
const themeToggleStats = document.getElementById("theme-toggle-stats");
const themeToggleSettings = document.getElementById("theme-toggle-settings");

[themeToggleStats, themeToggleSettings].forEach((toggle) => {
  if (toggle) {
    toggle.addEventListener("click", () => {
      html.classList.toggle("dark");
      localStorage.theme = html.classList.contains("dark") ? "dark" : "light";
    });
  }
});

// ============================================================================
// Panel Collapse/Expand Functionality
// ============================================================================
const leftPanel = document.getElementById("left-panel");
const collapseToggle = document.getElementById("collapse-toggle");
const expandPanelBtn = document.getElementById("expand-panel-btn");

/**
 * Toggle panel collapsed state.
 */
function togglePanelCollapse() {
  const isCollapsed = leftPanel.classList.toggle("collapsed");

  // Show/hide expand button
  if (isCollapsed) {
    expandPanelBtn.classList.remove("hidden");
  } else {
    expandPanelBtn.classList.add("hidden");
  }

  // Persist state
  localStorage.setItem("panelCollapsed", isCollapsed);

  // Trigger map resize after transition
  setTimeout(() => {
    if (mapController && mapController.map) {
      mapController.map.invalidateSize();
    }
  }, 350);

  console.log(`[Nav] Panel ${isCollapsed ? "collapsed" : "expanded"}`);
}

// Collapse toggle button
if (collapseToggle) {
  collapseToggle.addEventListener("click", togglePanelCollapse);
}

// Expand button (floating)
if (expandPanelBtn) {
  expandPanelBtn.addEventListener("click", togglePanelCollapse);
}

// Restore collapsed state on load
const savedCollapsed = localStorage.getItem("panelCollapsed") === "true";
if (savedCollapsed && leftPanel) {
  leftPanel.classList.add("collapsed");
  if (expandPanelBtn) expandPanelBtn.classList.remove("hidden");
}

// ============================================================================
// Sidebar Resize Functionality
// ============================================================================
const sidebarEl = document.getElementById("sidebar");
const resizeHandle = document.getElementById("sidebar-resize-handle");

const MIN_SIDEBAR_WIDTH = 280;
const MAX_SIDEBAR_WIDTH = 600;

let isResizing = false;
let startX = 0;
let startWidth = 0;

/**
 * Start resize operation.
 */
function startResize(e) {
  if (window.innerWidth < 768) return; // Disabled on mobile

  isResizing = true;
  startX = e.clientX;
  startWidth = sidebarEl.offsetWidth;

  document.body.classList.add("resizing");
  resizeHandle.classList.add("dragging");

  document.addEventListener("mousemove", doResize);
  document.addEventListener("mouseup", stopResize);

  e.preventDefault();
}

/**
 * Perform resize during drag.
 */
function doResize(e) {
  if (!isResizing) return;

  const diff = e.clientX - startX;
  let newWidth = startWidth + diff;

  // Clamp to min/max
  newWidth = Math.max(MIN_SIDEBAR_WIDTH, Math.min(MAX_SIDEBAR_WIDTH, newWidth));

  sidebarEl.style.width = `${newWidth}px`;
}

/**
 * End resize operation.
 */
function stopResize() {
  if (!isResizing) return;

  isResizing = false;
  document.body.classList.remove("resizing");
  resizeHandle.classList.remove("dragging");

  document.removeEventListener("mousemove", doResize);
  document.removeEventListener("mouseup", stopResize);

  // Persist width
  const currentWidth = sidebarEl.offsetWidth;
  localStorage.setItem("sidebarWidth", currentWidth);

  // Trigger map resize
  if (mapController && mapController.map) {
    mapController.map.invalidateSize();
  }

  console.log(`[Nav] Sidebar resized to ${currentWidth}px`);
}

// Attach resize handler
if (resizeHandle) {
  resizeHandle.addEventListener("mousedown", startResize);
}

// Restore saved width
const savedWidth = localStorage.getItem("sidebarWidth");
if (savedWidth && sidebarEl) {
  const width = parseInt(savedWidth, 10);
  if (width >= MIN_SIDEBAR_WIDTH && width <= MAX_SIDEBAR_WIDTH) {
    sidebarEl.style.width = `${width}px`;
  }
}

// Initial state
updateClearButtons();
updateInstructions();

console.log("[App] PathFinder initialised with instant geocoding");
console.log("[Nav] Navigation rail ready with collapse and resize support");
