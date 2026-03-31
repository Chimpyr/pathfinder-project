/**
 * Loop Demo Player
 *
 * Replays a route-focused story of loop solver milestones as map overlays.
 * Includes a scrub timeline so users can inspect individual steps.
 */

import { mapController } from "./map_manager.js";

const FRAME_DELAY_MS = 1000;
const BEARING_LINE_METRES = 900;
const PAUSE_POLL_MS = 120;
const BEARING_TOLERANCE_DEG = 1.0;
const MAX_ROUTE_VIEW_POINTS = 40;
const MAX_LEG_VISUAL_STEPS = 4;

let demoBaseLayerGroup = null;
let demoStageLayerGroup = null;
let playbackToken = 0;
let currentFrames = [];
let currentIndex = 0; // Next step index to render while autoplaying.
let lastRenderedIndex = -1;
let loadedStartPoint = null;
let isPlaying = false;
let isPaused = false;
let playbackSeed = {
  selectedLoop: null,
  focusBearing: null,
  focusShapeSides: null,
  focusType: null,
};
let playbackState = createPlaybackStateFromSeed(playbackSeed);

const ui = {
  isInitialised: false,
  container: null,
  status: null,
  note: null,
  scrubber: null,
  stepIndicator: null,
  playToggle: null,
  skipBtn: null,
  stopBtn: null,
};

function setMapFocusMode(active) {
  const mapElement =
    mapController?.map?.getContainer?.() || document.getElementById("map");
  if (!mapElement) return;

  mapElement.classList.toggle("loop-demo-focus", Boolean(active));
}

function createPlaybackStateFromSeed(seed) {
  return {
    targetDistanceM: null,
    focusBearing: seed.focusBearing ?? null,
    focusShapeSides: seed.focusShapeSides ?? null,
    focusType: seed.focusType ?? null,
    selectedLoop: seed.selectedLoop ?? null,
    currentBearing: null,
    lastProjectedPoints: [],
    lastSnappedPoints: [],
    lastActualDistanceM: null,
  };
}

function updateControlsVisibility(visible) {
  if (!ui.container) return;
  ui.container.classList.toggle("hidden", !visible);
  setMapFocusMode(visible);
}

function updateStatus(text) {
  if (!ui.status) return;
  ui.status.textContent = text || "";
}

function updateNote(text) {
  if (!ui.note) return;
  ui.note.textContent = text || "";
}

function updateStepIndicator(index, total) {
  if (!ui.stepIndicator) return;
  if (!Number.isFinite(index) || !total) {
    ui.stepIndicator.textContent = "Step 0 / 0";
    return;
  }

  ui.stepIndicator.textContent = `Step ${index + 1} / ${total}`;
}

function configureScrubber(totalSteps) {
  if (!ui.scrubber) return;

  const total = Math.max(0, Number(totalSteps) || 0);
  const maxValue = Math.max(1, total);
  ui.scrubber.min = "1";
  ui.scrubber.max = String(maxValue);
  ui.scrubber.step = "1";
  ui.scrubber.value = "1";
  ui.scrubber.disabled = total <= 1;
}

function syncScrubber(displayedIndex) {
  if (!ui.scrubber || !currentFrames.length) return;
  const index = Math.max(0, Math.min(currentFrames.length - 1, displayedIndex));
  ui.scrubber.value = String(index + 1);
}

function updatePlayButton() {
  if (!ui.playToggle) return;

  const icon = ui.playToggle.querySelector("i");
  const text = ui.playToggle.querySelector("span");

  if (isPlaying && !isPaused) {
    if (icon) icon.className = "fas fa-pause mr-1";
    if (text) text.textContent = "Pause";
    return;
  }

  if (
    currentFrames.length > 0 &&
    currentIndex > 0 &&
    currentIndex < currentFrames.length
  ) {
    if (icon) icon.className = "fas fa-play mr-1";
    if (text) text.textContent = "Resume";
    return;
  }

  if (currentFrames.length > 0 && currentIndex >= currentFrames.length) {
    if (icon) icon.className = "fas fa-rotate-left mr-1";
    if (text) text.textContent = "Replay";
    return;
  }

  if (icon) icon.className = "fas fa-play mr-1";
  if (text) text.textContent = "Play";
}

function stopAutoPlayback() {
  playbackToken += 1;
  isPlaying = false;
  isPaused = false;
  updatePlayButton();
}

function stopPlayback({ clearFrames = false, clearVisuals = true } = {}) {
  stopAutoPlayback();

  if (clearVisuals) {
    clearLayers();
  }

  if (clearFrames) {
    currentFrames = [];
    currentIndex = 0;
    lastRenderedIndex = -1;
    loadedStartPoint = null;
    playbackSeed = {
      selectedLoop: null,
      focusBearing: null,
      focusShapeSides: null,
      focusType: null,
    };
    playbackState = createPlaybackStateFromSeed(playbackSeed);
    configureScrubber(0);
    updateStepIndicator(null, 0);
    updateNote("Select a loop demo to begin.");
  }
}

function startPlayback() {
  if (!currentFrames.length || !Array.isArray(loadedStartPoint)) {
    return;
  }

  if (isPlaying && isPaused) {
    isPaused = false;
    updateStatus("Demo resumed.");
    updatePlayButton();
    return;
  }

  if (isPlaying) {
    return;
  }

  if (currentIndex >= currentFrames.length) {
    currentIndex = 0;
  }

  isPlaying = true;
  isPaused = false;
  updatePlayButton();

  const localToken = ++playbackToken;
  void runPlayback(localToken);
}

function pausePlayback() {
  if (!isPlaying) return;

  isPaused = true;
  const shown =
    lastRenderedIndex >= 0
      ? `${lastRenderedIndex + 1}/${currentFrames.length}`
      : "0/0";
  updateStatus(`Paused on step ${shown}.`);
  updatePlayButton();
}

function ensureLayerGroup() {
  if (!mapController || !mapController.map || typeof L === "undefined") {
    return null;
  }

  if (!demoBaseLayerGroup) {
    demoBaseLayerGroup = L.layerGroup().addTo(mapController.map);
  }

  if (!demoStageLayerGroup) {
    demoStageLayerGroup = L.layerGroup().addTo(mapController.map);
  }

  return {
    base: demoBaseLayerGroup,
    stage: demoStageLayerGroup,
  };
}

function clearStageLayer() {
  if (demoStageLayerGroup) {
    demoStageLayerGroup.clearLayers();
  }
}

function clearLayers() {
  if (demoBaseLayerGroup) {
    demoBaseLayerGroup.clearLayers();
  }

  if (demoStageLayerGroup) {
    demoStageLayerGroup.clearLayers();
  }
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitWhilePaused(localToken) {
  while (isPaused && localToken === playbackToken) {
    await delay(PAUSE_POLL_MS);
  }
  return localToken === playbackToken;
}

function projectPoint(lat, lon, bearingDeg, distanceM) {
  const earthRadius = 6371000;
  const bearing = (bearingDeg * Math.PI) / 180;
  const lat1 = (lat * Math.PI) / 180;
  const lon1 = (lon * Math.PI) / 180;
  const angularDistance = distanceM / earthRadius;

  const lat2 = Math.asin(
    Math.sin(lat1) * Math.cos(angularDistance) +
      Math.cos(lat1) * Math.sin(angularDistance) * Math.cos(bearing),
  );

  const lon2 =
    lon1 +
    Math.atan2(
      Math.sin(bearing) * Math.sin(angularDistance) * Math.cos(lat1),
      Math.cos(angularDistance) - Math.sin(lat1) * Math.sin(lat2),
    );

  return [(lat2 * 180) / Math.PI, (lon2 * 180) / Math.PI];
}

function clampStepIndex(index) {
  if (!currentFrames.length) return -1;
  const i = Number(index);
  if (!Number.isFinite(i)) return -1;
  return Math.max(0, Math.min(currentFrames.length - 1, Math.floor(i)));
}

function normaliseBearing(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return null;
  const wrapped = ((n % 360) + 360) % 360;
  return wrapped;
}

function bearingDelta(a, b) {
  if (!Number.isFinite(a) || !Number.isFinite(b)) return Infinity;
  const raw = Math.abs(a - b);
  return Math.min(raw, 360 - raw);
}

function parseShapeSides(value) {
  if (Number.isFinite(Number(value))) {
    return Number.parseInt(String(value), 10);
  }

  const token = String(value || "").trim();
  const match = token.match(/(\d+)/);
  if (!match) return null;
  return Number.parseInt(match[1], 10);
}

function normaliseLoopType(value) {
  const token = String(value || "")
    .trim()
    .toLowerCase()
    .replaceAll("_", "-");

  if (token.includes("out-and-back") || token === "out-back") {
    return "out-and-back";
  }

  return token || null;
}

function parseShapeSidesFromSubtitle(subtitle) {
  const token = String(subtitle || "").toLowerCase();
  if (!token) return null;

  if (token.includes("triangle")) return 3;
  if (token.includes("quadrilateral") || token.includes("square")) return 4;
  if (token.includes("pentagon")) return 5;
  if (token.includes("hexagon")) return 6;

  return null;
}

function parseBearingFromSubtitle(subtitle) {
  const token = String(subtitle || "")
    .toLowerCase()
    .replaceAll("_", "-")
    .replaceAll(" ", "-");

  if (!token) return null;

  const directionMap = [
    ["north-east", 45],
    ["northeast", 45],
    ["east", 90],
    ["south-east", 135],
    ["southeast", 135],
    ["south", 180],
    ["south-west", 225],
    ["southwest", 225],
    ["west", 270],
    ["north-west", 315],
    ["northwest", 315],
    ["north", 0],
  ];

  for (const [key, bearing] of directionMap) {
    if (token.includes(key)) {
      return bearing;
    }
  }

  return null;
}

function extractFocusFromLoop(loop) {
  const metadata =
    loop && typeof loop.metadata === "object" ? loop.metadata : {};
  const subtitle = String(loop?.label_subtitle || "");
  const bearing =
    normaliseBearing(metadata.bearing) ??
    normaliseBearing(parseBearingFromSubtitle(subtitle));
  const shapeSides =
    parseShapeSides(metadata.shape_sides ?? metadata.shape) ??
    parseShapeSidesFromSubtitle(subtitle);
  const loopType = normaliseLoopType(metadata.type);

  return {
    bearing,
    shapeSides,
    type: loopType,
  };
}

function frameHasMatchingBearing(frame, focusBearing) {
  if (!Number.isFinite(focusBearing)) return true;

  const frameBearing = normaliseBearing(frame.bearing);
  if (!Number.isFinite(frameBearing)) {
    return true;
  }

  return bearingDelta(frameBearing, focusBearing) <= BEARING_TOLERANCE_DEG;
}

function frameHasMatchingShape(frame, focusShapeSides) {
  if (!Number.isFinite(focusShapeSides)) return true;

  const frameShape = parseShapeSides(frame.shape_sides ?? frame.num_vertices);
  if (!Number.isFinite(frameShape)) {
    return true;
  }

  return frameShape === focusShapeSides;
}

function frameMatchesFocus(frame, focus) {
  if (!focus) return true;

  return (
    frameHasMatchingBearing(frame, focus.bearing) &&
    frameHasMatchingShape(frame, focus.shapeSides)
  );
}

function includeUniqueFrame(list, frame, seen) {
  if (!frame) return;
  if (seen.has(frame)) return;

  list.push(frame);
  seen.add(frame);
}

function findFirstFrame(frames, eventName, predicate = () => true) {
  for (const frame of frames) {
    if (!frame || frame.event !== eventName) continue;
    if (predicate(frame)) return frame;
  }

  return null;
}

function findMatchingFrames(frames, eventName, predicate = () => true) {
  const matches = [];
  for (const frame of frames) {
    if (!frame || frame.event !== eventName) continue;
    if (predicate(frame)) {
      matches.push(frame);
    }
  }
  return matches;
}

function buildNarrativeFrames(frames, focus) {
  const source = Array.isArray(frames) ? frames : [];
  const selected = [];
  const seen = new Set();

  includeUniqueFrame(selected, findFirstFrame(source, "solver_started"), seen);
  includeUniqueFrame(
    selected,
    findFirstFrame(source, "bearings_selected"),
    seen,
  );

  const isFallbackFocus = focus?.type === "out-and-back";
  if (isFallbackFocus) {
    [
      "fallback_started",
      "fallback_out_and_back_started",
      "fallback_waypoint_projected",
    ].forEach((eventName) => {
      includeUniqueFrame(
        selected,
        findFirstFrame(source, eventName, (frame) =>
          frameMatchesFocus(frame, focus),
        ),
        seen,
      );
    });

    const fallbackLegFrames = findMatchingFrames(
      source,
      "fallback_leg_routed",
      (frame) => frameMatchesFocus(frame, focus),
    );
    const fallbackSeenKeys = new Set();
    const fallbackDeduped = [];
    for (const frame of fallbackLegFrames) {
      const legIndex = Number(frame?.leg_index);
      const totalLegs = Number(frame?.total_legs);
      const key =
        Number.isFinite(legIndex) && Number.isFinite(totalLegs)
          ? `${legIndex}/${totalLegs}`
          : null;
      if (key && fallbackSeenKeys.has(key)) continue;
      if (key) fallbackSeenKeys.add(key);
      fallbackDeduped.push(frame);
      if (fallbackDeduped.length >= MAX_LEG_VISUAL_STEPS) break;
    }
    fallbackDeduped.forEach((frame) => {
      includeUniqueFrame(selected, frame, seen);
    });

    ["fallback_out_and_back_completed", "fallback_accepted"].forEach(
      (eventName) => {
        includeUniqueFrame(
          selected,
          findFirstFrame(source, eventName, (frame) =>
            frameMatchesFocus(frame, focus),
          ),
          seen,
        );
      },
    );
  } else {
    ["skeleton_projected", "skeleton_snapped"].forEach((eventName) => {
      includeUniqueFrame(
        selected,
        findFirstFrame(source, eventName, (frame) =>
          frameMatchesFocus(frame, focus),
        ),
        seen,
      );
    });

    const legFrames = findMatchingFrames(source, "leg_routed", (frame) =>
      frameMatchesFocus(frame, focus),
    );
    const seenLegKeys = new Set();
    const dedupedLegFrames = [];
    for (const frame of legFrames) {
      const legIndex = Number(frame?.leg_index);
      const totalLegs = Number(frame?.total_legs);
      const key =
        Number.isFinite(legIndex) && Number.isFinite(totalLegs)
          ? `${legIndex}/${totalLegs}`
          : null;
      if (key && seenLegKeys.has(key)) continue;
      if (key) seenLegKeys.add(key);
      dedupedLegFrames.push(frame);
      if (dedupedLegFrames.length >= MAX_LEG_VISUAL_STEPS) break;
    }
    dedupedLegFrames.forEach((frame) => {
      includeUniqueFrame(selected, frame, seen);
    });

    ["distance_evaluated", "tau_adjusted", "candidate_accepted"].forEach(
      (eventName) => {
        includeUniqueFrame(
          selected,
          findFirstFrame(source, eventName, (frame) =>
            frameMatchesFocus(frame, focus),
          ),
          seen,
        );
      },
    );
  }

  if (!selected.some((frame) => frame.event === "candidate_accepted")) {
    includeUniqueFrame(
      selected,
      findFirstFrame(source, "fallback_accepted", (frame) =>
        frameMatchesFocus(frame, focus),
      ),
      seen,
    );
  }

  includeUniqueFrame(
    selected,
    findFirstFrame(source, "solver_completed"),
    seen,
  );

  if (selected.length > 2) {
    return selected;
  }

  // Fallback: build a generic story if focus metadata cannot be matched.
  const relaxed = [];
  const relaxedSeen = new Set();
  [
    "solver_started",
    "bearings_selected",
    "skeleton_projected",
    "skeleton_snapped",
    "leg_routed",
    "fallback_leg_routed",
    "distance_evaluated",
    "tau_adjusted",
    "candidate_accepted",
    "fallback_accepted",
    "solver_completed",
  ].forEach((eventName) => {
    includeUniqueFrame(relaxed, findFirstFrame(source, eventName), relaxedSeen);
  });

  return relaxed;
}

function applyFrameContext(state, frame) {
  if (!frame || !frame.event) return;

  if (
    frame.event === "solver_started" &&
    typeof frame.target_distance_m === "number"
  ) {
    state.targetDistanceM = frame.target_distance_m;
  }

  if (frame.event === "bearings_selected") {
    const resolved = resolveBearingForFrame(frame, state);
    if (Number.isFinite(resolved)) {
      state.currentBearing = resolved;
    }
  }

  if (
    frame.event === "shape_attempt_started" ||
    frame.event === "polygon_attempt_started" ||
    frame.event === "fallback_started" ||
    frame.event === "fallback_out_and_back_started"
  ) {
    const directBearing = normaliseBearing(frame.bearing);
    if (Number.isFinite(directBearing)) {
      state.currentBearing = directBearing;
    }
  }

  if (frame.event === "skeleton_projected") {
    state.lastProjectedPoints = normalisePoints(frame.points);
  }

  if (frame.event === "skeleton_snapped") {
    state.lastSnappedPoints = normalisePoints(frame.points);
  }

  if (
    frame.event === "distance_evaluated" &&
    typeof frame.actual_distance_m === "number"
  ) {
    state.lastActualDistanceM = frame.actual_distance_m;
  }
}

function buildStateForStep(stepIndex) {
  const state = createPlaybackStateFromSeed(playbackSeed);
  for (let i = 0; i <= stepIndex; i += 1) {
    applyFrameContext(state, currentFrames[i]);
  }
  return state;
}

function drawStartPoint(startPoint, layerGroup) {
  if (!Array.isArray(startPoint) || startPoint.length < 2) return;

  L.circleMarker(startPoint, {
    radius: 7,
    color: "#15803d",
    weight: 3,
    fillColor: "#22c55e",
    fillOpacity: 0.95,
  }).addTo(layerGroup);

  L.circle(startPoint, {
    radius: 30,
    color: "#15803d",
    weight: 1,
    opacity: 0.4,
    fillOpacity: 0,
  }).addTo(layerGroup);
}

function drawMutedSelectedLoop(loop, layerGroup) {
  if (
    !loop ||
    !Array.isArray(loop.route_coords) ||
    loop.route_coords.length < 2
  ) {
    return;
  }

  L.polyline(loop.route_coords, {
    color: loop.colour || "#3B82F6",
    weight: 5,
    opacity: 0.22,
    dashArray: "10 8",
    lineJoin: "round",
  }).addTo(layerGroup);
}

function highlightSelectedLoop(loop, layerGroup) {
  if (
    !loop ||
    !Array.isArray(loop.route_coords) ||
    loop.route_coords.length < 2
  ) {
    return;
  }

  L.polyline(loop.route_coords, {
    color: loop.colour || "#3B82F6",
    weight: 6,
    opacity: 0.95,
    lineJoin: "round",
  }).addTo(layerGroup);
}

function downsampleRoutePoints(points) {
  if (!Array.isArray(points) || points.length <= MAX_ROUTE_VIEW_POINTS) {
    return Array.isArray(points) ? points : [];
  }

  const sampled = [];
  const stride = Math.max(1, Math.floor(points.length / MAX_ROUTE_VIEW_POINTS));
  for (let i = 0; i < points.length; i += stride) {
    sampled.push(points[i]);
  }

  const last = points[points.length - 1];
  if (sampled[sampled.length - 1] !== last) {
    sampled.push(last);
  }

  return sampled;
}

function drawTargetDistanceGuide(state, startPoint, layerGroup) {
  if (!Number.isFinite(state.targetDistanceM) || state.targetDistanceM <= 0) {
    return;
  }

  L.circle(startPoint, {
    radius: state.targetDistanceM,
    color: "#2563eb",
    weight: 2,
    opacity: 0.6,
    dashArray: "7 7",
    fillOpacity: 0,
  }).addTo(layerGroup);
}

function drawBearingOptions(frame, state, startPoint, layerGroup) {
  const bearings = Array.isArray(frame.bearings)
    ? frame.bearings
        .map((value) => normaliseBearing(value))
        .filter((value) => Number.isFinite(value))
    : [];

  if (!bearings.length) {
    const fallbackBearing = resolveBearingForFrame(frame, state);
    if (Number.isFinite(fallbackBearing)) {
      bearings.push(fallbackBearing);
    }
  }

  if (!bearings.length) return;

  const lineDistance = Number.isFinite(state.targetDistanceM)
    ? Math.max(320, Math.min(1800, state.targetDistanceM * 0.22))
    : BEARING_LINE_METRES;

  const selectedBearing = resolveBearingForFrame(frame, state);
  if (Number.isFinite(selectedBearing)) {
    state.currentBearing = selectedBearing;
  }

  bearings.forEach((bearing) => {
    const endpoint = projectPoint(
      startPoint[0],
      startPoint[1],
      bearing,
      lineDistance,
    );
    const isSelected = Number.isFinite(selectedBearing)
      ? bearingDelta(bearing, selectedBearing) <= BEARING_TOLERANCE_DEG
      : false;

    if (isSelected) {
      L.polyline([startPoint, endpoint], {
        color: "#e0f2fe",
        weight: 8,
        opacity: 0.95,
      }).addTo(layerGroup);
    }

    L.polyline([startPoint, endpoint], {
      color: isSelected ? "#1e3a8a" : "#0ea5e9",
      weight: isSelected ? 4.5 : 3,
      opacity: isSelected ? 1 : 0.78,
      dashArray: isSelected ? "" : "8 6",
    }).addTo(layerGroup);

    L.circleMarker(endpoint, {
      radius: isSelected ? 6 : 4,
      color: isSelected ? "#1e3a8a" : "#0369a1",
      weight: 2,
      fillColor: isSelected ? "#60a5fa" : "#67e8f9",
      fillOpacity: isSelected ? 1 : 0.88,
    }).addTo(layerGroup);
  });
}

function resolveBearingForFrame(frame, state) {
  const directBearing = normaliseBearing(frame.bearing);
  if (Number.isFinite(directBearing)) {
    return directBearing;
  }

  const candidates = Array.isArray(frame.bearings) ? frame.bearings : [];
  if (!candidates.length) return null;

  const normalised = candidates
    .map((value) => normaliseBearing(value))
    .filter((value) => Number.isFinite(value));

  if (!normalised.length) return null;

  if (Number.isFinite(state.focusBearing)) {
    return normalised.reduce((best, current) =>
      bearingDelta(current, state.focusBearing) <
      bearingDelta(best, state.focusBearing)
        ? current
        : best,
    );
  }

  return normalised[0];
}

function drawBearingFrame(frame, state, startPoint, layerGroup) {
  const bearing = resolveBearingForFrame(frame, state);
  if (!Number.isFinite(bearing)) return;

  state.currentBearing = bearing;

  const lineDistance = Number.isFinite(state.targetDistanceM)
    ? Math.max(300, Math.min(1800, state.targetDistanceM * 0.22))
    : BEARING_LINE_METRES;

  const endpoint = projectPoint(
    startPoint[0],
    startPoint[1],
    bearing,
    lineDistance,
  );

  L.polyline([startPoint, endpoint], {
    color: "#2563eb",
    weight: 4,
    opacity: 0.95,
  }).addTo(layerGroup);

  L.circleMarker(endpoint, {
    radius: 5,
    color: "#1d4ed8",
    weight: 2,
    fillColor: "#60a5fa",
    fillOpacity: 0.95,
  }).addTo(layerGroup);

  L.circle(startPoint, {
    radius: lineDistance,
    color: "#3b82f6",
    weight: 1,
    opacity: 0.45,
    dashArray: "6 6",
    fillOpacity: 0,
  }).addTo(layerGroup);
}

function normalisePoints(framePoints) {
  const points = Array.isArray(framePoints) ? framePoints : [];
  return points
    .filter((point) => Array.isArray(point) && point.length >= 2)
    .map((point) => [Number(point[0]), Number(point[1])])
    .filter((point) => Number.isFinite(point[0]) && Number.isFinite(point[1]));
}

function buildSkeletonNodes(startPoint, points) {
  const skeletonNodes = [startPoint, ...points];
  const unique = skeletonNodes.filter((point, idx, arr) => {
    return (
      idx ===
      arr.findIndex((candidate) => {
        return (
          Math.abs(candidate[0] - point[0]) < 1e-8 &&
          Math.abs(candidate[1] - point[1]) < 1e-8
        );
      })
    );
  });
  return unique;
}

function drawSkeletonFromPoints(startPoint, points, layerGroup, options = {}) {
  const nodes = buildSkeletonNodes(startPoint, points);
  if (nodes.length < 2) return;

  const path = nodes.length > 2 ? [...nodes, nodes[0]] : nodes;

  L.polyline(path, {
    color: options.color || "#f97316",
    weight: options.weight || 4,
    opacity: options.opacity || 0.9,
    dashArray: options.dashArray ?? "6 4",
    lineJoin: "round",
  }).addTo(layerGroup);

  const pointRadius = Number.isFinite(options.pointRadius)
    ? options.pointRadius
    : 4;

  nodes.slice(1).forEach((point) => {
    if (options.haloRadius && options.haloColor) {
      L.circleMarker(point, {
        radius: options.haloRadius,
        color: options.haloColor,
        weight: 1,
        fillColor: options.haloFillColor || options.haloColor,
        fillOpacity: options.haloOpacity ?? 0.18,
        opacity: options.haloStrokeOpacity ?? 0.45,
      }).addTo(layerGroup);
    }

    L.circleMarker(point, {
      radius: pointRadius,
      color: options.color || "#f97316",
      weight: 2,
      fillColor: options.fillColor || "#fdba74",
      fillOpacity: 0.95,
    }).addTo(layerGroup);
  });
}

function drawTheoreticalSkeleton(frame, startPoint, layerGroup) {
  const points = normalisePoints(frame.points);
  if (!points.length) return;

  drawSkeletonFromPoints(startPoint, points, layerGroup, {
    color: "#f97316",
    fillColor: "#fdba74",
    dashArray: "6 4",
    weight: 3.5,
    pointRadius: 5,
  });
}

function drawSnappedSkeleton(frame, startPoint, layerGroup) {
  const points = normalisePoints(frame.points);
  if (!points.length) return;

  drawSkeletonFromPoints(startPoint, points, layerGroup, {
    color: "#16a34a",
    fillColor: "#86efac",
    dashArray: "",
    weight: 4,
    pointRadius: 5,
    haloRadius: 10,
    haloColor: "#16a34a",
    haloFillColor: "#4ade80",
    haloOpacity: 0.2,
    haloStrokeOpacity: 0.4,
  });
}

function drawDistanceComparison(frame, state, startPoint, layerGroup) {
  const targetDistance = Number.isFinite(state.targetDistanceM)
    ? state.targetDistanceM
    : null;
  const actualDistance = Number.isFinite(frame.actual_distance_m)
    ? frame.actual_distance_m
    : Number.isFinite(state.lastActualDistanceM)
      ? state.lastActualDistanceM
      : null;

  if (targetDistance) {
    L.circle(startPoint, {
      radius: targetDistance,
      color: "#2563eb",
      weight: 2,
      opacity: 0.6,
      dashArray: "7 7",
      fillOpacity: 0,
    }).addTo(layerGroup);
  }

  if (actualDistance) {
    L.circle(startPoint, {
      radius: actualDistance,
      color: "#0ea5e9",
      weight: 2,
      opacity: 0.85,
      dashArray: "",
      fillOpacity: 0,
    }).addTo(layerGroup);
  }
}

function scalePointsFromStart(points, startPoint, ratio) {
  if (!Array.isArray(points) || !points.length || !Number.isFinite(ratio)) {
    return [];
  }

  return points.map((point) => {
    const lat = startPoint[0] + (point[0] - startPoint[0]) * ratio;
    const lon = startPoint[1] + (point[1] - startPoint[1]) * ratio;
    return [lat, lon];
  });
}

function drawTauAdjustment(frame, state, startPoint, layerGroup) {
  const tauBefore = Number(frame.tau_before);
  const tauAfter = Number(frame.tau_after);
  if (
    !Number.isFinite(tauBefore) ||
    !Number.isFinite(tauAfter) ||
    tauBefore === 0
  ) {
    return;
  }

  const basePoints = state.lastProjectedPoints.length
    ? state.lastProjectedPoints
    : state.lastSnappedPoints;
  if (basePoints.length) {
    drawSkeletonFromPoints(startPoint, basePoints, layerGroup, {
      color: "#f97316",
      fillColor: "#fdba74",
      dashArray: "6 4",
      weight: 3,
      pointRadius: 4,
    });

    const ratio = tauAfter / tauBefore;
    const scaledPoints = scalePointsFromStart(basePoints, startPoint, ratio);
    drawSkeletonFromPoints(startPoint, scaledPoints, layerGroup, {
      color: "#7c3aed",
      fillColor: "#c4b5fd",
      dashArray: "10 6",
      weight: 3,
      pointRadius: 4,
      haloRadius: 7,
      haloColor: "#7c3aed",
      haloFillColor: "#a78bfa",
      haloOpacity: 0.16,
      haloStrokeOpacity: 0.35,
    });
  }

  const delta = tauAfter - tauBefore;
  const sign = delta >= 0 ? "+" : "";
  const label = `tau ${tauBefore.toFixed(3)} -> ${tauAfter.toFixed(3)} (${sign}${delta.toFixed(3)})`;

  L.circleMarker(startPoint, {
    radius: 8,
    color: "#7c3aed",
    weight: 3,
    fillColor: "#a78bfa",
    fillOpacity: 0.92,
  })
    .bindTooltip(label, { direction: "top", opacity: 0.95 })
    .addTo(layerGroup);
}

function drawFallbackWaypointFrame(frame, startPoint, layerGroup) {
  const waypoint = normalisePoints([frame.waypoint])[0];
  if (!waypoint) return;

  L.polyline([startPoint, waypoint], {
    color: "#d97706",
    weight: 3,
    opacity: 0.95,
    dashArray: "6 4",
  }).addTo(layerGroup);

  L.circleMarker(waypoint, {
    radius: 5,
    color: "#92400e",
    weight: 2,
    fillColor: "#fbbf24",
    fillOpacity: 0.92,
  }).addTo(layerGroup);
}

function drawLegRoutedFrame(frame, state, startPoint, layerGroup) {
  const path = normalisePoints(frame.path);

  if (state.lastSnappedPoints.length) {
    drawSkeletonFromPoints(startPoint, state.lastSnappedPoints, layerGroup, {
      color: "#16a34a",
      fillColor: "#86efac",
      dashArray: "4 4",
      weight: 2,
      pointRadius: 3.5,
      haloRadius: 7,
      haloColor: "#16a34a",
      haloFillColor: "#4ade80",
      haloOpacity: 0.12,
      haloStrokeOpacity: 0.26,
    });
  }

  if (path.length < 2) {
    return;
  }

  L.polyline([path[0], path[path.length - 1]], {
    color: "#a5b4fc",
    weight: 2,
    opacity: 0.8,
    dashArray: "6 6",
  }).addTo(layerGroup);

  L.polyline(path, {
    color: "#06b6d4",
    weight: 5,
    opacity: 0.96,
    lineJoin: "round",
    lineCap: "round",
  }).addTo(layerGroup);

  [path[0], path[path.length - 1]].forEach((point) => {
    L.circleMarker(point, {
      radius: 6,
      color: "#155e75",
      weight: 2,
      fillColor: "#67e8f9",
      fillOpacity: 0.95,
    }).addTo(layerGroup);
  });

  const mid = path[Math.floor(path.length / 2)];
  const legIndex = Number(frame.leg_index);
  const totalLegs = Number(frame.total_legs);
  const legLabel = Number.isFinite(legIndex) && Number.isFinite(totalLegs)
    ? `WSM A* leg ${legIndex}/${totalLegs}`
    : "WSM A* routed leg";

  L.circleMarker(mid, {
    radius: 4,
    color: "#0f172a",
    weight: 1,
    fillColor: "#22d3ee",
    fillOpacity: 0.95,
  })
    .bindTooltip(legLabel, { direction: "top", opacity: 0.95 })
    .addTo(layerGroup);
}

function drawAcceptedCandidate(state, layerGroup, isComplete = false) {
  if (state.selectedLoop) {
    highlightSelectedLoop(state.selectedLoop, layerGroup);

    const coords = Array.isArray(state.selectedLoop.route_coords)
      ? state.selectedLoop.route_coords
      : [];
    if (coords.length > 1) {
      const markerIndex = Math.floor(coords.length * 0.45);
      const markerPoint =
        coords[Math.max(0, Math.min(coords.length - 1, markerIndex))];
      L.circleMarker(markerPoint, {
        radius: isComplete ? 7 : 6,
        color: isComplete ? "#15803d" : "#2563eb",
        weight: 2,
        fillColor: isComplete ? "#22c55e" : "#60a5fa",
        fillOpacity: 0.95,
      }).addTo(layerGroup);
    }
  }
}

function renderBaseScene(baseLayer) {
  if (!baseLayer) return;

  baseLayer.clearLayers();
  if (loadedStartPoint) {
    drawStartPoint(loadedStartPoint, baseLayer);
  }

  if (playbackState.selectedLoop) {
    drawMutedSelectedLoop(playbackState.selectedLoop, baseLayer);
  }
}

function renderFrame(frame, state, startPoint, stageLayer) {
  if (!frame || !frame.event || !stageLayer) return;

  if (frame.event === "solver_started") {
    drawTargetDistanceGuide(state, startPoint, stageLayer);
    return;
  }

  if (frame.event === "bearings_selected") {
    drawBearingOptions(frame, state, startPoint, stageLayer);
    return;
  }

  if (
    frame.event === "shape_attempt_started" ||
    frame.event === "polygon_attempt_started"
  ) {
    drawBearingFrame(frame, state, startPoint, stageLayer);
    drawTargetDistanceGuide(state, startPoint, stageLayer);
    return;
  }

  if (
    frame.event === "fallback_started" ||
    frame.event === "fallback_out_and_back_started"
  ) {
    drawBearingFrame(frame, state, startPoint, stageLayer);
    drawTargetDistanceGuide(state, startPoint, stageLayer);
    return;
  }

  if (frame.event === "skeleton_projected") {
    drawTheoreticalSkeleton(frame, startPoint, stageLayer);
    return;
  }

  if (frame.event === "skeleton_snapped") {
    drawSnappedSkeleton(frame, startPoint, stageLayer);
    return;
  }

  if (frame.event === "distance_evaluated") {
    drawDistanceComparison(frame, state, startPoint, stageLayer);
    return;
  }

  if (frame.event === "leg_routed" || frame.event === "fallback_leg_routed") {
    drawLegRoutedFrame(frame, state, startPoint, stageLayer);
    return;
  }

  if (frame.event === "tau_adjusted") {
    drawTauAdjustment(frame, state, startPoint, stageLayer);
    return;
  }

  if (frame.event === "fallback_waypoint_projected") {
    drawFallbackWaypointFrame(frame, startPoint, stageLayer);
    return;
  }

  if (
    frame.event === "candidate_accepted" ||
    frame.event === "fallback_accepted" ||
    frame.event === "fallback_out_and_back_completed"
  ) {
    drawAcceptedCandidate(state, stageLayer);
    return;
  }

  if (frame.event === "solver_completed") {
    drawAcceptedCandidate(state, stageLayer, true);
  }
}

function formatDistanceMeters(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return null;
  if (n >= 1000) {
    return `${(n / 1000).toFixed(2)} km`;
  }
  return `${Math.round(n)} m`;
}

function formatBearing(value) {
  const bearing = normaliseBearing(value);
  if (!Number.isFinite(bearing)) return null;
  return `${Math.round(bearing)}deg`;
}

function describeFrame(frame, state, stepIndex, totalSteps) {
  const bearingText = formatBearing(frame.bearing ?? state.currentBearing);

  let message = "";

  switch (frame.event) {
    case "solver_started": {
      const target = formatDistanceMeters(frame.target_distance_m);
      message = target
        ? `Start point fixed. Target loop length set to ${target}.`
        : "Start point fixed. Solver begins.";
      break;
    }
    case "bearings_selected":
      message = bearingText
        ? `Choose candidate bearings; focus direction is ${bearingText}.`
        : "Choose candidate bearings.";
      break;
    case "shape_attempt_started": {
      const sides = parseShapeSides(frame.shape_sides);
      const shapeText = Number.isFinite(sides) ? `${sides}-point` : "polygon";
      message = bearingText
        ? `Prepare ${shapeText} skeleton attempt toward ${bearingText}.`
        : `Prepare ${shapeText} skeleton attempt.`;
      break;
    }
    case "polygon_attempt_started":
      message = "Prepare theoretical waypoint projection.";
      break;
    case "skeleton_projected":
      message = "Projected theoretical skeleton (orange) shown.";
      break;
    case "skeleton_snapped":
      message = "Skeleton snapped onto graph edges (green points + halos).";
      break;
    case "leg_routed": {
      const legIndex = Number(frame.leg_index);
      const totalLegs = Number(frame.total_legs);
      const legDistance = formatDistanceMeters(frame.leg_distance_m);
      if (Number.isFinite(legIndex) && Number.isFinite(totalLegs)) {
        message = legDistance
          ? `WSM A* routed leg ${legIndex}/${totalLegs} on graph edges (${legDistance}).`
          : `WSM A* routed leg ${legIndex}/${totalLegs} on graph edges.`;
      } else {
        message = "WSM A* routed a leg on graph edges.";
      }
      break;
    }
    case "fallback_leg_routed": {
      const legIndex = Number(frame.leg_index);
      const totalLegs = Number(frame.total_legs);
      const direction = String(frame.direction || "").trim();
      const legLabel =
        Number.isFinite(legIndex) && Number.isFinite(totalLegs)
          ? `Fallback WSM A* leg ${legIndex}/${totalLegs}`
          : "Fallback WSM A* leg";
      message = direction ? `${legLabel} (${direction}).` : `${legLabel}.`;
      break;
    }
    case "distance_evaluated": {
      const actual = formatDistanceMeters(frame.actual_distance_m);
      const deviation = Number(frame.deviation_percent);
      if (actual && Number.isFinite(deviation)) {
        message = `Distance check ${actual} (${deviation.toFixed(1)}% from target).`;
      } else {
        message = "Evaluate actual distance against target radius.";
      }
      break;
    }
    case "tau_adjusted": {
      const before = Number(frame.tau_before);
      const after = Number(frame.tau_after);
      if (Number.isFinite(before) && Number.isFinite(after)) {
        message = `Adjust shape scale (tau ${before.toFixed(3)} -> ${after.toFixed(3)}).`;
      } else {
        message = "Adjust shape scale and retry.";
      }
      break;
    }
    case "fallback_started":
      message = "Polygon attempts failed; switch to out-and-back fallback.";
      break;
    case "fallback_out_and_back_started":
      message = "Project turnaround waypoint for out-and-back.";
      break;
    case "fallback_waypoint_projected":
      message = "Fallback waypoint projected and snapped.";
      break;
    case "fallback_out_and_back_completed":
      message = "Fallback out-and-back legs connected.";
      break;
    case "candidate_accepted":
      message = "Candidate accepted and highlighted as the selected final loop.";
      break;
    case "fallback_accepted":
      message = "Fallback candidate accepted.";
      break;
    case "solver_completed":
      message = "Solver completed and ranked the returned loop options.";
      break;
    default:
      message = String(frame.event || "step").replaceAll("_", " ");
  }

  const loopLabel = state.selectedLoop?.label
    ? `${state.selectedLoop.label}: `
    : "";

  return `${loopLabel}${message} (${stepIndex}/${totalSteps})`;
}

function describeFrameNote(frame) {
  if (!frame || !frame.event) {
    return "";
  }

  switch (frame.event) {
    case "solver_started":
      return "Dashed blue radius marks the requested target loop distance from the start point.";
    case "bearings_selected":
      return "Dashed cyan rays are candidate bearings. The darkest blue ray is the selected bearing for this candidate.";
    case "skeleton_projected":
      return "Orange dashed skeleton is theoretical geometry before graph snapping.";
    case "skeleton_snapped":
      return "Green points (with halos) show snapped waypoints anchored to reachable graph nodes.";
    case "leg_routed":
    case "fallback_leg_routed":
      return "Cyan path shows one WSM A* leg between snapped waypoints. Purple dashed segment is straight-line reference only.";
    case "distance_evaluated":
      return "Dashed blue circle is target distance; solid cyan circle is this candidate's actual loop distance.";
    case "tau_adjusted":
      return "Orange shape is previous scale; purple shape is the tau-adjusted retry geometry.";
    case "candidate_accepted":
      return "Solid blue route is the accepted candidate. Any diagonal-looking segment is routed path, not a bearing guide.";
    case "solver_completed":
      return "Ranking complete for this candidate path. Use other loop cards to compare alternatives.";
    default:
      return "";
  }
}

function buildStepViewPoints(frame, state, startPoint) {
  const points = [];

  if (Array.isArray(startPoint) && startPoint.length >= 2) {
    points.push(startPoint);
  }

  if (state.selectedLoop && Array.isArray(state.selectedLoop.route_coords)) {
    points.push(...downsampleRoutePoints(state.selectedLoop.route_coords));
  }

  if (
    frame?.event === "skeleton_projected" ||
    frame?.event === "skeleton_snapped"
  ) {
    points.push(...normalisePoints(frame.points));
  }

  if (frame?.event === "leg_routed" || frame?.event === "fallback_leg_routed") {
    points.push(...normalisePoints(frame.path));
  }

  if (frame?.event === "fallback_waypoint_projected") {
    const waypoint = normalisePoints([frame.waypoint]);
    points.push(...waypoint);
  }

  if (
    frame?.event === "bearings_selected" ||
    frame?.event === "shape_attempt_started" ||
    frame?.event === "polygon_attempt_started" ||
    frame?.event === "fallback_started" ||
    frame?.event === "fallback_out_and_back_started"
  ) {
    const bearing = resolveBearingForFrame(frame, state);
    if (
      Number.isFinite(bearing) &&
      Array.isArray(startPoint) &&
      Number.isFinite(state.targetDistanceM)
    ) {
      const endpoint = projectPoint(
        startPoint[0],
        startPoint[1],
        bearing,
        Math.max(320, Math.min(1800, state.targetDistanceM * 0.22)),
      );
      points.push(endpoint);
    }
  }

  return points;
}

function fitStepView(frame, state, startPoint) {
  if (!mapController?.map || typeof L === "undefined") {
    return;
  }

  const points = buildStepViewPoints(frame, state, startPoint);
  if (points.length < 2) return;

  const bounds = L.latLngBounds(
    points.map((point) => L.latLng(point[0], point[1])),
  );
  if (!bounds.isValid()) return;

  mapController.map.fitBounds(bounds, {
    padding: [60, 60],
    maxZoom: 16,
    animate: false,
  });
}

function renderStep(stepIndex, options = {}) {
  const index = clampStepIndex(stepIndex);
  if (index < 0) return;

  const groups = ensureLayerGroup();
  if (!groups || !loadedStartPoint) return;

  playbackState = buildStateForStep(index);

  renderBaseScene(groups.base);
  clearStageLayer();

  const frame = currentFrames[index];
  renderFrame(frame, playbackState, loadedStartPoint, groups.stage);

  if (options.fitView) {
    fitStepView(frame, playbackState, loadedStartPoint);
  }

  lastRenderedIndex = index;
  syncScrubber(index);
  updateStepIndicator(index, currentFrames.length);
  updateStatus(
    describeFrame(frame, playbackState, index + 1, currentFrames.length),
  );
  updateNote(describeFrameNote(frame));
  updatePlayButton();
}

async function runPlayback(localToken) {
  if (!currentFrames.length || !loadedStartPoint) {
    stopPlayback({ clearFrames: true, clearVisuals: true });
    updateControlsVisibility(false);
    return;
  }

  const groups = ensureLayerGroup();
  if (!groups) {
    stopPlayback({ clearFrames: true, clearVisuals: true });
    updateControlsVisibility(false);
    return;
  }

  while (currentIndex < currentFrames.length) {
    if (localToken !== playbackToken) {
      return;
    }

    if (!(await waitWhilePaused(localToken))) {
      return;
    }

    renderStep(currentIndex);
    currentIndex += 1;

    if (currentIndex >= currentFrames.length) {
      break;
    }

    await delay(FRAME_DELAY_MS);
  }

  if (localToken !== playbackToken) {
    return;
  }

  isPlaying = false;
  isPaused = false;

  if (lastRenderedIndex >= 0) {
    const finalFrame = currentFrames[lastRenderedIndex];
    updateStatus(
      `${describeFrame(finalFrame, playbackState, lastRenderedIndex + 1, currentFrames.length)} Complete.`,
    );
  } else {
    updateStatus("Demo complete.");
  }

  updatePlayButton();
}

function skipToEnd() {
  if (!currentFrames.length || !loadedStartPoint) {
    return;
  }

  stopAutoPlayback();
  const lastIndex = currentFrames.length - 1;
  renderStep(lastIndex, { fitView: true });
  currentIndex = currentFrames.length;
  updateStatus(
    `${describeFrame(currentFrames[lastIndex], playbackState, lastIndex + 1, currentFrames.length)} Skipped to end.`,
  );
}

export function initLoopDemoPlayer() {
  if (ui.isInitialised) return;

  ui.container = document.getElementById("loop-demo-controls");
  if (!ui.container) {
    return;
  }

  ui.status = document.getElementById("loop-demo-status");
  ui.note = document.getElementById("loop-demo-note");
  ui.scrubber = document.getElementById("loop-demo-scrubber");
  ui.stepIndicator = document.getElementById("loop-demo-step-indicator");
  ui.playToggle = document.getElementById("loop-demo-play-toggle");
  ui.skipBtn = document.getElementById("loop-demo-skip-btn");
  ui.stopBtn = document.getElementById("loop-demo-stop-btn");

  ui.playToggle?.addEventListener("click", () => {
    if (!currentFrames.length) return;

    if (isPlaying && !isPaused) {
      pausePlayback();
    } else {
      startPlayback();
    }
  });

  ui.skipBtn?.addEventListener("click", () => {
    skipToEnd();
  });

  ui.scrubber?.addEventListener("input", () => {
    if (!currentFrames.length) return;

    stopAutoPlayback();
    const rawValue = Number(ui.scrubber.value);
    const selectedIndex = clampStepIndex(rawValue - 1);
    if (selectedIndex < 0) return;

    renderStep(selectedIndex, { fitView: true });
    currentIndex = selectedIndex + 1;
  });

  ui.stopBtn?.addEventListener("click", () => {
    stopAutoPlayback();
    clearLayers();
    currentIndex = 0;
    lastRenderedIndex = -1;
    configureScrubber(currentFrames.length);
    updateStepIndicator(null, currentFrames.length);
    updateStatus("Demo stopped. Scrub timeline or press Play.");
    updateNote("Use the timeline to inspect any step or press Play to continue.");
    if (currentFrames.length) {
      updateControlsVisibility(true);
    }
    updatePlayButton();
  });

  ui.isInitialised = true;
  updateControlsVisibility(false);
  configureScrubber(0);
  updateStepIndicator(null, 0);
  updateStatus("");
  updateNote("Select a loop demo to begin.");
  updatePlayButton();
}

export function cancelLoopDemoPlayback() {
  stopPlayback({ clearFrames: true, clearVisuals: true });
  updateControlsVisibility(false);
  updateStatus("");
  updateNote("Select a loop demo to begin.");
}

export async function playLoopDemo(loopDemo, startPoint, selectedLoop = null) {
  initLoopDemoPlayer();

  if (
    !loopDemo ||
    !Array.isArray(loopDemo.frames) ||
    loopDemo.frames.length === 0
  ) {
    cancelLoopDemoPlayback();
    return;
  }
  if (!Array.isArray(startPoint) || startPoint.length < 2) {
    cancelLoopDemoPlayback();
    return;
  }

  const layerGroup = ensureLayerGroup();
  if (!layerGroup) {
    cancelLoopDemoPlayback();
    return;
  }

  const focus = extractFocusFromLoop(selectedLoop);
  const narrativeFrames = buildNarrativeFrames(loopDemo.frames, focus);
  if (!narrativeFrames.length) {
    cancelLoopDemoPlayback();
    return;
  }

  stopPlayback({ clearFrames: false, clearVisuals: true });

  currentFrames = narrativeFrames;
  currentIndex = 0;
  lastRenderedIndex = -1;
  loadedStartPoint = [startPoint[0], startPoint[1]];
  playbackSeed = {
    selectedLoop,
    focusBearing: focus.bearing,
    focusShapeSides: focus.shapeSides,
    focusType: focus.type,
  };
  playbackState = createPlaybackStateFromSeed(playbackSeed);

  configureScrubber(currentFrames.length);
  updateStepIndicator(null, currentFrames.length);

  updateControlsVisibility(true);
  const loopLabel = selectedLoop?.label || "loop";
  updateStatus(`Loaded ${currentFrames.length} story steps for ${loopLabel}.`);
  updateNote("Autoplay will advance each step. Drag the timeline to inspect any step.");
  updatePlayButton();

  renderBaseScene(layerGroup.base);
  fitStepView(currentFrames[0], playbackState, loadedStartPoint);

  startPlayback();
}
