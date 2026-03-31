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
import {
  formatPaceFromSpeed,
  getDistanceUnit,
  kmToDisplay,
  speedKmhToDisplay,
} from "./movement_prefs.js";

// DOM Elements
const routeOptionsList = document.getElementById("route-options-list");
const routeOptionsContainer = document.getElementById("route-options");
const routesEmptyState = document.getElementById("routes-empty-state");
const routesLoadingState = document.getElementById("routes-loading-state");
const routesLoadingMessage = document.getElementById("routes-loading-message");
const routesRecalculatingBanner = document.getElementById(
  "routes-recalculating-banner",
);
const routesRecalculatingMessage = document.getElementById(
  "routes-recalculating-message",
);
const routeStatsContainer = document.getElementById("route-stats");
const statDistance = document.getElementById("stat-distance");
const statDistanceUnit = document.getElementById("stat-distance-unit");
const statTime = document.getElementById("stat-time");
const statProfile = document.getElementById("stat-profile");
const statSpeed = document.getElementById("stat-speed");
const statSpeedUnit = document.getElementById("stat-speed-unit");
const statPace = document.getElementById("stat-pace");
const exportGpxBtn = document.getElementById("export-gpx-btn");

function prettifyProfileLabel(profile) {
  if (!profile || typeof profile !== "string") return "walking";
  return profile.replaceAll("_", " ");
}

function resolveDistanceParts(stats = {}) {
  if (stats.distance !== undefined && stats.distance !== null) {
    return {
      value: String(stats.distance),
      unit: stats.distance_unit || getDistanceUnit(),
    };
  }

  const unit = stats.distance_unit || getDistanceUnit();
  const kmValue = Number(stats.distance_km);
  if (Number.isFinite(kmValue)) {
    return {
      value: kmToDisplay(kmValue, unit).toFixed(2),
      unit,
    };
  }

  return { value: "?", unit };
}

function resolveSpeedParts(stats = {}) {
  if (stats.assumed_speed !== undefined && stats.assumed_speed !== null) {
    return {
      value: String(stats.assumed_speed),
      unit: stats.speed_unit || (stats.distance_unit === "mi" ? "mph" : "km/h"),
    };
  }

  const fallbackSpeedKmh = Number(stats.assumed_speed_kmh ?? stats.pace_kmh);
  if (Number.isFinite(fallbackSpeedKmh)) {
    const unit = stats.distance_unit || getDistanceUnit();
    return {
      value: speedKmhToDisplay(fallbackSpeedKmh, unit).toFixed(1),
      unit: unit === "mi" ? "mph" : "km/h",
    };
  }

  return { value: "?", unit: "km/h" };
}

function resolvePaceText(stats = {}) {
  if (stats.assumed_pace) return String(stats.assumed_pace);

  const speedKmh = Number(stats.assumed_speed_kmh ?? stats.pace_kmh);
  if (Number.isFinite(speedKmh) && speedKmh > 0) {
    return formatPaceFromSpeed(
      speedKmh,
      stats.distance_unit || getDistanceUnit(),
    );
  }

  return "n/a";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function humaniseRoleToken(value) {
  return String(value ?? "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (token) => token.toUpperCase());
}

function classifyLoopTag(tag) {
  const token = String(tag ?? "")
    .trim()
    .toLowerCase();
  if (!token) return "loop-tag-neutral";

  const varietyMatch = token.match(/^variety\s*l(\d+)$/);
  if (varietyMatch) {
    const varietyLevel = Math.max(
      0,
      Math.min(3, Number.parseInt(varietyMatch[1], 10) || 0),
    );
    return `loop-tag-variety-${varietyLevel}`;
  }

  if (token.includes("quality leader")) return "loop-tag-quality";
  if (token.startsWith("target delta")) return "loop-tag-distance";
  if (token.startsWith("scenic rank") || token.includes("lowest scenic cost"))
    return "loop-tag-scenic";
  if (
    token.includes("different vs best") ||
    token.includes("edge diversity") ||
    token.includes("novelty")
  )
    return "loop-tag-diversity";
  if (token.startsWith("bias:") || token.includes("smart bearing"))
    return "loop-tag-direction";

  return "loop-tag-neutral";
}

function hasRenderedResults() {
  if (!routeOptionsList || !routeOptionsContainer) return false;
  if (routeOptionsContainer.classList.contains("hidden")) return false;
  return routeOptionsList.children.length > 0;
}

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
    ["prefer_dedicated_pavements", "prefer-dedicated-pavements-toggle"],
    ["prefer_nature_trails", "prefer-nature-trails-toggle"],
    ["prefer_paved", "prefer-paved-toggle"],
    ["prefer_lit", "prefer-lit-toggle"],
    ["heavily_avoid_unlit", "heavily-avoid-unlit-toggle"],
    ["avoid_unsafe_roads", "avoid-unsafe-toggle"],
  ];
  for (const [key, id] of advToggles) {
    const el = document.getElementById(id);
    if (el) w[key] = el.checked;
  }

  // Legacy compatibility with previously stored query snapshots.
  if (w.prefer_dedicated_pavements === true) {
    w.prefer_pedestrian = true;
  }
  if (w.avoid_unsafe_roads === true) {
    w.avoid_unsafe = true;
  }

  return w;
}

/**
 * Generate a human-readable query name from addresses or coordinates.
 */
function generateQueryName(isLoop, routeType = null) {
  const startLabel =
    startState.address ||
    (startState.lat
      ? `${startState.lat.toFixed(4)}, ${startState.lon.toFixed(4)}`
      : "Unknown");

  if (isLoop) {
    const loopLabel =
      loopState.loops?.find((l) => l.id === routeType)?.label || "Loop";
    return `${loopLabel} from ${startLabel}`;
  }

  const endLabel =
    endState.address ||
    (endState.lat
      ? `${endState.lat.toFixed(4)}, ${endState.lon.toFixed(4)}`
      : "Unknown");

  const routeName = ROUTE_CONFIG[routeType]?.name || "Route";
  return `${routeName}: ${startLabel} → ${endLabel}`;
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
    name: generateQueryName(isLoop, routeType),
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

    const distanceParts = resolveDistanceParts(routeData.stats);
    const timeMin = routeData.stats?.time_min || "?";
    const routeSubtitle = routeData.route_context?.subtitle || config.subtitle;
    const routeModifiers = Array.isArray(routeData.route_context?.modifiers)
      ? routeData.route_context.modifiers
      : [];
    const modifiersLine = routeModifiers.length
      ? `<div class="text-xs text-gray-400 dark:text-gray-500 mt-1 ml-8">${routeModifiers.join(" • ")}</div>`
      : "";

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
                          <span class="text-xs text-gray-400 ml-1">(${routeSubtitle})</span>
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
                    ${distanceParts.value} ${distanceParts.unit} • ${timeMin} min
                </div>
                ${modifiersLine}
            </div>
        `;
  }

  routeOptionsList.innerHTML = html;
  routeOptionsContainer.classList.remove("hidden");
  if (routesLoadingState) routesLoadingState.classList.add("hidden");
  if (routesRecalculatingBanner)
    routesRecalculatingBanner.classList.add("hidden");
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

  const distanceParts = resolveDistanceParts(routeData.stats);
  const speedParts = resolveSpeedParts(routeData.stats);
  const paceText = resolvePaceText(routeData.stats);
  const profileLabel = prettifyProfileLabel(
    routeData.stats.travel_profile || "walking",
  );

  if (statDistance) statDistance.textContent = distanceParts.value;
  if (statDistanceUnit) statDistanceUnit.textContent = distanceParts.unit;
  if (statTime) statTime.textContent = routeData.stats.time_min;
  if (statProfile) statProfile.textContent = profileLabel;
  if (statSpeed) statSpeed.textContent = speedParts.value;
  if (statSpeedUnit) statSpeedUnit.textContent = speedParts.unit;
  if (statPace) statPace.textContent = paceText;

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
    const loopLabel = escapeHtml(loop.label || "Loop");
    const loopSubtitle = loop.label_subtitle
      ? escapeHtml(loop.label_subtitle)
      : "";
    const loopRole = loop.label_role
      ? escapeHtml(humaniseRoleToken(loop.label_role))
      : "";
    const loopReason = loop.label_reason ? escapeHtml(loop.label_reason) : "";
    const loopTags = Array.isArray(loop.label_tags)
      ? loop.label_tags
          .map((tag) => escapeHtml(tag))
          .filter(Boolean)
          .slice(0, 7)
      : [];
    const tagsHtml = loopTags.length
      ? `<div class="loop-tag-list flex flex-wrap gap-1 mt-1 ml-8">${loopTags
          .map(
            (tag) =>
              `<span class="loop-tag ${classifyLoopTag(tag)}">${tag}</span>`,
          )
          .join("")}</div>`
      : loopRole
        ? `<div class="text-[11px] text-gray-500 dark:text-gray-400 mt-1 ml-8">Role: ${loopRole}</div>`
        : "";
    const loopDistance =
      loop.distance !== undefined && loop.distance !== null
        ? `${loop.distance} ${loop.distance_unit || getDistanceUnit()}`
        : `${loop.distance_km} km`;

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
                          <span class="font-medium text-gray-700 dark:text-gray-200">${loopLabel}</span>
                          ${loopSubtitle ? `<div class="text-[11px] text-gray-500 dark:text-gray-400 mt-0.5">${loopSubtitle}</div>` : ""}
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
                    <span>${loopDistance}</span>
                    <span>${loop.time_min} min</span>
                    ${loop.quality_score ? `<span title="Quality Score (0-1)\n60% Distance Accuracy\n40% Scenic Quality">★ ${loop.quality_score}</span>` : ""}
                </div>
                ${tagsHtml}
                ${loopReason ? `<div class="text-[11px] text-gray-500 dark:text-gray-400 mt-1 ml-8">${loopReason}</div>` : ""}
            </div>
        `;
  });

  html += `
        <div class="loop-routes-footer text-xs text-gray-400 mt-3 px-1 border-t border-gray-100 dark:border-gray-700 pt-2">
            <div class="italic">
              <i class="fas fa-info-circle mr-1"></i> 
              Quality Score = 60% Distance + 40% Scenery
            </div>
            <div class="loop-tags-legend">
              <button type="button" class="loop-tags-legend-trigger" aria-label="Explain loop tag colours" title="Explain loop tag colours">
                <i class="fas fa-palette"></i>
              </button>
              <div class="loop-tags-legend-tooltip" role="tooltip">
                <div class="loop-tags-legend-title">Tag colours</div>
                <div class="loop-tags-legend-items">
                  <span class="loop-tag loop-tag-quality">Quality</span>
                  <span class="loop-tag loop-tag-distance">Distance</span>
                  <span class="loop-tag loop-tag-scenic">Scenic</span>
                  <span class="loop-tag loop-tag-diversity">Diversity</span>
                  <span class="loop-tag loop-tag-direction">Direction</span>
                  <span class="loop-tag loop-tag-variety-0">Variety L0</span>
                  <span class="loop-tag loop-tag-variety-1">L1</span>
                  <span class="loop-tag loop-tag-variety-2">L2</span>
                  <span class="loop-tag loop-tag-variety-3">L3</span>
                </div>
              </div>
            </div>
        </div>
    `;

  routeOptionsList.innerHTML = html;
  routeOptionsContainer.classList.remove("hidden");
  if (routesLoadingState) routesLoadingState.classList.add("hidden");
  if (routesRecalculatingBanner)
    routesRecalculatingBanner.classList.add("hidden");
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
    if (statDistance) {
      statDistance.textContent = String(
        selectedLoop.distance !== undefined && selectedLoop.distance !== null
          ? selectedLoop.distance
          : selectedLoop.distance_km,
      );
    }
    if (statDistanceUnit) {
      statDistanceUnit.textContent =
        selectedLoop.distance_unit || getDistanceUnit();
    }
    if (statTime) statTime.textContent = selectedLoop.time_min;
    if (statProfile)
      statProfile.textContent = prettifyProfileLabel(
        selectedLoop.travel_profile || "walking",
      );
    if (statSpeed)
      statSpeed.textContent = String(selectedLoop.assumed_speed ?? "?");
    if (statSpeedUnit)
      statSpeedUnit.textContent =
        selectedLoop.speed_unit ||
        (getDistanceUnit() === "mi" ? "mph" : "km/h");
    if (statPace) statPace.textContent = selectedLoop.assumed_pace || "n/a";
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

export function hideResults(options = {}) {
  const {
    showLoading = false,
    message = "Calculating route...",
    keepPrevious = false,
  } = options;

  const canKeepPrevious = keepPrevious && hasRenderedResults();

  if (!canKeepPrevious) {
    if (routeOptionsContainer) routeOptionsContainer.classList.add("hidden");
    if (routeStatsContainer) routeStatsContainer.classList.add("hidden");
  }

  if (showLoading) {
    if (canKeepPrevious) {
      if (routeOptionsContainer)
        routeOptionsContainer.classList.remove("hidden");
      if (routeStatsContainer) routeStatsContainer.classList.remove("hidden");
      if (routesRecalculatingMessage)
        routesRecalculatingMessage.textContent = message;
      if (routesRecalculatingBanner)
        routesRecalculatingBanner.classList.remove("hidden");
      if (routesLoadingState) routesLoadingState.classList.add("hidden");
      if (routesEmptyState) routesEmptyState.classList.add("hidden");
      return;
    }

    if (routesLoadingMessage) routesLoadingMessage.textContent = message;
    if (routesLoadingState) routesLoadingState.classList.remove("hidden");
    if (routesRecalculatingBanner)
      routesRecalculatingBanner.classList.add("hidden");
    if (routesEmptyState) routesEmptyState.classList.add("hidden");
    return;
  }

  if (routesRecalculatingBanner)
    routesRecalculatingBanner.classList.add("hidden");
  if (routesLoadingState) routesLoadingState.classList.add("hidden");

  if (canKeepPrevious) {
    if (routeOptionsContainer) routeOptionsContainer.classList.remove("hidden");
    if (routeStatsContainer) routeStatsContainer.classList.remove("hidden");
    if (routesEmptyState) routesEmptyState.classList.add("hidden");
    return;
  }

  if (routesEmptyState) routesEmptyState.classList.remove("hidden");
}
