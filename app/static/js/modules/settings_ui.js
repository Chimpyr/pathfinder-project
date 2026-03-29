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

const SOURCE_LABELS = {
  all: "All sources",
  council: "Council only",
  osm: "OSM only",
  bristol: "Bristol council only",
  south_glos: "South Glos council only",
};

const REGIME_LABELS = {
  all: "All regimes",
  all_night: "All night",
  part_night: "Part night",
  timed_window: "Timed window",
  solar: "Solar",
  unlit: "Unlit",
  unknown: "Unknown",
};

function initMapOverlays() {
  const toggle = document.getElementById("lighting-overlay-toggle");
  const advancedPanel = document.getElementById("lighting-advanced-options");
  const litColorPicker = document.getElementById("lighting-lit-color");
  const unlitColorPicker = document.getElementById("lighting-unlit-color");
  const unknownColorPicker = document.getElementById("lighting-unknown-color");
  const dimMapToggle = document.getElementById("lighting-dim-map-toggle");
  const hoverInfoToggle = document.getElementById("lighting-hover-info-toggle");
  const weightSlider = document.getElementById("lighting-weight-slider");
  const weightLabel = document.getElementById("lighting-weight-value");
  const sourceFilter = document.getElementById("lighting-source-filter");
  const regimeFilter = document.getElementById("lighting-regime-filter");
  const activeSourceLabel = document.getElementById("lighting-active-source");
  const activeRegimeLabel = document.getElementById("lighting-active-regime");

  if (!toggle) return;

  // --- Restore persisted state ---
  const savedOn = localStorage.getItem("lightingOverlay") === "true";
  const savedLitColor = localStorage.getItem("lightingLitColor") || "#FFD700";
  const savedUnlitColor =
    localStorage.getItem("lightingUnlitColor") || "#1a1a1a";
  const savedUnknownColor =
    localStorage.getItem("lightingUnknownColor") || "#888888";
  const savedWeight = parseInt(
    localStorage.getItem("lightingWeight") || "2",
    10,
  );
  const savedSourceFilter =
    localStorage.getItem("lightingSourceFilter") || "all";
  const savedRegimeFilter =
    localStorage.getItem("lightingRegimeFilter") || "all";
  const savedDimMap = localStorage.getItem("lightingDimMap");
  const dimMapEnabled = savedDimMap === null ? true : savedDimMap === "true";
  const savedHoverInfo = localStorage.getItem("lightingHoverInfo");
  const hoverInfoEnabled =
    savedHoverInfo === null ? true : savedHoverInfo === "true";

  toggle.checked = savedOn;
  litColorPicker.value = savedLitColor;
  unlitColorPicker.value = savedUnlitColor;
  unknownColorPicker.value = savedUnknownColor;
  if (dimMapToggle) dimMapToggle.checked = dimMapEnabled;
  if (hoverInfoToggle) hoverInfoToggle.checked = hoverInfoEnabled;
  weightSlider.value = savedWeight;
  weightLabel.textContent = WEIGHT_LABELS[savedWeight] || "Normal";
  if (sourceFilter) sourceFilter.value = savedSourceFilter;
  if (regimeFilter) regimeFilter.value = savedRegimeFilter;

  const updateMetadataSummary = () => {
    if (activeSourceLabel) {
      activeSourceLabel.textContent =
        SOURCE_LABELS[sourceFilter?.value || "all"];
    }
    if (activeRegimeLabel) {
      activeRegimeLabel.textContent =
        REGIME_LABELS[regimeFilter?.value || "all"];
    }
  };
  updateMetadataSummary();

  // Show/hide advanced panel to match initial state
  advancedPanel.classList.toggle("hidden", !savedOn);

  if (savedOn && mapController) {
    mapController.addLightingLayer({
      litColor: savedLitColor,
      unlitColor: savedUnlitColor,
      unknownColor: savedUnknownColor,
      litWeight: savedWeight,
      sourceFilter: savedSourceFilter,
      regimeFilter: savedRegimeFilter,
      dimMap: dimMapEnabled,
      hoverInfo: hoverInfoEnabled,
    });
  }

  // Helper: read current options and re-render
  const applyStyle = () => {
    mapController?.updateLightingStyle({
      litColor: litColorPicker.value,
      unlitColor: unlitColorPicker.value,
      unknownColor: unknownColorPicker.value,
      litWeight: parseInt(weightSlider.value, 10),
      sourceFilter: sourceFilter?.value || "all",
      regimeFilter: regimeFilter?.value || "all",
      dimMap: dimMapToggle?.checked ?? true,
      hoverInfo: hoverInfoToggle?.checked ?? true,
    });
    updateMetadataSummary();
  };

  // --- Toggle ---
  toggle.addEventListener("change", () => {
    const on = toggle.checked;
    advancedPanel.classList.toggle("hidden", !on);
    if (on) {
      mapController?.addLightingLayer({
        litColor: litColorPicker.value,
        unlitColor: unlitColorPicker.value,
        unknownColor: unknownColorPicker.value,
        litWeight: parseInt(weightSlider.value, 10),
        sourceFilter: sourceFilter?.value || "all",
        regimeFilter: regimeFilter?.value || "all",
        dimMap: dimMapToggle?.checked ?? true,
        hoverInfo: hoverInfoToggle?.checked ?? true,
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

  // --- Colour pickers (live preview on input, persist on change) ---
  litColorPicker.addEventListener("input", applyStyle);
  litColorPicker.addEventListener("change", () => {
    localStorage.setItem("lightingLitColor", litColorPicker.value);
  });

  unlitColorPicker.addEventListener("input", applyStyle);
  unlitColorPicker.addEventListener("change", () => {
    localStorage.setItem("lightingUnlitColor", unlitColorPicker.value);
  });

  unknownColorPicker.addEventListener("input", applyStyle);
  unknownColorPicker.addEventListener("change", () => {
    localStorage.setItem("lightingUnknownColor", unknownColorPicker.value);
  });

  if (dimMapToggle) {
    dimMapToggle.addEventListener("change", () => {
      localStorage.setItem(
        "lightingDimMap",
        dimMapToggle.checked ? "true" : "false",
      );
      if (toggle.checked) {
        applyStyle();
      }
    });
  }

  if (hoverInfoToggle) {
    hoverInfoToggle.addEventListener("change", () => {
      localStorage.setItem(
        "lightingHoverInfo",
        hoverInfoToggle.checked ? "true" : "false",
      );
      if (toggle.checked) {
        applyStyle();
      }
    });
  }

  // --- Weight slider ---
  weightSlider.addEventListener("input", () => {
    const v = parseInt(weightSlider.value, 10);
    weightLabel.textContent = WEIGHT_LABELS[v] || v;
    applyStyle();
  });
  weightSlider.addEventListener("change", () => {
    localStorage.setItem("lightingWeight", weightSlider.value);
  });

  if (sourceFilter) {
    sourceFilter.addEventListener("change", () => {
      localStorage.setItem("lightingSourceFilter", sourceFilter.value);
      applyStyle();
    });
  }

  if (regimeFilter) {
    regimeFilter.addEventListener("change", () => {
      localStorage.setItem("lightingRegimeFilter", regimeFilter.value);
      applyStyle();
    });
  }
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
