/**
 * Map Manager
 * Wraps the global MapController
 */
import { formatCoords } from './ui_common.js';
import { startState, endState, resetRouteState } from './state.js';

// We assume MapController is loaded globally via script tag (leaflet dependency)
// or we could refactor MapController to be an ES module too. 
// For now, let's assume `window.MapController` exists from `map.js`.
// Ideally, `map.js` should also be a module, but let's stick to refactoring `main.js` first.


export let mapController = null;
console.log("[MapManager] Module loaded. mapController:", mapController);

/**
 * Initialize the map controller
 * @param {Object} callbacks - callbacks for UI updates (onStartSet, onEndSet, etc)
 */
export function initMap(callbacks) {
    if (typeof MapController === 'undefined') {
        console.error("[MapManager] MapController class is not defined! Check map.js loading.");
        return;
    }
    console.log("[MapManager] Initializing MapController...");
    mapController = new MapController("map", {
        center: [51.4545, -2.5879], // Bristol
        zoom: 13,
        
        onStartSet: (lat, lon) => {
            // Update State
            startState.lat = lat;
            startState.lon = lon;
            startState.address = null;
            startState.isGeocoding = false;
            
            if (callbacks.onStartSet) callbacks.onStartSet(lat, lon);
        },

        onEndSet: (lat, lon) => {
            // Update State
            endState.lat = lat;
            endState.lon = lon;
            endState.address = null;
            endState.isGeocoding = false;

            if (callbacks.onEndSet) callbacks.onEndSet(lat, lon);
        },

        onMarkersReady: () => {
            if (callbacks.onMarkersReady) callbacks.onMarkersReady();
        },

        onMarkersCleared: () => {
            // Reset State logic is handled in input handlers usually, but map clearing
            // should propagate up.
            if (callbacks.onMarkersCleared) callbacks.onMarkersCleared();
        }
    });

    // Expose for debugging if needed
    window.mapController = mapController;
}

/**
 * Display cached tiles overlay
 */
export function displayCachedTiles(tiles, usedTileIds) {
    if (mapController) {
        mapController.displayCachedTiles(tiles, usedTileIds);
    }
}

export function clearTileLayers() {
    if (mapController) {
        mapController.clearTileLayers();
    }
}
