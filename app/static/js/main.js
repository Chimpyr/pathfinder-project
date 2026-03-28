/**
 * Main Entry Point
 * Refactored into ES Modules
 */

import { initThemeToggle } from "./modules/ui_common.js";
import {
  initMap,
  mapController,
  displayCachedTiles,
} from "./modules/map_manager.js";
import {
  initInputHandlers,
  syncInputWithCoords,
  clearInputs,
} from "./modules/input_handlers.js";
import {
  initScenicControls,
  getScenicWeights,
} from "./modules/scenic_controls.js";
import { initLayoutUI } from "./modules/layout_ui.js";
import { initRoutingUI } from "./modules/routing_ui.js";
import { getCachedTiles } from "./modules/api.js";
import { initSettingsUI } from "./modules/settings_ui.js";
import { initAuthUI } from "./modules/auth_ui.js";
import { initSavedUI } from "./modules/saved_ui.js";
import { initMovementPreferences } from "./modules/movement_prefs.js";

// Initialize Everything
document.addEventListener("DOMContentLoaded", () => {
  console.log("[App] Initializing Modules...");

  // 1. UI Basics
  initMovementPreferences();
  initThemeToggle();
  initLayoutUI();
  initScenicControls();

  // 2. Map (needs callbacks for inputs)
  initMap({
    onStartSet: (lat, lon) => syncInputWithCoords("start", lat, lon),
    onEndSet: (lat, lon) => syncInputWithCoords("end", lat, lon),
    onMarkersReady: () => {}, // Handled by sync
    onMarkersCleared: () => clearInputs(),
  });

  // 3. Inputs (needs map controller)
  initInputHandlers();

  // 4. Routing Logic
  initRoutingUI();

  // 5. Debug / Cached Tiles
  initCachedTilesDebug();

  // 6. Settings
  initSettingsUI();

  // 7. Auth / Account
  initAuthUI();

  // 8. Saved Panel
  initSavedUI();

  console.log("[App] Ready.");
});

function initCachedTilesDebug() {
  const toggle = document.getElementById("show-cached-tiles");
  const tileCountSpan = document.getElementById("tile-count");

  if (!toggle) return;

  toggle.addEventListener("change", async () => {
    if (toggle.checked) {
      try {
        const data = await getCachedTiles();
        if (data.tiles) {
          displayCachedTiles(data.tiles, []);
          tileCountSpan.textContent = `(${data.tiles.length} cached)`;
        }
      } catch (err) {
        console.error(err);
        tileCountSpan.textContent = "(error)";
      }
    } else {
      if (mapController) mapController.clearTileLayers();
      tileCountSpan.textContent = "";
    }
  });
}
