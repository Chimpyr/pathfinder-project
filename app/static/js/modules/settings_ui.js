/**
 * Settings UI Module
 * Handles application settings interactions
 */
import { mapController } from "./map_manager.js";

export function initSettingsUI() {
  console.log("[SettingsUI] Initializing...");

  initMapAppearance();
  initMapOverlays();
}

const WEIGHT_LABELS = {
  1: "Thin",
  2: "Normal",
  3: "Thick",
  4: "Very Thick",
  5: "Max",
};

function initMapOverlays() {
  const toggle = document.getElementById("lighting-overlay-toggle");
  const advancedPanel = document.getElementById("lighting-advanced-options");
  const colorPicker = document.getElementById("lighting-lit-color");
  const weightSlider = document.getElementById("lighting-weight-slider");
  const weightLabel = document.getElementById("lighting-weight-value");

  if (!toggle) return;

  // --- Restore persisted state ---
  const savedOn = localStorage.getItem("lightingOverlay") === "true";
  const savedColor = localStorage.getItem("lightingColor") || "#FFD700";
  const savedWeight = parseInt(
    localStorage.getItem("lightingWeight") || "2",
    10,
  );

  toggle.checked = savedOn;
  colorPicker.value = savedColor;
  weightSlider.value = savedWeight;
  weightLabel.textContent = WEIGHT_LABELS[savedWeight] || "Normal";

  // Show/hide advanced panel to match initial state
  advancedPanel.classList.toggle("hidden", !savedOn);

  if (savedOn && mapController) {
    mapController.addLightingLayer({
      litColor: savedColor,
      litWeight: savedWeight,
    });
  }

  // Helper: read current options and re-render
  const applyStyle = () => {
    const opts = {
      litColor: colorPicker.value,
      litWeight: parseInt(weightSlider.value, 10),
    };
    mapController?.updateLightingStyle(opts);
  };

  // --- Toggle ---
  toggle.addEventListener("change", () => {
    const on = toggle.checked;
    advancedPanel.classList.toggle("hidden", !on);
    if (on) {
      mapController?.addLightingLayer({
        litColor: colorPicker.value,
        litWeight: parseInt(weightSlider.value, 10),
      });
      localStorage.setItem("lightingOverlay", "true");
    } else {
      mapController?.removeLightingLayer();
      localStorage.setItem("lightingOverlay", "false");
    }
    console.log(
      `[SettingsUI] Street lighting overlay ${on ? "enabled" : "disabled"}`,
    );
  });

  // --- Colour picker (live preview on input, persist on change) ---
  colorPicker.addEventListener("input", applyStyle);
  colorPicker.addEventListener("change", () => {
    localStorage.setItem("lightingColor", colorPicker.value);
  });

  // --- Weight slider ---
  weightSlider.addEventListener("input", () => {
    const v = parseInt(weightSlider.value, 10);
    weightLabel.textContent = WEIGHT_LABELS[v] || v;
    applyStyle();
  });
  weightSlider.addEventListener("change", () => {
    localStorage.setItem("lightingWeight", weightSlider.value);
  });
}

function initMapAppearance() {
  const styleInputs = document.querySelectorAll('input[name="map-style"]');

  if (!styleInputs.length) {
    console.warn("[SettingsUI] No map style inputs found");
    return;
  }

  // Load saved preference
  const savedStyle = localStorage.getItem("mapStyle") || "osm";

  // Set initial state on map
  // Note: mapController should be initialized by now if called from main.js after initMap
  if (mapController) {
    mapController.setTileLayer(savedStyle);
  } else {
    console.warn("[SettingsUI] mapController not ready yet");
  }

  // Update UI radio button
  const radio = document.querySelector(
    `input[name="map-style"][value="${savedStyle}"]`,
  );
  if (radio) {
    radio.checked = true;
  }

  // Add listeners
  styleInputs.forEach((input) => {
    input.addEventListener("change", (e) => {
      const styleId = e.target.value;

      console.log(`[SettingsUI] Map style changed to: ${styleId}`);

      if (mapController) {
        mapController.setTileLayer(styleId);
      }

      // Persist preference
      localStorage.setItem("mapStyle", styleId);
    });
  });
}
