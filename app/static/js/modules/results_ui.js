/**
 * Results UI (Route Cards & Stats)
 * Handles rendering route/loop option cards with save functionality.
 */
import {
  routeState,
  loopState,
  startState,
  endState,
  appState,
} from "./state.js";
import { ROUTE_CONFIG } from "./config.js";
import { mapController } from "./map_manager.js";
import { showToast, isAuthenticated } from "./ui_common.js";
import { buildGpxXml, buildExportFilename, downloadGpx } from "./gpx_export.js";

// DOM Elements
const routeOptionsList = document.getElementById("route-options-list");
const routeOptionsContainer = document.getElementById("route-options");
const routesEmptyState = document.getElementById("routes-empty-state");
const routeStatsContainer = document.getElementById("route-stats");
const statDistance = document.getElementById("stat-distance");
const statTime = document.getElementById("stat-time");
const exportGpxBtn = document.getElementById("export-gpx-btn");

// ============================================================================
// SAVE QUERY LOGIC
// ============================================================================

/**
 * Collect the current scenic weights from the UI controls.
 * @returns {Object} weights snapshot
 */
function collectWeights() {
  const w = {};
  const sliders = [
    ["distance", "weight-distance"],
    ["quietness", "weight-quietness"],
    ["greenness", "weight-greenness"],
    ["water", "weight-water"],
    ["nature", "weight-nature"],
    ["flatness", "weight-flatness"],
  ];
  for (const [key, id] of sliders) {
    const el = document.getElementById(id);
    if (el) w[key] = parseFloat(el.value);
  }
  // Toggles
  const socialToggle = document.getElementById("weight-social");
  if (socialToggle) w.social = socialToggle.checked;
  const groupNature = document.getElementById("group-nature-toggle");
  if (groupNature) w.group_nature = groupNature.checked;

  // Advanced options
  const advToggles = [
    ["prefer_pedestrian", "prefer-pedestrian-toggle"],
    ["prefer_paved", "prefer-paved-toggle"],
    ["prefer_lit", "prefer-lit-toggle"],
    ["heavily_avoid_unlit", "heavily-avoid-unlit-toggle"],
    ["avoid_unsafe", "avoid-unsafe-toggle"],
  ];
  for (const [key, id] of advToggles) {
    const el = document.getElementById(id);
    if (el) w[key] = el.checked;
  }

  return w;
}

/**
 * Generate a human-readable query name from addresses or coordinates.
 */
function generateQueryName(isLoop) {
  const startLabel =
    startState.address ||
    (startState.lat
      ? `${startState.lat.toFixed(4)}, ${startState.lon.toFixed(4)}`
      : "Unknown");

  if (isLoop) {
    return `Loop from ${startLabel}`;
  }

  const endLabel =
    endState.address ||
    (endState.lat
      ? `${endState.lat.toFixed(4)}, ${endState.lon.toFixed(4)}`
      : "Unknown");
  return `${startLabel} → ${endLabel}`;
}

/**
 * Save a route/loop query to the database.
 * @param {string} routeType - e.g. "balanced", "baseline", "extremist", or loop ID
 * @param {boolean} isLoop - Whether this is a loop query
 * @param {HTMLElement} btn - The save button element
 */
async function handleSaveQuery(routeType, isLoop, btn) {
  if (btn.classList.contains("saved")) return;

  // Auth check
  const authed = await isAuthenticated();
  if (!authed) {
    showToast("Sign in to save queries", "info");
    return;
  }

  // Collect data
  let geometry = null;
  let distanceKm = null;

  if (isLoop) {
    // Find the loop data
    const loops = loopState.loops;
    const loop = loops?.find((l) => l.id === routeType);
    if (loop) {
      geometry = loop.route_coords;
      distanceKm = loop.distance_km;
    }
  } else {
    const routeData = routeState.routes?.[routeType];
    if (routeData) {
      geometry = routeData.route_coords || routeData.coordinates;
      distanceKm = routeData.stats?.distance_km;
    }
  }

  const payload = {
    name: generateQueryName(isLoop),
    start_lat: startState.lat,
    start_lon: startState.lon,
    end_lat: isLoop ? null : endState.lat,
    end_lon: isLoop ? null : endState.lon,
    weights: collectWeights(),
    route_geometry: geometry,
    distance_km: distanceKm,
    is_loop: isLoop,
  };

  // Save
  btn.innerHTML = '<i class="fas fa-circle-notch fa-spin"></i>';
  try {
    const res = await fetch("/api/queries", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (res.ok) {
      btn.classList.add("saved");
      btn.innerHTML = '<i class="fas fa-check"></i> Saved';
      showToast("Query saved!", "success");
      document.dispatchEvent(new CustomEvent("saved-query-added"));
    } else {
      const data = await res.json();
      showToast(data.error || "Failed to save", "error");
      btn.innerHTML = '<i class="fas fa-bookmark"></i> Save';
    }
  } catch (err) {
    showToast("Network error", "error");
    btn.innerHTML = '<i class="fas fa-bookmark"></i> Save';
  }
}

// ============================================================================
// ROUTE CARDS (Standard Mode)
// ============================================================================

/**
 * Render route option cards in the sidebar.
 */
export function renderRouteOptions(routes) {
  if (!routeOptionsList || !routeOptionsContainer) return;

  let html = "";
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

    const duplicateBadge = isDuplicate
      ? `<span class="route-duplicate-badge">Same as ${ROUTE_CONFIG[isDuplicate]?.name || isDuplicate}</span>`
      : "";

    html += `
            <div class="route-option-card ${isSelected ? "selected" : ""} ${isDuplicate ? "is-duplicate" : ""}" 
                 data-route-type="${type}">
                <div class="flex items-center justify-between">
                    <div class="flex items-center gap-2">
                        <button class="route-visibility-toggle" 
                                data-type="${type}"
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
                    <div class="flex items-center gap-1">
                        <button class="save-query-btn" data-route-type="${type}" data-is-loop="false" title="Save this query">
                            <i class="fas fa-bookmark"></i> Save
                        </button>
                        ${isSelected ? '<i class="fas fa-check text-primary-500"></i>' : ""}
                    </div>
                </div>
                <div class="text-xs text-gray-500 dark:text-gray-400 mt-1 ml-8">
                    ${distanceKm} km • ${timeMin} min
                </div>
            </div>
        `;
  }

  routeOptionsList.innerHTML = html;
  routeOptionsContainer.classList.remove("hidden");
  if (routesEmptyState) routesEmptyState.classList.add("hidden");
  if (routeStatsContainer) routeStatsContainer.classList.remove("hidden");

  // Add listeners
  document.querySelectorAll(".route-option-card").forEach((card) => {
    card.addEventListener("click", (e) => {
      if (e.target.closest(".route-visibility-toggle")) return;
      if (e.target.closest(".save-query-btn")) return;
      handleRouteSelect(card.dataset.routeType);
    });
  });

  document.querySelectorAll(".route-visibility-toggle").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      handleRouteVisibilityToggle(btn.dataset.type);
    });
  });

  // Save buttons
  document.querySelectorAll(".save-query-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const type = btn.dataset.routeType;
      const isLoop = btn.dataset.isLoop === "true";
      handleSaveQuery(type, isLoop, btn);
    });
  });
}

function handleRouteSelect(routeType) {
  routeState.selected = routeType;
  if (mapController) mapController.highlightRoute(routeType);
  updateStatsForRoute(routeType);
  renderRouteOptions(routeState.routes); // Re-render to update selected state
}

function handleRouteVisibilityToggle(routeType) {
  routeState.visibility[routeType] = !routeState.visibility[routeType];
  if (mapController)
    mapController.setRouteVisibility(
      routeType,
      routeState.visibility[routeType],
    );
  renderRouteOptions(routeState.routes); // Re-render to update icon
}

export function updateStatsForRoute(routeType) {
  const routeData = routeState.routes?.[routeType];
  if (!routeData?.stats) return;

  if (statDistance) statDistance.textContent = routeData.stats.distance_km;
  if (statTime) statTime.textContent = routeData.stats.time_min;

  if (routeStatsContainer) routeStatsContainer.classList.remove("hidden");
}

// ============================================================================
// LOOP CARDS (Round Trip Mode)
// ============================================================================

/**
 * Render loop option cards (Multi-Loop support)
 */
export function renderLoopOptions(loops) {
  if (!routeOptionsList || !routeOptionsContainer || !loops) return;

  let html = "";

  loops.forEach((loop) => {
    const isSelected = loopState.selectedId === loop.id;
    const isVisible = loopState.visibility[loop.id] !== false;
    const colour = loop.colour || "#3B82F6";

    html += `
            <div class="loop-option-card px-4 py-3 rounded-lg border cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors mb-2 ${isSelected ? "border-primary-500 bg-primary-50 dark:bg-primary-900/20" : "border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-700"}" 
                 data-loop-id="${loop.id}">
                <div class="flex items-center justify-between">
                    <div class="flex items-center gap-2">
                        <button class="loop-visibility-toggle p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-500" 
                                data-loop-id="${loop.id}"
                                title="Toggle visibility">
                            <i class="fas ${isVisible ? "fa-eye" : "fa-eye-slash"} text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"></i>
                        </button>
                        <span class="w-3 h-3 rounded-full" style="background-color: ${colour}"></span>
                        <div>
                            <span class="font-medium text-gray-700 dark:text-gray-200">${loop.label || "Loop"}</span>
                        </div>
                    </div>
                    <div class="flex items-center gap-1">
                        <button class="save-query-btn" data-route-type="${loop.id}" data-is-loop="true" title="Save this query">
                            <i class="fas fa-bookmark"></i> Save
                        </button>
                        ${isSelected ? '<i class="fas fa-check text-primary-500"></i>' : ""}
                    </div>
                </div>
                <div class="text-xs text-gray-500 dark:text-gray-400 mt-1 ml-8 flex gap-3">
                    <span>${loop.distance_km} km</span>
                    <span>${loop.time_min} min</span>
                    ${loop.quality_score ? `<span title="Quality Score (0-1)\n60% Distance Accuracy\n40% Scenic Quality">★ ${loop.quality_score}</span>` : ""}
                </div>
            </div>
        `;
  });

  html += `
        <div class="text-xs text-gray-400 mt-3 px-1 italic border-t border-gray-100 dark:border-gray-700 pt-2">
            <i class="fas fa-info-circle mr-1"></i> 
            Quality Score = 60% Distance + 40% Scenery
        </div>
    `;

  routeOptionsList.innerHTML = html;
  routeOptionsContainer.classList.remove("hidden");
  if (routesEmptyState) routesEmptyState.classList.add("hidden");
  if (routeStatsContainer) routeStatsContainer.classList.remove("hidden");

  // Add listeners
  document.querySelectorAll(".loop-option-card").forEach((card) => {
    card.addEventListener("click", (e) => {
      if (e.target.closest(".loop-visibility-toggle")) return;
      if (e.target.closest(".save-query-btn")) return;
      handleLoopSelect(card.dataset.loopId, loops);
    });
  });

  document.querySelectorAll(".loop-visibility-toggle").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const loopId = btn.dataset.loopId;
      handleLoopVisibilityToggle(loopId, loops);
    });
  });

  // Save buttons
  document.querySelectorAll(".save-query-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const type = btn.dataset.routeType;
      const isLoop = btn.dataset.isLoop === "true";
      handleSaveQuery(type, isLoop, btn);
    });
  });
}

function handleLoopSelect(loopId, loops) {
  loopState.selectedId = loopId;

  if (mapController) mapController.highlightLoop(loopId);

  const selectedLoop = loops.find((l) => l.id === loopId);
  if (selectedLoop) {
    if (statDistance) statDistance.textContent = selectedLoop.distance_km;
    if (statTime) statTime.textContent = selectedLoop.time_min;
  }

  renderLoopOptions(loops);
}

function handleLoopVisibilityToggle(loopId, loops) {
  const isVisible = loopState.visibility[loopId] !== false;
  loopState.visibility[loopId] = !isVisible;

  if (mapController) mapController.setLoopVisibility(loopId, !isVisible);
  renderLoopOptions(loops);
}

function formatDistanceLabel(distanceKm) {
  const n = Number(distanceKm);
  return Number.isFinite(n) ? `${n.toFixed(1)} km` : "Unknown distance";
}

function getLocationLabel(pointState, fallback = "Unknown") {
  if (pointState?.address && pointState.address.trim()) {
    return pointState.address.trim();
  }
  if (Number.isFinite(pointState?.lat) && Number.isFinite(pointState?.lon)) {
    return `${pointState.lat.toFixed(4)}, ${pointState.lon.toFixed(4)}`;
  }
  return fallback;
}

function getShortLocationLabel(pointState, fallback = "Unknown") {
  const full = getLocationLabel(pointState, fallback);
  const short = full.split(",")[0]?.trim();
  return short || full;
}

function getAddressParts(address) {
  if (!address || typeof address !== "string") return [];
  return address
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean)
    .map((part) => part.toLowerCase());
}

function inferAreaLabel(startAddress, endAddress) {
  const startParts = getAddressParts(startAddress);
  const endParts = getAddressParts(endAddress);
  if (!startParts.length && !endParts.length) return "";

  // Prefer shared locality components before falling back to a single address.
  if (startParts.length && endParts.length) {
    for (const part of startParts) {
      if (endParts.includes(part) && part.length >= 3) {
        return part;
      }
    }
  }

  return startParts[1] || endParts[1] || startParts[0] || endParts[0] || "";
}

function getCurrentExportContext() {
  const startLabel = getShortLocationLabel(startState, "Start");
  const endLabel = getShortLocationLabel(endState, "End");

  if (appState.routingMode === "loop") {
    const selectedLoop = loopState.loops?.find(
      (l) => l.id === loopState.selectedId,
    );
    if (!selectedLoop) return null;
    const distanceKm = selectedLoop.distance_km;
    const areaLabel = inferAreaLabel(startState.address, null);
    return {
      routeData: selectedLoop,
      label: selectedLoop.label || "loop",
      distanceKm,
      startLabel,
      endLabel: startLabel,
      areaLabel,
      name: `${startLabel} -> ${startLabel} | ${formatDistanceLabel(distanceKm)}`,
    };
  }

  const selectedType = routeState.selected;
  const selectedRoute = routeState.routes?.[selectedType];
  if (!selectedType || !selectedRoute) return null;
  const distanceKm = selectedRoute.stats?.distance_km;
  const areaLabel = inferAreaLabel(startState.address, endState.address);
  return {
    routeData: selectedRoute,
    label: selectedType,
    distanceKm,
    startLabel,
    endLabel,
    areaLabel,
    name: `${startLabel} -> ${endLabel} | ${formatDistanceLabel(distanceKm)}`,
  };
}

function hasValidRouteCoords(routeData) {
  const coords = routeData?.route_coords || routeData?.coordinates;
  return Array.isArray(coords) && coords.length >= 2;
}

function initGpxExport() {
  if (!exportGpxBtn) return;
  exportGpxBtn.addEventListener("click", () => {
    const context = getCurrentExportContext();
    if (!context) {
      showToast("Select a route before exporting.", "info");
      return;
    }
    if (!hasValidRouteCoords(context.routeData)) {
      showToast("Route data unavailable for GPX export.", "error");
      return;
    }

    const routePayload = {
      ...context.routeData,
      name: context.name,
    };
    const xml = buildGpxXml(routePayload);
    const filename = buildExportFilename({
      label: context.label,
      distanceKm: context.distanceKm,
      startLabel: context.startLabel,
      endLabel: context.endLabel,
      areaLabel: context.areaLabel,
    });
    downloadGpx(xml, filename);
    showToast("GPX exported successfully.", "success");
  });
}

initGpxExport();

export function hideResults() {
  if (routeOptionsContainer) routeOptionsContainer.classList.add("hidden");
  if (routeStatsContainer) routeStatsContainer.classList.add("hidden");
  if (routesEmptyState) routesEmptyState.classList.remove("hidden");
}
