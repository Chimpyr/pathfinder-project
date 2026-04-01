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
const MAX_STACKED_LEGS_PER_RETRY = 24;
const MAX_CONTEXT_FAILED_RETRY_WINDOWS = 2;
const FRAME_CONTEXT_KEY = "__loopDemoFrameContext";
const FRAME_CONTEXT_FAILED_ATTEMPT = "failed_attempt";

const WSM_CURRENT_LEG_COLOR = "#e11d48";
const WSM_PREVIOUS_LEG_COLOR = "#fb7185";
const WSM_ENDPOINT_STROKE = "#9f1239";
const WSM_ENDPOINT_FILL = "#fecdd3";
const WSM_MARKER_FILL = "#f43f5e";
const WSM_REFERENCE_COLOR = "#94a3b8";

const CONTEXT_SELECTED_LOOP_OPACITY = 0.0;
const CONTEXT_OTHER_LOOP_OPACITY = 0.0;
const DEMO_NON_SELECTED_LOOP_OPACITY = 0.0;

const POLYGON_STORY_EVENTS = new Set([
  "shape_attempt_started",
  "retry_started",
  "polygon_attempt_started",
  "skeleton_projected",
  "skeleton_snapped",
  "leg_routed",
  "leg_failed",
  "distance_evaluated",
  "tau_adjusted",
  "candidate_accepted",
  "shape_attempt_failed",
]);

const FALLBACK_STORY_EVENTS = new Set([
  "fallback_started",
  "fallback_out_and_back_started",
  "fallback_waypoint_projected",
  "fallback_leg_routed",
  "fallback_out_and_back_completed",
  "fallback_accepted",
  "fallback_rejected",
  "fallback_out_and_back_failed",
]);

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
  prevFrameBtn: null,
  nextFrameBtn: null,
  skipBtn: null,
  stopBtn: null,
};

function updateFrameStepButtons() {
  const hasFrames = currentFrames.length > 0;
  const shownIndex =
    lastRenderedIndex >= 0
      ? lastRenderedIndex
      : hasFrames
        ? Math.max(0, Math.min(currentIndex, currentFrames.length - 1))
        : -1;

  if (ui.prevFrameBtn) {
    ui.prevFrameBtn.disabled = !hasFrames || shownIndex <= 0;
  }

  if (ui.nextFrameBtn) {
    ui.nextFrameBtn.disabled =
      !hasFrames || shownIndex < 0 || shownIndex >= currentFrames.length - 1;
  }
}

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
    currentRetry: null,
    currentTau: null,
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
  updateFrameStepButtons();

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

function seekToStep(stepIndex, options = { fitView: true }) {
  if (!currentFrames.length || !loadedStartPoint) {
    return;
  }

  stopAutoPlayback();
  const index = clampStepIndex(stepIndex);
  if (index < 0) {
    return;
  }

  renderStep(index, { fitView: options.fitView !== false });
  currentIndex = index + 1;
}

function stepByFrame(delta, options = { fitView: true }) {
  if (!currentFrames.length || !Number.isFinite(delta)) {
    return;
  }

  const originIndex =
    lastRenderedIndex >= 0
      ? lastRenderedIndex
      : Math.max(0, Math.min(currentIndex, currentFrames.length - 1));
  const targetIndex = clampStepIndex(originIndex + delta);
  if (targetIndex < 0 || targetIndex === originIndex) {
    updateFrameStepButtons();
    return;
  }

  seekToStep(targetIndex, { fitView: options.fitView !== false });
}

function stopAutoPlayback() {
  playbackToken += 1;
  isPlaying = false;
  isPaused = false;
  updatePlayButton();
}

function stopPlayback({ clearFrames = false, clearVisuals = true } = {}) {
  stopAutoPlayback();
  applyLoopCandidateContextStyles(false, false);

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

function parseRetryIndex(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return null;
  return Math.max(0, Math.floor(n));
}

function resolveRetryIndex(frame, state = null) {
  const directRetry = parseRetryIndex(frame?.retry);
  if (Number.isFinite(directRetry)) {
    return directRetry;
  }

  const stateRetry = parseRetryIndex(state?.currentRetry);
  return Number.isFinite(stateRetry) ? stateRetry : null;
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

function clearFrameContextFlags(frames) {
  const source = Array.isArray(frames) ? frames : [];
  source.forEach((frame) => {
    if (frame && typeof frame === "object" && FRAME_CONTEXT_KEY in frame) {
      delete frame[FRAME_CONTEXT_KEY];
    }
  });
}

function markFrameAsFailedContext(frame) {
  if (!frame || typeof frame !== "object") return;
  frame[FRAME_CONTEXT_KEY] = FRAME_CONTEXT_FAILED_ATTEMPT;
}

function isFailedContextFrame(frame) {
  return frame?.[FRAME_CONTEXT_KEY] === FRAME_CONTEXT_FAILED_ATTEMPT;
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

function findFirstFrameIndex(frames, eventName, predicate = () => true) {
  for (let i = 0; i < frames.length; i += 1) {
    const frame = frames[i];
    if (!frame || frame.event !== eventName) continue;
    if (predicate(frame)) return i;
  }

  return -1;
}

function framesShareAttemptIdentity(a, b) {
  if (!a || !b) return false;

  const retryA = parseRetryIndex(a.retry);
  const retryB = parseRetryIndex(b.retry);
  if (Number.isFinite(retryA) && Number.isFinite(retryB) && retryA !== retryB) {
    return false;
  }

  const bearingA = normaliseBearing(a.bearing);
  const bearingB = normaliseBearing(b.bearing);
  if (
    Number.isFinite(bearingA) &&
    Number.isFinite(bearingB) &&
    bearingDelta(bearingA, bearingB) > BEARING_TOLERANCE_DEG
  ) {
    return false;
  }

  const shapeA = parseShapeSides(a.shape_sides ?? a.num_vertices);
  const shapeB = parseShapeSides(b.shape_sides ?? b.num_vertices);
  if (Number.isFinite(shapeA) && Number.isFinite(shapeB) && shapeA !== shapeB) {
    return false;
  }

  return true;
}

function findRetryWindowStartIndex(frames, tauAdjustedIndex) {
  const tauFrame = frames[tauAdjustedIndex];
  if (!tauFrame) return -1;

  for (let i = tauAdjustedIndex; i >= 0; i -= 1) {
    const frame = frames[i];
    if (!frame) continue;

    if (
      frame.event === "retry_started" &&
      framesShareAttemptIdentity(frame, tauFrame)
    ) {
      return i;
    }

    if (
      frame.event === "shape_attempt_started" &&
      framesShareAttemptIdentity(frame, tauFrame)
    ) {
      return i;
    }
  }

  return -1;
}

function getFrameComparableFocus(frame) {
  const bearing = normaliseBearing(frame?.bearing);
  const shapeSides = parseShapeSides(frame?.shape_sides ?? frame?.num_vertices);
  return {
    bearing: Number.isFinite(bearing) ? bearing : null,
    shapeSides: Number.isFinite(shapeSides) ? shapeSides : null,
  };
}

function windowMatchesFocus(windowFrames, focus) {
  if (!focus) {
    return true;
  }

  const focusBearing = normaliseBearing(focus.bearing);
  const focusShapeSides = parseShapeSides(focus.shapeSides);
  const hasFocusBearing = Number.isFinite(focusBearing);
  const hasFocusShape = Number.isFinite(focusShapeSides);
  if (!hasFocusBearing && !hasFocusShape) {
    return true;
  }

  let hasComparableFocus = false;

  for (const frame of windowFrames) {
    const comparable = getFrameComparableFocus(frame);

    if (hasFocusBearing && Number.isFinite(comparable.bearing)) {
      hasComparableFocus = true;
      if (
        bearingDelta(comparable.bearing, focusBearing) > BEARING_TOLERANCE_DEG
      ) {
        return false;
      }
    }

    if (hasFocusShape && Number.isFinite(comparable.shapeSides)) {
      hasComparableFocus = true;
      if (comparable.shapeSides !== focusShapeSides) {
        return false;
      }
    }
  }

  return hasComparableFocus;
}

function collectRejectedRetryWindows(
  frames,
  endIndex,
  maxWindows,
  focus = null,
) {
  const cappedEnd = Math.max(0, Math.min(frames.length - 1, endIndex));
  const rejectedTauIndexes = [];

  for (let i = 0; i <= cappedEnd; i += 1) {
    const frame = frames[i];
    if (!frame || frame.event !== "tau_adjusted") continue;
    rejectedTauIndexes.push(i);
  }

  const recentTauIndexes = rejectedTauIndexes.slice(-Math.max(0, maxWindows));
  const windows = [];

  for (const tauIndex of recentTauIndexes) {
    const startIndex = findRetryWindowStartIndex(frames, tauIndex);
    if (startIndex < 0 || startIndex > tauIndex) continue;

    const windowFrames = [];
    for (let i = startIndex; i <= tauIndex; i += 1) {
      const frame = frames[i];
      if (!frame || !POLYGON_STORY_EVENTS.has(frame.event)) continue;
      windowFrames.push(frame);
    }

    if (!windowFrames.length) {
      continue;
    }

    if (!windowMatchesFocus(windowFrames, focus)) {
      continue;
    }

    windows.push(windowFrames);
  }

  return windows;
}

function collectPolygonStoryFrames(frames, focus) {
  const anchorIndex = findFirstFrameIndex(
    frames,
    "shape_attempt_started",
    (frame) => frameMatchesFocus(frame, focus),
  );

  if (anchorIndex < 0) {
    return [];
  }

  const selected = [];
  for (let i = anchorIndex; i < frames.length; i += 1) {
    const frame = frames[i];
    if (!frame || !frame.event) continue;

    if (i > anchorIndex && frame.event === "shape_attempt_started") {
      break;
    }

    if (!POLYGON_STORY_EVENTS.has(frame.event)) {
      continue;
    }

    selected.push(frame);

    if (
      frame.event === "candidate_accepted" ||
      frame.event === "shape_attempt_failed"
    ) {
      break;
    }
  }

  return selected;
}

function collectFallbackStoryFrames(frames, focus) {
  let anchorIndex = findFirstFrameIndex(frames, "fallback_started", (frame) =>
    frameMatchesFocus(frame, focus),
  );

  if (anchorIndex < 0) {
    anchorIndex = findFirstFrameIndex(
      frames,
      "fallback_out_and_back_started",
      (frame) => frameMatchesFocus(frame, focus),
    );
  }

  if (anchorIndex < 0) {
    return [];
  }

  const selected = [];
  for (let i = anchorIndex; i < frames.length; i += 1) {
    const frame = frames[i];
    if (!frame || !frame.event) continue;

    if (i > anchorIndex && frame.event === "fallback_started") {
      break;
    }

    if (i > anchorIndex && frame.event === "shape_attempt_started") {
      break;
    }

    if (!FALLBACK_STORY_EVENTS.has(frame.event)) {
      continue;
    }

    if (!frameMatchesFocus(frame, focus)) {
      continue;
    }

    selected.push(frame);

    if (
      frame.event === "fallback_accepted" ||
      frame.event === "fallback_rejected" ||
      frame.event === "fallback_out_and_back_failed"
    ) {
      break;
    }
  }

  return selected;
}

function buildNarrativeFrames(frames, focus) {
  const source = Array.isArray(frames) ? frames : [];
  const selected = [];
  const seen = new Set();

  clearFrameContextFlags(source);

  includeUniqueFrame(selected, findFirstFrame(source, "solver_started"), seen);
  includeUniqueFrame(
    selected,
    findFirstFrame(source, "bearings_selected"),
    seen,
  );

  const isFallbackFocus = focus?.type === "out-and-back";
  const focusedStory = isFallbackFocus
    ? collectFallbackStoryFrames(source, focus)
    : collectPolygonStoryFrames(source, focus);

  const focusedStorySet = new Set(focusedStory);

  const failedRetryWindows = collectRejectedRetryWindows(
    source,
    source.length - 1,
    MAX_CONTEXT_FAILED_RETRY_WINDOWS,
    focus,
  );
  failedRetryWindows.forEach((windowFrames) => {
    windowFrames.forEach((frame) => {
      if (focusedStorySet.has(frame)) {
        return;
      }
      markFrameAsFailedContext(frame);
      includeUniqueFrame(selected, frame, seen);
    });
  });

  focusedStory.forEach((frame) => {
    includeUniqueFrame(selected, frame, seen);
  });

  if (
    !selected.some(
      (frame) =>
        frame.event === "candidate_accepted" ||
        frame.event === "fallback_accepted",
    )
  ) {
    includeUniqueFrame(
      selected,
      findFirstFrame(source, "candidate_accepted", (frame) =>
        frameMatchesFocus(frame, focus),
      ),
      seen,
    );

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
    "shape_attempt_started",
    "retry_started",
    "polygon_attempt_started",
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

  const retryIndex = parseRetryIndex(frame.retry);
  if (Number.isFinite(retryIndex)) {
    state.currentRetry = retryIndex;
  }

  const tauValue = Number(frame.tau);
  if (Number.isFinite(tauValue)) {
    state.currentTau = tauValue;
  }

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

  if (frame.event === "tau_adjusted") {
    const tauAfter = Number(frame.tau_after);
    if (Number.isFinite(tauAfter)) {
      state.currentTau = tauAfter;
    }
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
    opacity: 0.14,
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

function drawRejectedDistanceComparison(frame, state, startPoint, layerGroup) {
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
      opacity: 0.55,
      dashArray: "7 7",
      fillOpacity: 0,
    }).addTo(layerGroup);
  }

  if (actualDistance) {
    L.circle(startPoint, {
      radius: actualDistance,
      color: "#dc2626",
      weight: 3,
      opacity: 0.95,
      dashArray: "8 5",
      fillOpacity: 0,
    }).addTo(layerGroup);

    L.circleMarker(startPoint, {
      radius: 8,
      color: "#7f1d1d",
      weight: 2,
      fillColor: "#ef4444",
      fillOpacity: 0.9,
    })
      .bindTooltip("Rejected attempt", {
        direction: "top",
        opacity: 0.95,
      })
      .addTo(layerGroup);
  }
}

function drawRetryStartedMarker(frame, state, startPoint, layerGroup) {
  const retryLabel = formatRetryLabel(frame, state) || "Retry";
  L.circleMarker(startPoint, {
    radius: 9,
    color: "#78350f",
    weight: 3,
    fillColor: "#f59e0b",
    fillOpacity: 0.92,
  })
    .bindTooltip(`${retryLabel} started`, {
      direction: "top",
      opacity: 0.95,
    })
    .addTo(layerGroup);
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

function formatRetryLabel(frame, state) {
  const retryIndex = resolveRetryIndex(frame, state);
  if (!Number.isFinite(retryIndex)) return null;
  return `Retry ${retryIndex + 1}`;
}

function collectLegFramesForRetry(stepIndex, legEventName, targetRetryIndex) {
  const limit = clampStepIndex(stepIndex);
  if (limit < 0) {
    return [];
  }

  const legs = [];
  let activeRetry = null;

  for (let i = 0; i <= limit; i += 1) {
    const frame = currentFrames[i];
    if (!frame) continue;

    if (frame.event === "retry_started") {
      const parsedRetry = parseRetryIndex(frame.retry);
      if (Number.isFinite(parsedRetry)) {
        activeRetry = parsedRetry;
      }
      continue;
    }

    if (frame.event !== legEventName) {
      continue;
    }

    const frameRetry = parseRetryIndex(frame.retry);
    const effectiveRetry = Number.isFinite(frameRetry)
      ? frameRetry
      : activeRetry;

    if (Number.isFinite(targetRetryIndex)) {
      if (
        !Number.isFinite(effectiveRetry) ||
        effectiveRetry !== targetRetryIndex
      ) {
        continue;
      }
    }

    legs.push(frame);
    if (legs.length >= MAX_STACKED_LEGS_PER_RETRY) {
      break;
    }
  }

  return legs;
}

function drawLegRoutedFrame(frame, state, startPoint, layerGroup, stepIndex) {
  const eventName =
    frame.event === "fallback_leg_routed"
      ? "fallback_leg_routed"
      : "leg_routed";
  const targetRetry = resolveRetryIndex(frame, state);
  const stackedLegFrames = collectLegFramesForRetry(
    stepIndex,
    eventName,
    targetRetry,
  );

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

  const legsToDraw = stackedLegFrames.length ? stackedLegFrames : [frame];
  const renderedPaths = [];

  for (const legFrame of legsToDraw) {
    const legPath = normalisePoints(legFrame.path);
    if (legPath.length < 2) continue;

    const isCurrentLeg = legFrame === frame;
    renderedPaths.push({ path: legPath, isCurrentLeg });

    L.polyline(legPath, {
      color: "#ffffff",
      weight: isCurrentLeg ? 8 : 6,
      opacity: isCurrentLeg ? 0.82 : 0.28,
      lineJoin: "round",
      lineCap: "round",
    }).addTo(layerGroup);

    L.polyline(legPath, {
      color: isCurrentLeg ? WSM_CURRENT_LEG_COLOR : WSM_PREVIOUS_LEG_COLOR,
      weight: isCurrentLeg ? 5 : 3.5,
      opacity: isCurrentLeg ? 0.98 : 0.62,
      lineJoin: "round",
      lineCap: "round",
    }).addTo(layerGroup);
  }

  if (!renderedPaths.length) {
    return;
  }

  const activePath =
    path.length >= 2 ? path : renderedPaths[renderedPaths.length - 1].path;

  L.polyline([activePath[0], activePath[activePath.length - 1]], {
    color: WSM_REFERENCE_COLOR,
    weight: 2,
    opacity: 0.72,
    dashArray: "6 6",
  }).addTo(layerGroup);

  [activePath[0], activePath[activePath.length - 1]].forEach((point) => {
    L.circleMarker(point, {
      radius: 6,
      color: WSM_ENDPOINT_STROKE,
      weight: 2,
      fillColor: WSM_ENDPOINT_FILL,
      fillOpacity: 0.95,
    }).addTo(layerGroup);
  });

  const mid = activePath[Math.floor(activePath.length / 2)];
  const legIndex = Number(frame.leg_index);
  const totalLegs = Number(frame.total_legs);
  const retryLabel = formatRetryLabel(frame, state);
  const legLabel =
    Number.isFinite(legIndex) && Number.isFinite(totalLegs)
      ? `${retryLabel ? `${retryLabel} - ` : ""}WSM A* leg ${legIndex}/${totalLegs}`
      : "WSM A* routed leg";

  L.circleMarker(mid, {
    radius: 4,
    color: WSM_ENDPOINT_STROKE,
    weight: 1,
    fillColor: WSM_MARKER_FILL,
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

function applyLoopCandidateContextStyles(
  contextFailedAttempt,
  playbackActive = true,
) {
  const loopLayers = mapController?.loopLayers;
  if (!loopLayers || typeof loopLayers !== "object") {
    return;
  }

  const selectedLoopId =
    mapController?.selectedLoop !== undefined &&
    mapController?.selectedLoop !== null
      ? String(mapController.selectedLoop)
      : null;

  for (const [id, layer] of Object.entries(loopLayers)) {
    if (!layer?.setStyle) continue;

    const isSelected = selectedLoopId !== null && String(id) === selectedLoopId;
    if (!playbackActive) {
      layer.setStyle({
        weight: isSelected ? 6 : 4,
        opacity: isSelected ? 1.0 : 0.5,
      });
      continue;
    }

    if (contextFailedAttempt) {
      layer.setStyle({
        weight: isSelected ? 4.5 : 3,
        opacity: isSelected
          ? CONTEXT_SELECTED_LOOP_OPACITY
          : CONTEXT_OTHER_LOOP_OPACITY,
      });
      continue;
    }

    layer.setStyle({
      weight: isSelected ? 6 : 4,
      opacity: isSelected ? 1.0 : DEMO_NON_SELECTED_LOOP_OPACITY,
    });
  }
}

function renderBaseScene(baseLayer, options = {}) {
  if (!baseLayer) return;

  const showSelectedLoopReference = options.showSelectedLoopReference !== false;

  baseLayer.clearLayers();
  if (loadedStartPoint) {
    drawStartPoint(loadedStartPoint, baseLayer);
  }

  if (showSelectedLoopReference && playbackState.selectedLoop) {
    drawMutedSelectedLoop(playbackState.selectedLoop, baseLayer);
  }
}

function isRejectedDistanceStep(stepIndex) {
  const index = clampStepIndex(stepIndex);
  if (index < 0) return false;

  const frame = currentFrames[index];
  const nextFrame = currentFrames[index + 1];

  if (!frame || frame.event !== "distance_evaluated") return false;
  if (!nextFrame || nextFrame.event !== "tau_adjusted") return false;

  return framesShareAttemptIdentity(frame, nextFrame);
}

function renderFrame(frame, state, startPoint, stageLayer, stepIndex = -1) {
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

  if (frame.event === "retry_started") {
    drawBearingFrame(frame, state, startPoint, stageLayer);
    drawTargetDistanceGuide(state, startPoint, stageLayer);
    drawRetryStartedMarker(frame, state, startPoint, stageLayer);
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
    if (isRejectedDistanceStep(stepIndex)) {
      drawRejectedDistanceComparison(frame, state, startPoint, stageLayer);
    } else {
      drawDistanceComparison(frame, state, startPoint, stageLayer);
    }
    return;
  }

  if (frame.event === "leg_routed" || frame.event === "fallback_leg_routed") {
    drawLegRoutedFrame(frame, state, startPoint, stageLayer, stepIndex);
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

function classifyDeviationDirection(deviationPercent) {
  const deviation = Number(deviationPercent);
  if (!Number.isFinite(deviation)) return null;
  if (Math.abs(deviation) < 0.1) return "on target";
  return deviation > 0 ? "overshoot" : "undershoot";
}

function describeFrame(frame, state, stepIndex, totalSteps, options = {}) {
  const contextFailed = Boolean(options.contextFailedAttempt);
  const rejectedDistance = Boolean(options.rejectedDistance);
  const bearingText = formatBearing(frame.bearing ?? state.currentBearing);
  const retryLabel = formatRetryLabel(frame, state);
  const retryPrefix = retryLabel ? `${retryLabel}: ` : "";

  let message = "";

  switch (frame.event) {
    case "solver_started": {
      const target = formatDistanceMeters(frame.target_distance_m);
      message = target
        ? `Start point fixed. Target loop length set to ${target}.`
        : "Start point fixed. Solver begins.";
      break;
    }
    case "bearings_selected": {
      message = bearingText
        ? `Choose candidate bearings; focus direction is ${bearingText}.`
        : "Choose candidate bearings.";
      break;
    }
    case "shape_attempt_started": {
      const sides = parseShapeSides(frame.shape_sides ?? frame.num_vertices);
      const shapeText = Number.isFinite(sides) ? `${sides}-point` : "polygon";
      message = bearingText
        ? `${retryPrefix}Prepare ${shapeText} skeleton attempt toward ${bearingText}.`
        : `${retryPrefix}Prepare ${shapeText} skeleton attempt.`;
      break;
    }
    case "retry_started": {
      const tau = Number(frame.tau);
      if (Number.isFinite(tau)) {
        message = `${retryLabel || "Retry"} begins with tau ${tau.toFixed(3)}.`;
      } else {
        message = `${retryLabel || "Retry"} begins with updated geometry.`;
      }
      break;
    }
    case "polygon_attempt_started": {
      message = `${retryPrefix}Prepare theoretical waypoint projection.`;
      break;
    }
    case "skeleton_projected": {
      message = `${retryPrefix}Projected theoretical skeleton (orange) shown.`;
      break;
    }
    case "skeleton_snapped": {
      message = `${retryPrefix}Skeleton snapped onto graph edges (green points + halos).`;
      break;
    }
    case "leg_routed": {
      const legIndex = Number(frame.leg_index);
      const totalLegs = Number(frame.total_legs);
      const legDistance = formatDistanceMeters(frame.leg_distance_m);
      if (Number.isFinite(legIndex) && Number.isFinite(totalLegs)) {
        message = legDistance
          ? `${retryPrefix}WSM A* routed leg ${legIndex}/${totalLegs} on graph edges (${legDistance}).`
          : `${retryPrefix}WSM A* routed leg ${legIndex}/${totalLegs} on graph edges.`;
      } else {
        message = `${retryPrefix}WSM A* routed a leg on graph edges.`;
      }
      break;
    }
    case "fallback_leg_routed": {
      const legIndex = Number(frame.leg_index);
      const totalLegs = Number(frame.total_legs);
      const direction = String(frame.direction || "").trim();
      const legLabel =
        Number.isFinite(legIndex) && Number.isFinite(totalLegs)
          ? `${retryPrefix}Fallback WSM A* leg ${legIndex}/${totalLegs}`
          : "Fallback WSM A* leg";
      message = direction ? `${legLabel} (${direction}).` : `${legLabel}.`;
      break;
    }
    case "distance_evaluated": {
      const actual = formatDistanceMeters(frame.actual_distance_m);
      const deviation = Number(frame.deviation_percent);
      const deviationDirection = classifyDeviationDirection(deviation);
      if (actual && Number.isFinite(deviation)) {
        if (rejectedDistance) {
          message = deviationDirection
            ? `${retryPrefix}Rejected distance check ${actual} (${deviation.toFixed(1)}% ${deviationDirection}); retry will rescale.`
            : `${retryPrefix}Rejected distance check ${actual}; retry will rescale.`;
        } else {
          message = deviationDirection
            ? `${retryPrefix}Distance check ${actual} (${deviation.toFixed(1)}% ${deviationDirection}).`
            : `${retryPrefix}Distance check ${actual} (${deviation.toFixed(1)}% from target).`;
        }
      } else {
        message = rejectedDistance
          ? `${retryPrefix}Rejected distance check; retry will rescale.`
          : `${retryPrefix}Evaluate actual distance against target radius.`;
      }
      break;
    }
    case "tau_adjusted": {
      const before = Number(frame.tau_before);
      const after = Number(frame.tau_after);
      const direction =
        Number.isFinite(before) && Number.isFinite(after)
          ? after > before
            ? "increase"
            : after < before
              ? "decrease"
              : "keep"
          : null;
      if (Number.isFinite(before) && Number.isFinite(after)) {
        message = direction
          ? `${retryPrefix}Adjust shape scale (tau ${before.toFixed(3)} -> ${after.toFixed(3)}) to ${direction} route length on next retry.`
          : `${retryPrefix}Adjust shape scale (tau ${before.toFixed(3)} -> ${after.toFixed(3)}).`;
      } else {
        message = `${retryPrefix}Adjust shape scale and retry.`;
      }
      break;
    }
    case "fallback_started": {
      message = "Polygon attempts failed; switch to out-and-back fallback.";
      break;
    }
    case "fallback_out_and_back_started": {
      message = "Project turnaround waypoint for out-and-back.";
      break;
    }
    case "fallback_waypoint_projected": {
      message = "Fallback waypoint projected and snapped.";
      break;
    }
    case "fallback_out_and_back_completed": {
      message = "Fallback out-and-back legs connected.";
      break;
    }
    case "candidate_accepted":
      message = retryLabel
        ? `${retryLabel}: candidate accepted and highlighted as the selected final loop.`
        : "Candidate accepted and highlighted as the selected final loop.";
      break;
    case "fallback_accepted": {
      message = "Fallback candidate accepted.";
      break;
    }
    case "solver_completed": {
      message = "Solver completed and ranked the returned loop options.";
      break;
    }
    default:
      message = String(frame.event || "step").replaceAll("_", " ");
  }

  const loopLabel = state.selectedLoop?.label
    ? `${state.selectedLoop.label}: `
    : "";

  if (contextFailed) {
    message = `Context rejected retry (same run): ${message}`;
  }

  return `${loopLabel}${message} (${stepIndex}/${totalSteps})`;
}

function describeFrameNote(frame, options = {}) {
  const contextFailed = Boolean(options.contextFailedAttempt);
  const rejectedDistance = Boolean(options.rejectedDistance);
  if (!frame || !frame.event) {
    return "";
  }

  const withContextSuffix = (note) => {
    if (!contextFailed) return note;
    return `${note} This step is from an earlier rejected retry in this loop run, shown for comparison.`;
  };

  switch (frame.event) {
    case "solver_started":
      return "Dashed blue radius marks the requested target loop distance from the start point.";
    case "bearings_selected":
      return "Dashed cyan rays are candidate bearings. The darkest blue ray is the selected bearing for this candidate.";
    case "retry_started":
      return "A new retry starts with the latest tau value. Subsequent skeleton and WSM legs belong to this retry cycle.";
    case "skeleton_projected":
      return withContextSuffix(
        "Orange dashed skeleton is theoretical geometry before graph snapping.",
      );
    case "skeleton_snapped":
      return withContextSuffix(
        "Green points (with halos) show snapped waypoints anchored to reachable graph nodes.",
      );
    case "leg_routed":
    case "fallback_leg_routed":
      return withContextSuffix(
        "Bright rose path is the current WSM leg; lighter rose paths are earlier legs from the same retry. Dashed slate segment is straight-line reference only.",
      );
    case "distance_evaluated":
      return withContextSuffix(
        rejectedDistance
          ? "Dashed blue circle is target distance; dashed red circle is the rejected retry distance. Tau is adjusted next and all legs are rerouted."
          : "Dashed blue circle is target distance; solid cyan circle is this retry's actual loop distance. Overshoot or undershoot triggers tau adjustment.",
      );
    case "tau_adjusted":
      return "Orange shape is previous scale; purple shape is the tau-adjusted geometry used for the next retry where all legs are re-routed.";
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
    frame?.event === "retry_started" ||
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

  const frame = currentFrames[index];
  const frameViewOptions = {
    contextFailedAttempt: isFailedContextFrame(frame),
    rejectedDistance: isRejectedDistanceStep(index),
  };

  applyLoopCandidateContextStyles(frameViewOptions.contextFailedAttempt);

  renderBaseScene(groups.base, {
    showSelectedLoopReference: !frameViewOptions.contextFailedAttempt,
  });
  clearStageLayer();
  renderFrame(frame, playbackState, loadedStartPoint, groups.stage, index);

  if (options.fitView) {
    fitStepView(frame, playbackState, loadedStartPoint);
  }

  lastRenderedIndex = index;
  syncScrubber(index);
  updateStepIndicator(index, currentFrames.length);
  updateStatus(
    describeFrame(
      frame,
      playbackState,
      index + 1,
      currentFrames.length,
      frameViewOptions,
    ),
  );
  updateNote(describeFrameNote(frame, frameViewOptions));
  updatePlayButton();
  updateFrameStepButtons();
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
  ui.prevFrameBtn = document.getElementById("loop-demo-prev-frame-btn");
  ui.nextFrameBtn = document.getElementById("loop-demo-next-frame-btn");
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

  ui.prevFrameBtn?.addEventListener("click", () => {
    stepByFrame(-1, { fitView: true });
  });

  ui.nextFrameBtn?.addEventListener("click", () => {
    stepByFrame(1, { fitView: true });
  });

  ui.scrubber?.addEventListener("input", () => {
    if (!currentFrames.length) return;

    const rawValue = Number(ui.scrubber.value);
    seekToStep(rawValue - 1, { fitView: true });
  });

  ui.stopBtn?.addEventListener("click", () => {
    stopAutoPlayback();
    applyLoopCandidateContextStyles(false, false);
    clearLayers();
    currentIndex = 0;
    lastRenderedIndex = -1;
    configureScrubber(currentFrames.length);
    updateStepIndicator(null, currentFrames.length);
    updateStatus("Demo stopped. Scrub timeline or press Play.");
    updateNote(
      "Use the timeline to inspect any step or press Play to continue.",
    );
    if (currentFrames.length) {
      updateControlsVisibility(true);
    }
    updatePlayButton();
    updateFrameStepButtons();
  });

  ui.isInitialised = true;
  updateControlsVisibility(false);
  configureScrubber(0);
  updateStepIndicator(null, 0);
  updateStatus("");
  updateNote("Select a loop demo to begin.");
  updatePlayButton();
  updateFrameStepButtons();
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
  updateNote(
    "Autoplay will advance each step. Drag the timeline to inspect any step.",
  );
  updatePlayButton();

  renderBaseScene(layerGroup.base);
  fitStepView(currentFrames[0], playbackState, loadedStartPoint);

  startPlayback();
}
