/**
 * Movement Preferences Module
 *
 * Handles local persistence, profile selection, conversion utilities,
 * and server sync for movement speed preferences.
 */

const PREFS_STORAGE_KEY = "movementPrefs:v1";
const PROFILE_STORAGE_KEY = "travelProfile:selected";
const DISTANCE_UNITS = new Set(["km", "mi"]);
const TRAVEL_PROFILES = new Set(["walking", "running_easy", "running_race"]);
const KM_PER_MILE = 1.609344;
const MIN_POSITIVE_SPEED_KMH = 0.01;

const DEFAULT_PREFS = {
  preferred_distance_unit: "km",
  walking_speed_kmh: 5.0,
  running_easy_speed_kmh: 9.5,
  running_race_speed_kmh: 12.5,
  movement_prefs_updated_at: null,
};

let currentPrefs = { ...DEFAULT_PREFS };

function nowIso() {
  return new Date().toISOString();
}

function parseIso(ts) {
  if (!ts || typeof ts !== "string") return null;
  const parsed = new Date(ts);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function normaliseUnit(unit, fallback = "km") {
  if (typeof unit !== "string") return fallback;
  const candidate = unit.trim().toLowerCase();
  return DISTANCE_UNITS.has(candidate) ? candidate : fallback;
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function safeNumber(value, fallback) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function normalisePrefs(raw = {}) {
  const merged = {
    ...DEFAULT_PREFS,
    ...raw,
  };

  merged.preferred_distance_unit = normaliseUnit(
    merged.preferred_distance_unit,
    DEFAULT_PREFS.preferred_distance_unit,
  );
  merged.walking_speed_kmh = clamp(
    safeNumber(merged.walking_speed_kmh, DEFAULT_PREFS.walking_speed_kmh),
    MIN_POSITIVE_SPEED_KMH,
    9.0,
  );
  merged.running_easy_speed_kmh = clamp(
    safeNumber(
      merged.running_easy_speed_kmh,
      DEFAULT_PREFS.running_easy_speed_kmh,
    ),
    MIN_POSITIVE_SPEED_KMH,
    20.0,
  );
  merged.running_race_speed_kmh = clamp(
    safeNumber(
      merged.running_race_speed_kmh,
      DEFAULT_PREFS.running_race_speed_kmh,
    ),
    MIN_POSITIVE_SPEED_KMH,
    30.0,
  );

  if (merged.running_race_speed_kmh < merged.running_easy_speed_kmh) {
    merged.running_race_speed_kmh = merged.running_easy_speed_kmh;
  }

  if (typeof merged.movement_prefs_updated_at !== "string") {
    merged.movement_prefs_updated_at = null;
  }

  return merged;
}

function writeLocalPrefs(prefs) {
  try {
    localStorage.setItem(PREFS_STORAGE_KEY, JSON.stringify(prefs));
  } catch (err) {
    console.warn("[MovementPrefs] Could not persist preferences", err);
  }
}

function readLocalPrefs() {
  try {
    const raw = localStorage.getItem(PREFS_STORAGE_KEY);
    if (!raw) return null;
    return normalisePrefs(JSON.parse(raw));
  } catch (err) {
    console.warn("[MovementPrefs] Ignoring malformed local preferences", err);
    return null;
  }
}

function emitPrefsChanged() {
  document.dispatchEvent(
    new CustomEvent("movement-prefs-changed", {
      detail: { preferences: getMovementPrefs() },
    }),
  );
}

function emitTravelProfileChanged(profile) {
  document.dispatchEvent(
    new CustomEvent("travel-profile-changed", {
      detail: { travelProfile: profile },
    }),
  );
}

function getProfileSpeedField(profile) {
  switch (profile) {
    case "running_easy":
      return "running_easy_speed_kmh";
    case "running_race":
      return "running_race_speed_kmh";
    default:
      return "walking_speed_kmh";
  }
}

function profileIsValid(profile) {
  return TRAVEL_PROFILES.has(profile);
}

function mergePrefs(localPrefs, serverPrefs) {
  const local = localPrefs ? normalisePrefs(localPrefs) : null;
  const server = serverPrefs ? normalisePrefs(serverPrefs) : null;

  if (!local && !server) {
    return { prefs: normalisePrefs(DEFAULT_PREFS), source: "default" };
  }
  if (!server) {
    return { prefs: local, source: "local" };
  }
  if (!local) {
    return { prefs: server, source: "server" };
  }

  const localTs = parseIso(local.movement_prefs_updated_at);
  const serverTs = parseIso(server.movement_prefs_updated_at);

  if (localTs && serverTs) {
    if (localTs > serverTs) return { prefs: local, source: "local" };
    if (serverTs > localTs) return { prefs: server, source: "server" };
    return { prefs: server, source: "server" }; // deterministic tie-break.
  }

  if (localTs && !serverTs) return { prefs: local, source: "local" };
  return { prefs: server, source: "server" };
}

export function initMovementPreferences() {
  currentPrefs = readLocalPrefs() || normalisePrefs(DEFAULT_PREFS);
  writeLocalPrefs(currentPrefs);
}

export function getMovementPrefs() {
  return { ...currentPrefs };
}

export function setMovementPrefs(partial, { touchTimestamp = true } = {}) {
  const merged = normalisePrefs({ ...currentPrefs, ...(partial || {}) });
  if (touchTimestamp) {
    merged.movement_prefs_updated_at = nowIso();
  }

  currentPrefs = merged;
  writeLocalPrefs(currentPrefs);
  emitPrefsChanged();
  return getMovementPrefs();
}

export function getDistanceUnit() {
  return currentPrefs.preferred_distance_unit || "km";
}

export function getSelectedTravelProfile() {
  const stored = localStorage.getItem(PROFILE_STORAGE_KEY);
  if (profileIsValid(stored)) return stored;
  return "walking";
}

export function setSelectedTravelProfile(profile) {
  if (!profileIsValid(profile)) return getSelectedTravelProfile();
  localStorage.setItem(PROFILE_STORAGE_KEY, profile);
  emitTravelProfileChanged(profile);
  return profile;
}

export function getEffectiveSpeedKmh(
  profile = getSelectedTravelProfile(),
  prefs = currentPrefs,
) {
  const field = getProfileSpeedField(profile);
  const speed = safeNumber(prefs[field], DEFAULT_PREFS[field]);
  return speed > 0 ? speed : DEFAULT_PREFS[field];
}

export function kmToDisplay(distanceKm, unit = getDistanceUnit()) {
  const unitNorm = normaliseUnit(unit, getDistanceUnit());
  return unitNorm === "mi"
    ? Number(distanceKm) / KM_PER_MILE
    : Number(distanceKm);
}

export function speedKmhToDisplay(speedKmh, unit = getDistanceUnit()) {
  const unitNorm = normaliseUnit(unit, getDistanceUnit());
  return unitNorm === "mi" ? Number(speedKmh) / KM_PER_MILE : Number(speedKmh);
}

export function speedDisplayToKmh(speedValue, unit = getDistanceUnit()) {
  const unitNorm = normaliseUnit(unit, getDistanceUnit());
  const value = safeNumber(speedValue, NaN);
  if (!Number.isFinite(value)) return NaN;
  return unitNorm === "mi" ? value * KM_PER_MILE : value;
}

export function parsePaceToKmh(text, paceUnit = getDistanceUnit()) {
  if (typeof text !== "string") return NaN;
  const trimmed = text.trim();
  const parts = trimmed.split(":");
  if (parts.length !== 2) return NaN;

  const minutes = Number(parts[0]);
  const seconds = Number(parts[1]);
  if (!Number.isFinite(minutes) || !Number.isFinite(seconds)) return NaN;
  if (minutes < 0 || seconds < 0 || seconds >= 60) return NaN;

  const totalMinutes = minutes + seconds / 60;
  if (totalMinutes <= 0) return NaN;

  if (normaliseUnit(paceUnit, "km") === "mi") {
    return (60 * KM_PER_MILE) / totalMinutes;
  }
  return 60 / totalMinutes;
}

export function formatPaceFromSpeed(speedKmh, unit = getDistanceUnit()) {
  const speed = safeNumber(speedKmh, NaN);
  if (!Number.isFinite(speed) || speed <= 0) {
    return `n/a min/${normaliseUnit(unit)}`;
  }

  const unitNorm = normaliseUnit(unit);
  const minutesPerUnit = (60 / speed) * (unitNorm === "mi" ? KM_PER_MILE : 1);
  let minutes = Math.floor(minutesPerUnit);
  let seconds = Math.round((minutesPerUnit - minutes) * 60);

  if (seconds === 60) {
    minutes += 1;
    seconds = 0;
  }

  return `${minutes}:${String(seconds).padStart(2, "0")} min/${unitNorm}`;
}

export function formatDistance(
  distanceKm,
  unit = getDistanceUnit(),
  decimals = 2,
) {
  const display = kmToDisplay(distanceKm, unit);
  return `${display.toFixed(decimals)} ${normaliseUnit(unit)}`;
}

export function formatSpeed(speedKmh, unit = getDistanceUnit(), decimals = 1) {
  const display = speedKmhToDisplay(speedKmh, unit);
  const label = normaliseUnit(unit) === "mi" ? "mph" : "km/h";
  return `${display.toFixed(decimals)} ${label}`;
}

export function buildMovementRequestPayload(
  profile = getSelectedTravelProfile(),
) {
  return {
    travel_profile: profileIsValid(profile) ? profile : "walking",
    distance_unit: getDistanceUnit(),
  };
}

async function fetchServerMovementPrefs() {
  const res = await fetch("/api/preferences/movement");
  if (res.status === 401) return null;
  if (!res.ok) throw new Error("Could not fetch movement preferences");

  const data = await res.json();
  return normalisePrefs(data.preferences || {});
}

async function pushServerMovementPrefs(prefs) {
  const payload = {
    preferred_distance_unit: prefs.preferred_distance_unit,
    walking_speed_kmh: prefs.walking_speed_kmh,
    running_easy_speed_kmh: prefs.running_easy_speed_kmh,
    running_race_speed_kmh: prefs.running_race_speed_kmh,
    client_updated_at: prefs.movement_prefs_updated_at,
  };

  const res = await fetch("/api/preferences/movement", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    if (res.status === 401) return null;
    throw new Error("Could not save movement preferences");
  }

  const data = await res.json();
  return normalisePrefs(data.preferences || prefs);
}

export async function syncMovementPreferencesWithServer() {
  const localPrefs = getMovementPrefs();

  let serverPrefs = null;
  try {
    serverPrefs = await fetchServerMovementPrefs();
  } catch (err) {
    console.warn(
      "[MovementPrefs] Server fetch failed, keeping local prefs",
      err,
    );
    return getMovementPrefs();
  }

  // Unauthenticated users only have local state.
  if (!serverPrefs) {
    return getMovementPrefs();
  }

  const merged = mergePrefs(localPrefs, serverPrefs);
  currentPrefs = normalisePrefs(merged.prefs);

  // If local copy is newer, write it up to the server.
  if (merged.source === "local") {
    try {
      const updatedServer = await pushServerMovementPrefs(currentPrefs);
      if (updatedServer) {
        currentPrefs = normalisePrefs(updatedServer);
      }
    } catch (err) {
      console.warn(
        "[MovementPrefs] Could not push merged prefs to server",
        err,
      );
    }
  }

  writeLocalPrefs(currentPrefs);
  emitPrefsChanged();
  return getMovementPrefs();
}

export async function saveMovementPreferencesEverywhere(partialPrefs) {
  const updatedLocal = setMovementPrefs(partialPrefs, { touchTimestamp: true });

  try {
    const updatedServer = await pushServerMovementPrefs(updatedLocal);
    if (updatedServer) {
      currentPrefs = normalisePrefs(updatedServer);
      writeLocalPrefs(currentPrefs);
      emitPrefsChanged();
    }
  } catch (err) {
    // Keep local preferences when server persistence is unavailable.
    console.warn("[MovementPrefs] Saved locally but server save failed", err);
  }

  return getMovementPrefs();
}
