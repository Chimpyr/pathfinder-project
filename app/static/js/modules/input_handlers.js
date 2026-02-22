/**
 * Input Handlers (Geocoding & Text Inputs)
 */
import { startState, endState } from './state.js';
import { mapController } from './map_manager.js';
import { fetchGeocode } from './api.js';
import { CONFIG } from './config.js';
import { formatCoords } from './ui_common.js';

const startInput = document.getElementById("start-input");
const endInput = document.getElementById("end-input");
const startCoordsDisplay = document.getElementById("start-coords");
const endCoordsDisplay = document.getElementById("end-coords");
const clearStartBtn = document.getElementById("clear-start");
const clearEndBtn = document.getElementById("clear-end");
const clearAllBtn = document.getElementById("clear-all-btn");

let startGeocodeTimer = null;
let endGeocodeTimer = null;

export function initInputHandlers(callbacks) {
    // Start Input
    startInput.addEventListener("input", () => {
        updateClearButtons();
        const value = startInput.value.trim();

        if (!value) {
            handleClearStart(false); 
        } else if (!value.match(/^-?\d+\.\d+,\s*-?\d+\.\d+$/)) {
             // User typed an address - trigger debounced geocode
             if (startGeocodeTimer) clearTimeout(startGeocodeTimer);
             startGeocodeTimer = setTimeout(() => {
                 performGeocode(value, "start");
             }, CONFIG.GEOCODE_DEBOUNCE_MS);
        }
    });

    // End Input
    endInput.addEventListener("input", () => {
        updateClearButtons();
        const value = endInput.value.trim();

        if (!value) {
            handleClearEnd(false);
        } else if (!value.match(/^-?\d+\.\d+,\s*-?\d+\.\d+$/)) {
             if (endGeocodeTimer) clearTimeout(endGeocodeTimer);
             endGeocodeTimer = setTimeout(() => {
                 performGeocode(value, "end");
             }, CONFIG.GEOCODE_DEBOUNCE_MS);
        }
    });

    // Clear Buttons
    clearStartBtn.addEventListener("click", () => handleClearStart(true));
    clearEndBtn.addEventListener("click", () => handleClearEnd(true));
    clearAllBtn.addEventListener("click", () => {
         if (mapController) mapController.clear(); 
         // State reset is handled via mapController callback onMarkersCleared
    });

    // Swap Locations Button
    const swapBtn = document.getElementById("swap-locations-btn");
    if (swapBtn) {
        swapBtn.addEventListener("click", swapLocations);
    }
}

async function performGeocode(address, type) {
    if (!address || address.length < 3) return;
    
    // Check if it looks like coordinates already (redundant check but safe)
    if (address.match(/^-?\d+\.\d+,\s*-?\d+\.\d+$/)) return;

    const state = type === "start" ? startState : endState;
    state.isGeocoding = true;
    
    const result = await fetchGeocode(address);
    state.isGeocoding = false;

    if (result.lat && result.lon) {
        state.lat = result.lat;
        state.lon = result.lon;
        state.address = address;

        // Place marker via MapController
        if (mapController) {
            if (type === "start") mapController.setStartPoint(result.lat, result.lon);
            else mapController.setEndPoint(result.lat, result.lon);
        }
        console.log(`[Geocode] ${type}: '${address}' -> ${result.lat}, ${result.lon}`);
    } else {
        console.warn(`[Geocode] Failed for ${type}: ${result.error}`);
    }
    
    updateCoordsDisplay();
}

function handleClearStart(clearInput = true) {
    if (clearInput) startInput.value = "";
    
    startState.lat = null;
    startState.lon = null;
    startState.address = null;
    
    if (mapController && mapController.startMarker) {
        mapController.map.removeLayer(mapController.startMarker);
        mapController.startMarker = null;
    }
    
    updateClearButtons();
    updateCoordsDisplay();
}

function handleClearEnd(clearInput = true) {
    if (clearInput) endInput.value = "";
    
    endState.lat = null;
    endState.lon = null;
    endState.address = null;
    
    if (mapController && mapController.endMarker) {
        mapController.map.removeLayer(mapController.endMarker);
        mapController.endMarker = null;
    }
    
    updateClearButtons();
    updateCoordsDisplay();
}

// Check if inputs match coords regex
const isCoords = (val) => val && val.match(/^-?\d+\.\d+,\s*-?\d+\.\d+$/);

// Exported for use by Map callbacks to sync UI
export function syncInputWithCoords(type, lat, lon) {
    const input = type === "start" ? startInput : endInput;
    if (!input.value || isCoords(input.value)) {
        input.value = formatCoords(lat, lon);
    }
    updateClearButtons();
    updateCoordsDisplay();
}

export function clearInputs() {
    startInput.value = "";
    endInput.value = "";
    updateClearButtons();
    updateCoordsDisplay();
}

function updateClearButtons() {
    clearStartBtn.classList.toggle("hidden", !startInput.value);
    clearEndBtn.classList.toggle("hidden", !endInput.value);
}

function updateCoordsDisplay() {
    if (startState.lat !== null) {
        startCoordsDisplay.textContent = `📍 ${formatCoords(startState.lat, startState.lon)}`;
        startCoordsDisplay.classList.remove("hidden");
    } else {
        startCoordsDisplay.classList.add("hidden");
    }

    if (endState.lat !== null) {
        endCoordsDisplay.textContent = `📍 ${formatCoords(endState.lat, endState.lon)}`;
        endCoordsDisplay.classList.remove("hidden");
    } else {
        endCoordsDisplay.classList.add("hidden");
    }
}

/**
 * Swap start and end locations — state, inputs, and map markers.
 */
function swapLocations() {
    // Swap state
    const tmpLat = startState.lat;
    const tmpLon = startState.lon;
    const tmpAddr = startState.address;

    startState.lat = endState.lat;
    startState.lon = endState.lon;
    startState.address = endState.address;

    endState.lat = tmpLat;
    endState.lon = tmpLon;
    endState.address = tmpAddr;

    // Swap input values
    const tmpVal = startInput.value;
    startInput.value = endInput.value;
    endInput.value = tmpVal;

    // Update map markers
    if (mapController) {
        // Remove existing markers
        if (mapController.startMarker) {
            mapController.map.removeLayer(mapController.startMarker);
            mapController.startMarker = null;
        }
        if (mapController.endMarker) {
            mapController.map.removeLayer(mapController.endMarker);
            mapController.endMarker = null;
        }

        // Re-place markers with swapped positions (don't trigger callbacks — state already updated)
        if (startState.lat !== null) {
            mapController.startMarker = L.marker([startState.lat, startState.lon], {
                icon: mapController._createIcon("green"),
                draggable: true,
            }).addTo(mapController.map);
            mapController.startMarker.bindPopup(
                mapController._buildPinPopup("Start Point", startState.lat, startState.lon)
            );
        }
        if (endState.lat !== null) {
            mapController.endMarker = L.marker([endState.lat, endState.lon], {
                icon: mapController._createIcon("red"),
                draggable: true,
            }).addTo(mapController.map);
            mapController.endMarker.bindPopup(
                mapController._buildPinPopup("End Point", endState.lat, endState.lon)
            );
        }
    }

    updateClearButtons();
    updateCoordsDisplay();
    console.log("[InputHandlers] Swapped start and end locations");
}

/**
 * Programmatically set a start point from coordinates.
 * Used by Saved panel to route from a pin.
 */
export function setStartFromCoords(lat, lon) {
    startState.lat = lat;
    startState.lon = lon;
    startState.address = null;
    startInput.value = formatCoords(lat, lon);
    if (mapController) mapController.setStartPoint(lat, lon);
    updateClearButtons();
    updateCoordsDisplay();
}

/**
 * Programmatically set an end point from coordinates.
 * Used by Saved panel to route from a pin.
 */
export function setEndFromCoords(lat, lon) {
    endState.lat = lat;
    endState.lon = lon;
    endState.address = null;
    endInput.value = formatCoords(lat, lon);
    if (mapController) mapController.setEndPoint(lat, lon);
    updateClearButtons();
    updateCoordsDisplay();
}
