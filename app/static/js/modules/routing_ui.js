/**
 * Routing UI Orchestrator
 * Handles form submissions, finding routes, and loops.
 */
import {
  appState,
  startState,
  endState,
  routeState,
  loopState,
  setRoutingMode,
  setSelectedDirection,
} from "./state.js";
import {
  createRouteTask,
  createLoopTask,
  pollTask,
  submitFeedback,
} from "./api.js";
import { getScenicWeights } from "./scenic_controls.js";
import { setLoadingState, clearLoadingState } from "./ui_common.js";
import { mapController } from "./map_manager.js";
import {
  renderRouteOptions,
  renderLoopOptions,
  updateStatsForRoute,
  hideResults,
} from "./results_ui.js";
import { switchView } from "./layout_ui.js";

// Elements
const modeStandardBtn = document.getElementById("mode-standard");
const modeLoopBtn = document.getElementById("mode-loop");
const endLocationGroup = document.getElementById("end-location-group");
const loopDistanceGroup = document.getElementById("loop-distance-group");
const btnText = document.getElementById("btn-text");
const errorMsg = document.getElementById("error-message");
const routeForm = document.getElementById("route-form");

// Loop specific elements
const loopDistanceSlider = document.getElementById("loop-distance-slider");
const loopDistanceValue = document.getElementById("loop-distance-value");
const longLoopWarning = document.getElementById("long-loop-warning");
const longLoopWarningText = document.getElementById("long-loop-warning-text");
const varietyLevelSlider = document.getElementById("variety-level-slider");
const varietyLevelValue = document.getElementById("variety-level-value");
const preferPedestrianToggle = document.getElementById(
  "prefer-pedestrian-toggle",
);
const preferPavedToggle = document.getElementById("prefer-paved-toggle");
const preferLitToggle = document.getElementById("prefer-lit-toggle");
const heavilyAvoidUnlitToggle = document.getElementById(
  "heavily-avoid-unlit-toggle",
);
const avoidUnsafeToggle = document.getElementById("avoid-unsafe-toggle");
const groupNatureToggle = document.getElementById("group-nature-toggle");

export function initRoutingUI() {
  initModeToggles();
  initLoopControls();
  initLitToggles();
  initFormSubmit();
}

function initModeToggles() {
  if (modeStandardBtn)
    modeStandardBtn.addEventListener("click", () =>
      switchRoutingMode("standard"),
    );
  if (modeLoopBtn)
    modeLoopBtn.addEventListener("click", () => switchRoutingMode("loop"));
}

function switchRoutingMode(mode) {
  setRoutingMode(mode);

  // UI Update
  const isStandard = mode === "standard";
  if (modeStandardBtn) modeStandardBtn.classList.toggle("active", isStandard);
  if (modeLoopBtn) modeLoopBtn.classList.toggle("active", !isStandard);

  if (endLocationGroup)
    endLocationGroup.classList.toggle("hidden", !isStandard);
  if (loopDistanceGroup)
    loopDistanceGroup.classList.toggle("hidden", isStandard);

  if (btnText) btnText.textContent = isStandard ? "Find Route" : "Find Loop";

  console.log(`[App] Routing mode: ${mode}`);
}

function initLoopControls() {
  // Loop Distance Slider
  if (loopDistanceSlider) {
    loopDistanceSlider.addEventListener("input", () => {
      const val = parseFloat(loopDistanceSlider.value);
      loopDistanceValue.textContent = `${val.toFixed(1)} km`;
      updateLoopDistanceWarning(val);
    });
  }

  // Preset Dist Buttons
  document.querySelectorAll(".preset-dist-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (loopDistanceSlider) {
        loopDistanceSlider.value = btn.dataset.dist;
        loopDistanceSlider.dispatchEvent(new Event("input"));
      }
    });
  });

  // Direction Bias
  document.querySelectorAll(".direction-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document
        .querySelectorAll(".direction-btn")
        .forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      setSelectedDirection(btn.dataset.direction);
    });
  });

  // Variety Slider
  if (varietyLevelSlider && varietyLevelValue) {
    const labels = ["Off", "Low", "Med", "High"];
    varietyLevelSlider.addEventListener("input", () => {
      const level = parseInt(varietyLevelSlider.value);
      varietyLevelValue.textContent = labels[level] || level;
    });
  }
}

function initLitToggles() {
  // Mutual exclusivity: "Prefer lit" and "Heavily avoid unlit" are
  // different strengths of the same feature. Enabling one unchecks the other.
  if (preferLitToggle && heavilyAvoidUnlitToggle) {
    preferLitToggle.addEventListener("change", () => {
      if (preferLitToggle.checked) {
        heavilyAvoidUnlitToggle.checked = false;
      }
    });
    heavilyAvoidUnlitToggle.addEventListener("change", () => {
      if (heavilyAvoidUnlitToggle.checked) {
        preferLitToggle.checked = false;
      }
    });
  }
}

function updateLoopDistanceWarning(km) {
  if (!longLoopWarning) return;
  longLoopWarning.classList.remove("hidden");

  if (km > 25) {
    longLoopWarning.className =
      "p-3 rounded-lg border transition-all loop-warning-red";
    longLoopWarningText.innerHTML =
      "<strong>Very long route!</strong> Distances over 25 km will take significantly longer and may timeout.";
  } else if (km > 20) {
    longLoopWarning.className =
      "p-3 rounded-lg border transition-all loop-warning-orange";
    longLoopWarningText.innerHTML =
      "<strong>Long route.</strong> Distances over 20 km may take a moment to calculate.";
  } else if (km > 15) {
    longLoopWarning.className =
      "p-3 rounded-lg border transition-all loop-warning-amber";
    longLoopWarningText.textContent =
      "Routes over 15 km may take a moment to calculate.";
  } else {
    longLoopWarning.classList.add("hidden");
  }
}

function initFormSubmit() {
  console.log("[RoutingUI] initFormSubmit called. routeForm:", routeForm);
  if (routeForm) {
    routeForm.addEventListener("submit", async (e) => {
      console.log("[RoutingUI] Form submit event fired");
      e.preventDefault();
      if (appState.routingMode === "loop") {
        await handleLoopSubmit();
      } else {
        await handleStandardSubmit();
      }
    });
  } else {
    console.error("[RoutingUI] routeForm not found during init!");
  }
}

// ----------------------------------------------------------------------------
// HANDLERS
// ----------------------------------------------------------------------------

async function handleStandardSubmit() {
  if (!startState.lat || !endState.lat) {
    showError("Please select both a start and end location.");
    return;
  }

  const payload = {
    start_lat: startState.lat,
    start_lon: startState.lon,
    end_lat: endState.lat,
    end_lon: endState.lon,
  };

  const scenicWeights = getScenicWeights();
  if (scenicWeights) {
    payload.use_wsm = true;
    payload.weights = scenicWeights;
    if (groupNatureToggle && groupNatureToggle.checked) {
      payload.combine_nature = true;
    }
  }

  // Add Advanced Toggles
  if (preferPedestrianToggle && preferPedestrianToggle.checked)
    payload.prefer_pedestrian = true;
  if (preferPavedToggle && preferPavedToggle.checked)
    payload.prefer_paved = true;
  if (preferLitToggle && preferLitToggle.checked) payload.prefer_lit = true;
  if (heavilyAvoidUnlitToggle && heavilyAvoidUnlitToggle.checked)
    payload.heavily_avoid_unlit = true;
  if (avoidUnsafeToggle && avoidUnsafeToggle.checked)
    payload.avoid_unsafe_roads = true;

  setLoadingState("Calculating route...");
  hideResults();

  try {
    const response = await createRouteTask(payload);
    const data = await response.json();
    console.log("[RoutingUI] Route Task Response:", data);

    if (response.ok) {
      if (data.task_id) {
        // Async: Poll for result
        pollTask(
          data.task_id,
          (result) => {
            // Check if this was just a graph build (no route data yet)
            if (!result.routes && !result.route_coords && result.node_count) {
              console.log(
                "[RoutingUI] Graph build complete. Re-requesting route...",
              );
              // Re-submit to trigger sync calculation now that graph exists
              handleStandardSubmit();
            } else {
              onRouteSuccess(result);
            }
          },
          (err) => showError(err),
        );
      } else if (data.routes || data.route_coords) {
        // Sync: Immediate result
        onRouteSuccess(data);
      } else {
        showError(data.error || "Failed to start routing task");
        clearLoadingState();
      }
    } else {
      showError(data.error || "Network response was not ok");
      clearLoadingState();
    }
  } catch (err) {
    console.error("[RoutingUI] Handle Standard Submit Error:", err);
    showError(`Application error: ${err.message}`);
    clearLoadingState();
  }
}

async function handleLoopSubmit() {
  if (!startState.lat) {
    showError("Please set a start location.");
    return;
  }

  const distKm = parseFloat(loopDistanceSlider ? loopDistanceSlider.value : 5);
  const payload = {
    start_lat: startState.lat,
    start_lon: startState.lon,
    distance_km: distKm,
    directional_bias: appState.selectedDirection,
    variety_level: varietyLevelSlider ? parseInt(varietyLevelSlider.value) : 0,
    prefer_pedestrian: preferPedestrianToggle
      ? preferPedestrianToggle.checked
      : false,
    prefer_paved: preferPavedToggle ? preferPavedToggle.checked : false,
    prefer_lit: preferLitToggle ? preferLitToggle.checked : false,
    heavily_avoid_unlit: heavilyAvoidUnlitToggle
      ? heavilyAvoidUnlitToggle.checked
      : false,
    avoid_unsafe_roads: avoidUnsafeToggle ? avoidUnsafeToggle.checked : false,
  };

  const scenicWeights = getScenicWeights();
  if (scenicWeights) {
    payload.use_wsm = true;
    payload.weights = scenicWeights;
    if (groupNatureToggle && groupNatureToggle.checked) {
      payload.combine_nature = true;
    }
  }

  setLoadingState("Calculating loop...");
  hideResults();

  try {
    const response = await createLoopTask(payload);
    const data = await response.json();

    if (response.ok) {
      if (data.task_id) {
        pollTask(data.task_id, onLoopSuccess, (err) => showError(err));
      } else if (data.loops || data.route_coords || data.routes) {
        onLoopSuccess(data);
      } else {
        showError(data.error || "Failed to start loop task");
        clearLoadingState();
      }
    } else {
      showError(data.error || "Network response was not ok");
      clearLoadingState();
    }
  } catch (err) {
    showError("Network error. Please try again.");
    clearLoadingState();
  }
}

// ----------------------------------------------------------------------------
// SUCCESS CALLBACKS
// ----------------------------------------------------------------------------

function onRouteSuccess(result) {
  console.log("[RoutingUI] onRouteSuccess:", result);
  clearLoadingState();

  if (!result || (!result.routes && !result.route_coords)) {
    console.error("[RoutingUI] Invalid route result:", result);
    showError("Received invalid route data from server.");
    return;
  }

  // Handle legacy single-route response (shim for compatibility)
  if (!result.routes && result.route_coords) {
    console.warn(
      "[RoutingUI] Received legacy single-route format, converting...",
    );
    result.routes = {
      balanced: {
        route_coords: result.route_coords,
        stats: result.stats || {},
        colour: "#3B82F6", // Default blue
      },
    };
    // Ensure stats are populated if missing from root
    if (!result.routes.balanced.stats.distance_km && result.distance_km) {
      result.routes.balanced.stats.distance_km = result.distance_km;
    }
  }

  switchView("routes-view");

  // Store result in state
  routeState.routes = result.routes;
  routeState.duplicates = detectDuplicates(result.routes);
  routeState.selected = "balanced"; // default

  // Render Results
  renderRouteOptions(result.routes);
  updateStatsForRoute("balanced");

  // Draw on map
  if (mapController) {
    console.log(
      "[RoutingUI] Calling mapController.displayMultipleRoutes with:",
      result.routes,
    );
    mapController.displayMultipleRoutes(result.routes);
  } else {
    console.error("[RoutingUI] mapController is null or undefined!");
  }
}

function onLoopSuccess(result) {
  clearLoadingState();
  console.log("[RoutingUI] onLoopSuccess with:", result);
  switchView("routes-view");

  if (mapController) {
    if (result.loops && Array.isArray(result.loops)) {
      // New Multi-loop response
      console.log("[RoutingUI] Displaying multiple loops:", result.loops);
      mapController.displayMultipleLoops(result.loops);

      // Render loop cards
      renderLoopOptions(result.loops);

      // Set initial selection logic if needed
      if (result.loops.length > 0) {
        loopState.selectedId = result.loops[0].id;
      }
    } else {
      // Legacy single loop or wrapped result
      console.log("[RoutingUI] Displaying single loop result");
      const loops = [result];
      mapController.displayMultipleLoops(loops);
      renderLoopOptions(loops);
    }

    if (result.bbox) {
      mapController.map.fitBounds(result.bbox);
    }
  }

  // Update stats manually for loop (since it doesn't use the standard multi-route card UI yet)
  // Or if it does, adapt here.
  if (result.stats) {
    const statDistance = document.getElementById("stat-distance");
    const statTime = document.getElementById("stat-time");
    if (statDistance) statDistance.textContent = result.stats.distance_km;
    if (statTime) statTime.textContent = result.stats.time_min;

    const routeStats = document.getElementById("route-stats");
    if (routeStats) routeStats.classList.remove("hidden");
  }
}

function showError(msg) {
  if (errorMsg) {
    errorMsg.textContent = msg;
    errorMsg.classList.remove("hidden");
  }
  clearLoadingState();
}

/**
 * Detect duplicate routes (same geometry)
 */
function detectDuplicates(routes) {
  const duplicates = {};
  const types = ["baseline", "extremist", "balanced"];

  // Simple check: compare distance and time (could compare geometry hashes ideally)
  const signatures = {};

  types.forEach((type) => {
    if (!routes[type]) return;
    const sig = `${routes[type].stats.distance_km}-${routes[type].stats.time_min}`;
    if (signatures[sig]) {
      duplicates[type] = signatures[sig]; // Maps current type -> original type
    } else {
      signatures[sig] = type;
    }
  });

  return duplicates;
}
