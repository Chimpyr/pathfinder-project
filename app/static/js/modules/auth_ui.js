/**
 * Auth UI Module
 * Handles login, registration, logout, and account movement preferences.
 */

import {
  getMovementPrefs,
  parsePaceToKmh,
  saveMovementPreferencesEverywhere,
  speedDisplayToKmh,
  speedKmhToDisplay,
  syncMovementPreferencesWithServer,
} from "./movement_prefs.js";

const SPEED_MAX_LIMITS = {
  walking_speed_kmh: 9.0,
  running_easy_speed_kmh: 20.0,
  running_race_speed_kmh: 30.0,
};

export function initAuthUI() {
  const loginForm = document.getElementById("auth-login");
  const registerForm = document.getElementById("auth-register");
  const profilePanel = document.getElementById("auth-profile");
  const authMessage = document.getElementById("auth-message");

  const movementForm = document.getElementById("movement-prefs-form");
  const movementMessage = document.getElementById("movement-prefs-message");
  const movementSaveBtn = document.getElementById("save-movement-prefs-btn");
  const movementSaveSpinner = document.getElementById(
    "save-movement-prefs-spinner",
  );

  const unitSelect = document.getElementById("preferred-distance-unit");
  const walkingSpeedInput = document.getElementById("walking-speed-input");

  const easyModeSelect = document.getElementById("running-easy-input-mode");
  const easySpeedRow = document.getElementById("running-easy-speed-row");
  const easyPaceRow = document.getElementById("running-easy-pace-row");
  const easySpeedInput = document.getElementById("running-easy-speed-input");
  const easyPaceInput = document.getElementById("running-easy-pace-input");
  const easyPaceSuffix = document.getElementById("running-easy-pace-suffix");

  const raceModeSelect = document.getElementById("running-race-input-mode");
  const raceSpeedRow = document.getElementById("running-race-speed-row");
  const racePaceRow = document.getElementById("running-race-pace-row");
  const raceSpeedInput = document.getElementById("running-race-speed-input");
  const racePaceInput = document.getElementById("running-race-pace-input");
  const racePaceSuffix = document.getElementById("running-race-pace-suffix");

  let displayedFormUnit = unitSelect?.value === "mi" ? "mi" : "km";

  if (!loginForm) return;

  // ── Sub-view Switching ───────────────────────────────────────────
  const showRegisterBtn = document.getElementById("show-register");
  const showLoginBtn = document.getElementById("show-login");

  showRegisterBtn?.addEventListener("click", () => {
    loginForm.classList.add("hidden");
    registerForm.classList.remove("hidden");
    hideAuthMessage();
  });

  showLoginBtn?.addEventListener("click", () => {
    registerForm.classList.add("hidden");
    loginForm.classList.remove("hidden");
    hideAuthMessage();
  });

  // ── Login ────────────────────────────────────────────────────────
  const loginBtn = document.getElementById("login-btn");
  const loginSpinner = document.getElementById("login-spinner");

  loginBtn?.addEventListener("click", async () => {
    const email = document.getElementById("login-email").value.trim();
    const password = document.getElementById("login-password").value;

    if (!email || !password) {
      showAuthMessage("Please enter your email and password.", "error");
      return;
    }

    setLoading(loginBtn, loginSpinner, true);
    hideAuthMessage();

    try {
      const res = await fetch("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const data = await res.json();

      if (res.ok) {
        showProfile(data.user);
        showAuthMessage("Signed in successfully!", "success");
      } else {
        showAuthMessage(data.error || "Login failed.", "error");
      }
    } catch (err) {
      showAuthMessage("Network error. Is the server running?", "error");
    } finally {
      setLoading(loginBtn, loginSpinner, false);
    }
  });

  // ── Register ─────────────────────────────────────────────────────
  const registerBtn = document.getElementById("register-btn");
  const registerSpinner = document.getElementById("register-spinner");

  registerBtn?.addEventListener("click", async () => {
    const email = document.getElementById("register-email").value.trim();
    const password = document.getElementById("register-password").value;
    const confirm = document.getElementById("register-confirm").value;

    if (!email || !password) {
      showAuthMessage("Please fill in all fields.", "error");
      return;
    }
    if (password !== confirm) {
      showAuthMessage("Passwords do not match.", "error");
      return;
    }
    if (password.length < 8) {
      showAuthMessage("Password must be at least 8 characters.", "error");
      return;
    }

    setLoading(registerBtn, registerSpinner, true);
    hideAuthMessage();

    try {
      const res = await fetch("/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const data = await res.json();

      if (res.ok) {
        showProfile(data.user);
        showAuthMessage("Account created! You're now signed in.", "success");
      } else {
        showAuthMessage(data.error || "Registration failed.", "error");
      }
    } catch (err) {
      showAuthMessage("Network error. Is the server running?", "error");
    } finally {
      setLoading(registerBtn, registerSpinner, false);
    }
  });

  // ── Logout ───────────────────────────────────────────────────────
  const logoutBtn = document.getElementById("logout-btn");

  logoutBtn?.addEventListener("click", async () => {
    try {
      await fetch("/auth/logout", { method: "POST" });
    } catch (_) {
      // Ignore network errors on logout.
    }

    showLoggedOut();
    showAuthMessage("You have been logged out.", "success");
  });

  // ── Enter key support ────────────────────────────────────────────
  document
    .getElementById("login-password")
    ?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") loginBtn?.click();
    });
  document
    .getElementById("register-confirm")
    ?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") registerBtn?.click();
    });

  // ── Movement preferences UI ──────────────────────────────────────
  function applyRunningModeVisibility() {
    const easyMode = easyModeSelect?.value || "speed";
    const raceMode = raceModeSelect?.value || "speed";

    easySpeedRow?.classList.toggle("hidden", easyMode !== "speed");
    easyPaceRow?.classList.toggle("hidden", easyMode !== "pace");
    raceSpeedRow?.classList.toggle("hidden", raceMode !== "speed");
    racePaceRow?.classList.toggle("hidden", raceMode !== "pace");
  }

  function paceInputValue(speedKmh, unit) {
    const speed = Number(speedKmh);
    if (!Number.isFinite(speed) || speed <= 0) return "";

    const factor = unit === "mi" ? 1.609344 : 1.0;
    const minutesPerUnit = (60 / speed) * factor;
    let whole = Math.floor(minutesPerUnit);
    let seconds = Math.round((minutesPerUnit - whole) * 60);

    if (seconds === 60) {
      whole += 1;
      seconds = 0;
    }

    return `${whole}:${String(seconds).padStart(2, "0")}`;
  }

  function applyUnitDisplayFormatting(unit) {
    if (easyPaceSuffix) easyPaceSuffix.textContent = `/ ${unit}`;
    if (racePaceSuffix) racePaceSuffix.textContent = `/ ${unit}`;

    document.querySelectorAll(".dyn-speed-suffix").forEach((el) => {
      el.textContent = unit === "km" ? "km/h" : "mph";
    });

    if (walkingSpeedInput)
      walkingSpeedInput.placeholder = unit === "km" ? "e.g. 5.0" : "e.g. 3.1";
    if (easySpeedInput)
      easySpeedInput.placeholder = unit === "km" ? "e.g. 9.5" : "e.g. 5.9";
    if (raceSpeedInput)
      raceSpeedInput.placeholder = unit === "km" ? "e.g. 12.5" : "e.g. 7.8";
  }

  function convertDisplayedValuesBetweenUnits(fromUnit, toUnit) {
    if (fromUnit === toUnit) return;

    const convertSpeedInput = (inputEl) => {
      const raw = Number(inputEl?.value);
      if (!Number.isFinite(raw) || raw <= 0) return;

      const kmh = speedDisplayToKmh(raw, fromUnit);
      if (!Number.isFinite(kmh) || kmh <= 0) return;

      inputEl.value = speedKmhToDisplay(kmh, toUnit).toFixed(1);
    };

    const convertPaceInput = (inputEl) => {
      const text = (inputEl?.value || "").trim();
      if (!text) return;

      const kmh = parsePaceToKmh(text, fromUnit);
      if (!Number.isFinite(kmh) || kmh <= 0) return;

      inputEl.value = paceInputValue(kmh, toUnit);
    };

    convertSpeedInput(walkingSpeedInput);
    convertSpeedInput(easySpeedInput);
    convertSpeedInput(raceSpeedInput);
    convertPaceInput(easyPaceInput);
    convertPaceInput(racePaceInput);
  }

  function populateMovementForm(prefs, displayUnitOverride = null) {
    if (!movementForm) return;

    const safePrefs = prefs || getMovementPrefs();
    const prefsUnit = safePrefs.preferred_distance_unit || "km";
    const unit = displayUnitOverride || prefsUnit;
    displayedFormUnit = unit;

    if (unitSelect) unitSelect.value = unit;

    applyUnitDisplayFormatting(unit);

    if (walkingSpeedInput) {
      walkingSpeedInput.value = speedKmhToDisplay(
        safePrefs.walking_speed_kmh,
        unit,
      ).toFixed(1);
    }

    if (easySpeedInput) {
      easySpeedInput.value = speedKmhToDisplay(
        safePrefs.running_easy_speed_kmh,
        unit,
      ).toFixed(1);
    }
    if (raceSpeedInput) {
      raceSpeedInput.value = speedKmhToDisplay(
        safePrefs.running_race_speed_kmh,
        unit,
      ).toFixed(1);
    }

    if (easyPaceInput) {
      easyPaceInput.value = paceInputValue(
        safePrefs.running_easy_speed_kmh,
        unit,
      );
    }
    if (racePaceInput) {
      racePaceInput.value = paceInputValue(
        safePrefs.running_race_speed_kmh,
        unit,
      );
    }

    applyRunningModeVisibility();
  }

  function showMovementMessage(text, type) {
    if (!movementMessage) return;

    movementMessage.textContent = text;
    movementMessage.classList.remove(
      "hidden",
      "bg-red-50",
      "text-red-600",
      "border-red-200",
      "bg-green-50",
      "text-green-600",
      "border-green-200",
      "dark:bg-red-900/30",
      "dark:text-red-400",
      "dark:bg-green-900/30",
      "dark:text-green-400",
    );

    if (type === "error") {
      movementMessage.classList.add(
        "bg-red-50",
        "text-red-600",
        "border",
        "border-red-200",
        "dark:bg-red-900/30",
        "dark:text-red-400",
      );
      return;
    }

    movementMessage.classList.add(
      "bg-green-50",
      "text-green-600",
      "border",
      "border-green-200",
      "dark:bg-green-900/30",
      "dark:text-green-400",
    );
  }

  function hideMovementMessage() {
    movementMessage?.classList.add("hidden");
  }

  function validateSpeed(field, valueKmh) {
    if (!Number.isFinite(valueKmh)) {
      return `${field} is not a valid number.`;
    }

    if (valueKmh <= 0) {
      return `${field.replaceAll("_", " ")} must be greater than 0.`;
    }

    const max = SPEED_MAX_LIMITS[field];
    if (valueKmh > max) {
      return `${field.replaceAll("_", " ")} must not exceed ${max.toFixed(1)} km/h.`;
    }

    return null;
  }

  function readRunningSpeedKmh(
    modeSelect,
    speedInput,
    paceInput,
    fallbackUnit,
  ) {
    const mode = modeSelect?.value || "speed";

    if (mode === "pace") {
      const parsed = parsePaceToKmh(paceInput?.value || "", fallbackUnit);
      return parsed;
    }

    return speedDisplayToKmh(speedInput?.value, fallbackUnit);
  }

  async function handleMovementSave() {
    if (!movementForm) return;

    hideMovementMessage();
    const unit = unitSelect?.value || "km";

    const walkingSpeedKmh = speedDisplayToKmh(walkingSpeedInput?.value, unit);
    const runningEasySpeedKmh = readRunningSpeedKmh(
      easyModeSelect,
      easySpeedInput,
      easyPaceInput,
      unit,
    );
    const runningRaceSpeedKmh = readRunningSpeedKmh(
      raceModeSelect,
      raceSpeedInput,
      racePaceInput,
      unit,
    );

    const problems = [
      validateSpeed("walking_speed_kmh", walkingSpeedKmh),
      validateSpeed("running_easy_speed_kmh", runningEasySpeedKmh),
      validateSpeed("running_race_speed_kmh", runningRaceSpeedKmh),
    ].filter(Boolean);

    if (runningRaceSpeedKmh < runningEasySpeedKmh) {
      problems.push(
        "Race running speed must be greater than or equal to easy running speed.",
      );
    }

    if (problems.length > 0) {
      showMovementMessage(problems[0], "error");
      return;
    }

    setLoading(movementSaveBtn, movementSaveSpinner, true);

    try {
      const saved = await saveMovementPreferencesEverywhere({
        preferred_distance_unit: unit,
        walking_speed_kmh: walkingSpeedKmh,
        running_easy_speed_kmh: runningEasySpeedKmh,
        running_race_speed_kmh: runningRaceSpeedKmh,
      });

      populateMovementForm(saved);
      showMovementMessage("Movement preferences saved.", "success");
    } catch (err) {
      console.error("[AuthUI] Failed to save movement preferences", err);
      showMovementMessage("Could not save preferences right now.", "error");
    } finally {
      setLoading(movementSaveBtn, movementSaveSpinner, false);
    }
  }

  movementSaveBtn?.addEventListener("click", handleMovementSave);

  movementForm?.addEventListener("submit", (event) => {
    event.preventDefault();
    handleMovementSave();
  });

  function handleUnitPreviewChange() {
    const selectedUnit = unitSelect?.value === "mi" ? "mi" : "km";
    const sourceUnit = displayedFormUnit === "mi" ? "mi" : "km";

    convertDisplayedValuesBetweenUnits(sourceUnit, selectedUnit);
    applyUnitDisplayFormatting(selectedUnit);

    displayedFormUnit = selectedUnit;
    if (unitSelect) unitSelect.value = selectedUnit;
  }

  unitSelect?.addEventListener("change", handleUnitPreviewChange);
  unitSelect?.addEventListener("input", handleUnitPreviewChange);
  unitSelect?.addEventListener("blur", handleUnitPreviewChange);
  movementForm?.addEventListener("change", (event) => {
    if (event.target === unitSelect) {
      handleUnitPreviewChange();
    }
  });

  easyModeSelect?.addEventListener("change", applyRunningModeVisibility);
  raceModeSelect?.addEventListener("change", applyRunningModeVisibility);

  // ── Session Check (on page load) ─────────────────────────────────
  populateMovementForm(getMovementPrefs());
  checkSession();

  async function checkSession() {
    try {
      const res = await fetch("/auth/me");
      if (res.ok) {
        const data = await res.json();
        showProfile(data.user);
      }
      // If 401, stay on login form (default state).
    } catch (_) {
      // Network error: keep default login form and local preferences.
    }
  }

  function showProfile(user) {
    loginForm.classList.add("hidden");
    registerForm.classList.add("hidden");
    profilePanel.classList.remove("hidden");

    document.getElementById("profile-email").textContent = user.email;
    const since = new Date(user.created_at);
    document.getElementById("profile-since").textContent =
      `Member since ${since.toLocaleDateString("en-GB", { month: "long", year: "numeric" })}`;

    document.getElementById("account-subtitle").textContent = user.email;

    // Update nav icon to indicate logged-in.
    const navIcon = document.getElementById("account-nav-icon");
    if (navIcon) {
      navIcon.classList.remove("fa-user-circle");
      navIcon.classList.add("fa-user-check");
      navIcon.style.color = "var(--primary-color)";
    }

    // Fetch saved data counts.
    fetchCounts();

    // Sync movement preferences (timestamp merge local/server).
    syncMovementPreferencesWithServer()
      .then((prefs) => populateMovementForm(prefs))
      .catch(() => populateMovementForm(getMovementPrefs()));
  }

  function showLoggedOut() {
    profilePanel.classList.add("hidden");
    registerForm.classList.add("hidden");
    loginForm.classList.remove("hidden");

    document.getElementById("account-subtitle").textContent =
      "Sign in to save routes and pins";

    // Reset nav icon.
    const navIcon = document.getElementById("account-nav-icon");
    if (navIcon) {
      navIcon.classList.remove("fa-user-check");
      navIcon.classList.add("fa-user-circle");
      navIcon.style.color = "";
    }

    // Clear form fields.
    document.getElementById("login-email").value = "";
    document.getElementById("login-password").value = "";
    document.getElementById("register-email").value = "";
    document.getElementById("register-password").value = "";
    document.getElementById("register-confirm").value = "";

    // Keep local movement preferences visible/editable when signed out.
    populateMovementForm(getMovementPrefs());
  }

  async function fetchCounts() {
    try {
      const [pinsRes, queriesRes] = await Promise.all([
        fetch("/api/pins"),
        fetch("/api/queries"),
      ]);
      if (pinsRes.ok) {
        const pinsData = await pinsRes.json();
        document.getElementById("profile-pin-count").textContent =
          pinsData.pins.length;
      }
      if (queriesRes.ok) {
        const queriesData = await queriesRes.json();
        document.getElementById("profile-route-count").textContent =
          queriesData.queries.length;
      }
    } catch (_) {
      // Silently fail — counts remain placeholders.
    }
  }

  function showAuthMessage(text, type) {
    if (!authMessage) return;
    authMessage.textContent = text;
    authMessage.classList.remove(
      "hidden",
      "bg-red-50",
      "text-red-600",
      "border-red-200",
      "bg-green-50",
      "text-green-600",
      "border-green-200",
      "dark:bg-red-900/30",
      "dark:text-red-400",
      "dark:bg-green-900/30",
      "dark:text-green-400",
    );

    if (type === "error") {
      authMessage.classList.add(
        "bg-red-50",
        "text-red-600",
        "border",
        "border-red-200",
        "dark:bg-red-900/30",
        "dark:text-red-400",
      );
    } else {
      authMessage.classList.add(
        "bg-green-50",
        "text-green-600",
        "border",
        "border-green-200",
        "dark:bg-green-900/30",
        "dark:text-green-400",
      );
    }
  }

  function hideAuthMessage() {
    authMessage?.classList.add("hidden");
  }

  function setLoading(btn, spinner, loading) {
    if (btn) btn.disabled = loading;
    if (spinner) spinner.classList.toggle("hidden", !loading);
  }
}
