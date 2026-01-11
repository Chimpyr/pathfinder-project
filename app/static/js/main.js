/**
 * Main Application JavaScript
 * 
 * Handles dual-input mode: text addresses AND map click coordinates.
 * Features instant geocoding preview when typing addresses.
 * 
 * @author ScenicPathFinder
 */

// ============================================================================
// Theme Toggle Logic
// ============================================================================
const themeToggle = document.getElementById('theme-toggle');
const html = document.documentElement;

if (localStorage.theme === 'dark' || (!('theme' in localStorage) && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
    html.classList.add('dark');
} else {
    html.classList.remove('dark');
}

themeToggle.addEventListener('click', () => {
    html.classList.toggle('dark');
    localStorage.theme = html.classList.contains('dark') ? 'dark' : 'light';
});

// ============================================================================
// UI Element References
// ============================================================================
const routeForm = document.getElementById('route-form');
const startInput = document.getElementById('start-input');
const endInput = document.getElementById('end-input');
const startCoordsDisplay = document.getElementById('start-coords');
const endCoordsDisplay = document.getElementById('end-coords');
const clearStartBtn = document.getElementById('clear-start');
const clearEndBtn = document.getElementById('clear-end');
const clearAllBtn = document.getElementById('clear-all-btn');
const findRouteBtn = document.getElementById('find-route-btn');
const btnText = document.getElementById('btn-text');
const btnSpinner = document.getElementById('btn-spinner');
const errorMsg = document.getElementById('error-message');
const routeStats = document.getElementById('route-stats');
const statDistance = document.getElementById('stat-distance');
const statTime = document.getElementById('stat-time');
const statPace = document.getElementById('stat-pace');
const debugInfo = document.getElementById('debug-info');
const debugContent = document.getElementById('debug-content');
const instructionBanner = document.getElementById('instruction-banner');
const instructionText = document.getElementById('instruction-text');

// ============================================================================
// State Management
// ============================================================================
let startState = { lat: null, lon: null, address: null, isGeocoding: false };
let endState = { lat: null, lon: null, address: null, isGeocoding: false };

// Debounce timers
let startGeocodeTimer = null;
let endGeocodeTimer = null;
const GEOCODE_DEBOUNCE_MS = 800;

/**
 * Format coordinates for display.
 */
function formatCoords(lat, lon) {
    return `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
}

/**
 * Update instruction banner based on current state.
 */
function updateInstructions() {
    const hasStart = startState.lat !== null;
    const hasEnd = endState.lat !== null;
    
    if (startState.isGeocoding || endState.isGeocoding) {
        instructionText.innerHTML = '<i class="fas fa-spinner fa-spin mr-1"></i> Looking up address...';
        instructionBanner.className = 'mx-6 mt-4 p-3 bg-yellow-50 dark:bg-yellow-900/30 border border-yellow-200 dark:border-yellow-800 rounded-lg';
    } else if (!hasStart && !hasEnd) {
        instructionText.innerHTML = 'Type addresses below or click the map to set points';
        instructionBanner.className = 'mx-6 mt-4 p-3 bg-blue-50 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-800 rounded-lg';
    } else if (hasStart && !hasEnd) {
        instructionText.innerHTML = 'Now set your <strong>end point</strong> (type or click)';
        instructionBanner.className = 'mx-6 mt-4 p-3 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-lg';
    } else if (!hasStart && hasEnd) {
        instructionText.innerHTML = 'Now set your <strong>start point</strong> (type or click)';
        instructionBanner.className = 'mx-6 mt-4 p-3 bg-green-50 dark:bg-green-900/30 border border-green-200 dark:border-green-800 rounded-lg';
    } else {
        instructionText.innerHTML = '<i class="fas fa-check-circle mr-1"></i> Ready! Click <strong>Find Route</strong>';
        instructionBanner.className = 'mx-6 mt-4 p-3 bg-green-50 dark:bg-green-900/30 border border-green-200 dark:border-green-800 rounded-lg';
    }
}

/**
 * Show/hide clear buttons based on input content.
 */
function updateClearButtons() {
    clearStartBtn.classList.toggle('hidden', !startInput.value);
    clearEndBtn.classList.toggle('hidden', !endInput.value);
}

/**
 * Update coordinate display below inputs.
 */
function updateCoordsDisplay() {
    if (startState.lat !== null) {
        startCoordsDisplay.textContent = `📍 ${formatCoords(startState.lat, startState.lon)}`;
        startCoordsDisplay.classList.remove('hidden');
    } else {
        startCoordsDisplay.classList.add('hidden');
    }
    
    if (endState.lat !== null) {
        endCoordsDisplay.textContent = `📍 ${formatCoords(endState.lat, endState.lon)}`;
        endCoordsDisplay.classList.remove('hidden');
    } else {
        endCoordsDisplay.classList.add('hidden');
    }
}

// ============================================================================
// Debug Edge Preview Rendering
// ============================================================================

/**
 * Render edge preview in debug info panel.
 * 
 * Shows first 5 edges with their feature values prominently,
 * using emoji indicators and a compact grid layout.
 * 
 * @param {Array} edges - Array of edge feature objects from API.
 */
function renderEdgePreview(edges) {
    const container = document.getElementById('edge-preview-container');
    if (!container || !edges || edges.length === 0) {
        if (container) container.classList.add('hidden');
        return;
    }
    
    let html = '<h5 class="font-semibold mb-2 text-gray-700 dark:text-gray-300">First 5 Edges:</h5>';
    html += '<div class="space-y-2">';
    
    edges.forEach((edge, idx) => {
        html += `
            <div class="p-2 bg-white dark:bg-gray-700 rounded border border-gray-200 dark:border-gray-600">
                <div class="flex justify-between items-center mb-1">
                    <span class="font-medium text-sm">${idx + 1}. ${edge.highway}</span>
                    <span class="text-xs text-gray-500">${edge.length_m}m</span>
                </div>
                <div class="grid grid-cols-5 gap-1 text-xs">
                    <span class="text-red-500" title="Noise Factor (1=quiet, 5=noisy)">🔊 ${edge.noise_factor ?? '-'}</span>
                    <span class="text-green-500" title="Greenness (0=green, 1=no green)">🌿 ${edge.green_cost?.toFixed(2) ?? '-'}</span>
                    <span class="text-blue-500" title="Water (0=near, 1=far)">💧 ${edge.water_cost?.toFixed(2) ?? '-'}</span>
                    <span class="text-amber-500" title="Social POIs (0=near, 1=far)">🏛️ ${edge.social_cost?.toFixed(2) ?? '-'}</span>
                    <span class="text-purple-500" title="Slope (gradient %)">⛰️ ${edge.slope_cost?.toFixed(3) ?? '-'}</span>
                </div>
            </div>
        `;
    });
    
    html += '</div>';
    container.innerHTML = html;
    container.classList.remove('hidden');
}

// ============================================================================
// Geocoding Functions
// ============================================================================

/**
 * Geocode an address and place marker.
 * @param {string} address - The address to geocode.
 * @param {string} type - 'start' or 'end'.
 */
async function geocodeAddress(address, type) {
    if (!address || address.length < 3) return;
    
    // Check if it looks like coordinates already
    if (address.match(/^-?\d+\.\d+,\s*-?\d+\.\d+$/)) return;
    
    const state = type === 'start' ? startState : endState;
    state.isGeocoding = true;
    updateInstructions();
    
    try {
        const response = await fetch('/api/geocode', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ address })
        });
        
        const data = await response.json();
        
        if (response.ok && data.lat && data.lon) {
            // Update state
            state.lat = data.lat;
            state.lon = data.lon;
            state.address = address;
            
            // Place marker on map
            if (type === 'start') {
                mapController.setStartPoint(data.lat, data.lon);
            } else {
                mapController.setEndPoint(data.lat, data.lon);
            }
            
            console.log(`[Geocode] ${type}: '${address}' -> ${data.lat}, ${data.lon}`);
        } else {
            console.warn(`[Geocode] Failed for ${type}: ${data.error}`);
        }
    } catch (err) {
        console.error(`[Geocode] Error for ${type}:`, err);
    } finally {
        state.isGeocoding = false;
        updateInstructions();
        updateCoordsDisplay();
    }
}

/**
 * Debounced geocode for start input.
 */
function debounceStartGeocode() {
    if (startGeocodeTimer) clearTimeout(startGeocodeTimer);
    startGeocodeTimer = setTimeout(() => {
        geocodeAddress(startInput.value.trim(), 'start');
    }, GEOCODE_DEBOUNCE_MS);
}

/**
 * Debounced geocode for end input.
 */
function debounceEndGeocode() {
    if (endGeocodeTimer) clearTimeout(endGeocodeTimer);
    endGeocodeTimer = setTimeout(() => {
        geocodeAddress(endInput.value.trim(), 'end');
    }, GEOCODE_DEBOUNCE_MS);
}

// ============================================================================
// Map Controller Initialisation
// ============================================================================
const mapController = new MapController('map', {
    center: [51.4545, -2.5879], // Bristol
    zoom: 13,
    
    onStartSet: (lat, lon) => {
        startState = { lat, lon, address: null, isGeocoding: false };
        // Only update input if it's currently empty or contains coords
        if (!startInput.value || startInput.value.match(/^-?\d+\.\d+,\s*-?\d+\.\d+$/)) {
            startInput.value = formatCoords(lat, lon);
        }
        updateClearButtons();
        updateCoordsDisplay();
        updateInstructions();
    },
    
    onEndSet: (lat, lon) => {
        endState = { lat, lon, address: null, isGeocoding: false };
        if (!endInput.value || endInput.value.match(/^-?\d+\.\d+,\s*-?\d+\.\d+$/)) {
            endInput.value = formatCoords(lat, lon);
        }
        updateClearButtons();
        updateCoordsDisplay();
        updateInstructions();
    },
    
    onMarkersReady: () => {
        updateInstructions();
    },
    
    onMarkersCleared: () => {
        startState = { lat: null, lon: null, address: null, isGeocoding: false };
        endState = { lat: null, lon: null, address: null, isGeocoding: false };
        startInput.value = '';
        endInput.value = '';
        updateClearButtons();
        updateCoordsDisplay();
        updateInstructions();
        routeStats.classList.add('hidden');
        errorMsg.classList.add('hidden');
    }
});

// ============================================================================
// Text Input Handlers - Debounced Geocoding
// ============================================================================
startInput.addEventListener('input', () => {
    updateClearButtons();
    const value = startInput.value.trim();
    
    if (!value) {
        // Cleared input - reset state
        startState = { lat: null, lon: null, address: null, isGeocoding: false };
        if (mapController.startMarker) {
            mapController.map.removeLayer(mapController.startMarker);
            mapController.startMarker = null;
        }
        updateCoordsDisplay();
        updateInstructions();
    } else if (!value.match(/^-?\d+\.\d+,\s*-?\d+\.\d+$/)) {
        // User typed an address - trigger debounced geocode
        debounceStartGeocode();
    }
});

endInput.addEventListener('input', () => {
    updateClearButtons();
    const value = endInput.value.trim();
    
    if (!value) {
        endState = { lat: null, lon: null, address: null, isGeocoding: false };
        if (mapController.endMarker) {
            mapController.map.removeLayer(mapController.endMarker);
            mapController.endMarker = null;
        }
        updateCoordsDisplay();
        updateInstructions();
    } else if (!value.match(/^-?\d+\.\d+,\s*-?\d+\.\d+$/)) {
        debounceEndGeocode();
    }
});

// ============================================================================
// Clear Button Handlers
// ============================================================================
clearStartBtn.addEventListener('click', () => {
    startInput.value = '';
    startState = { lat: null, lon: null, address: null, isGeocoding: false };
    if (mapController.startMarker) {
        mapController.map.removeLayer(mapController.startMarker);
        mapController.startMarker = null;
    }
    updateClearButtons();
    updateCoordsDisplay();
    updateInstructions();
});

clearEndBtn.addEventListener('click', () => {
    endInput.value = '';
    endState = { lat: null, lon: null, address: null, isGeocoding: false };
    if (mapController.endMarker) {
        mapController.map.removeLayer(mapController.endMarker);
        mapController.endMarker = null;
    }
    updateClearButtons();
    updateCoordsDisplay();
    updateInstructions();
});

clearAllBtn.addEventListener('click', () => {
    mapController.clear();
});

// ============================================================================
// Form Submission Handler
// ============================================================================
routeForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    // Validate that we have coordinates for both points
    if (!startState.lat || !endState.lat) {
        errorMsg.textContent = 'Please set both start and end locations.';
        errorMsg.classList.remove('hidden');
        return;
    }
    
    // Build request payload - always use coordinates now
    const payload = {
        start_lat: startState.lat,
        start_lon: startState.lon,
        end_lat: endState.lat,
        end_lon: endState.lon
    };
    
    // UI Loading State
    btnText.textContent = 'Calculating...';
    btnSpinner.classList.remove('hidden');
    findRouteBtn.disabled = true;
    errorMsg.classList.add('hidden');
    routeStats.classList.add('hidden');
    
    try {
        const response = await fetch('/api/route', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: JSON.stringify(payload)
        });
        
        const data = await response.json();
        
        if (response.ok) {
            // Display route on map
            if (data.route_coords && data.route_coords.length > 0) {
                mapController.displayRoute(data.route_coords);
            }
            
            // Update Stats
            if (data.stats) {
                statDistance.textContent = data.stats.distance_km;
                statTime.textContent = data.stats.time_min;
                statPace.textContent = data.stats.pace_kmh;
                routeStats.classList.remove('hidden');
            }
            
            // Display edge features on map (only for short routes)
            if (data.edge_features && data.edge_features.length > 0) {
                mapController.displayEdgeFeatures(data.edge_features);
            } else {
                mapController.clearDebugLayers();
            }
            
            // Update Debug Info panel
            if (data.debug_info) {
                // Render edge preview prominently
                if (data.debug_info.edge_preview) {
                    renderEdgePreview(data.debug_info.edge_preview);
                }
                
                // Show raw debug data in collapsible section
                debugContent.textContent = JSON.stringify(data.debug_info, null, 2);
                debugInfo.classList.remove('hidden');
            } else {
                debugInfo.classList.add('hidden');
                const edgePreviewContainer = document.getElementById('edge-preview-container');
                if (edgePreviewContainer) edgePreviewContainer.classList.add('hidden');
            }
            
        } else {
            errorMsg.textContent = data.error || 'An error occurred.';
            errorMsg.classList.remove('hidden');
        }
    } catch (err) {
        console.error('[App] Network error:', err);
        errorMsg.textContent = 'Network error. Please try again.';
        errorMsg.classList.remove('hidden');
    } finally {
        btnText.textContent = 'Find Route';
        btnSpinner.classList.add('hidden');
        findRouteBtn.disabled = false;
    }
});

// ============================================================================
// Keyboard Shortcuts
// ============================================================================
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        mapController.clear();
    }
});

// Initial state
updateClearButtons();
updateInstructions();

console.log('[App] PathFinder initialised with instant geocoding');
