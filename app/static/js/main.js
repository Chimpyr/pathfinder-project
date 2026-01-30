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

// Scenic routing preferences
const useScenicToggle = document.getElementById('use-scenic-routing');
const scenicSliders = document.getElementById('scenic-sliders');
const weightQuietness = document.getElementById('weight-quietness');
const weightGreenness = document.getElementById('weight-greenness');
const weightWater = document.getElementById('weight-water');
const weightSocial = document.getElementById('weight-social');
const weightFlatness = document.getElementById('weight-flatness');
const weightDistance = document.getElementById('weight-distance');

// ============================================================================
// Scenic Routing Toggle Handler
// ============================================================================
useScenicToggle.addEventListener('change', () => {
    const enabled = useScenicToggle.checked;
    if (enabled) {
        scenicSliders.classList.remove('opacity-50', 'pointer-events-none');
    } else {
        scenicSliders.classList.add('opacity-50', 'pointer-events-none');
    }
});

// Slider value display updates
[weightDistance, weightQuietness, weightGreenness, weightWater, weightSocial, weightFlatness].forEach(slider => {
    if (slider) {
        slider.addEventListener('input', () => {
            const valueSpan = document.getElementById(`${slider.id}-value`);
            if (valueSpan) valueSpan.textContent = slider.value;
        });
    }
});

/**
 * Get scenic weights from sliders.
 * All values use the same 0-10 scale for proportional weighting.
 * Returns null if scenic routing is disabled.
 */
function getScenicWeights() {
    if (!useScenicToggle.checked) return null;
    
    // All sliders use 0-10 scale, weights are proportional
    // Example: distance=5, greenery=10 → distance=33%, greenery=67%
    return {
        distance: parseInt(weightDistance.value),
        quietness: parseInt(weightQuietness.value),
        greenness: parseInt(weightGreenness.value),
        water: parseInt(weightWater.value),
        social: parseInt(weightSocial.value),
        slope: parseInt(weightFlatness.value)
    };
}

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
        instructionBanner.classList.remove('hidden');
        instructionText.innerHTML = '<i class="fas fa-spinner fa-spin mr-1"></i> Looking up address...';
        instructionBanner.className = 'mx-6 mt-4 p-3 bg-yellow-50 dark:bg-yellow-900/30 border border-yellow-200 dark:border-yellow-800 rounded-lg';
    } else if (!hasStart && !hasEnd) {
        instructionBanner.classList.remove('hidden');
        instructionText.innerHTML = 'Type addresses below or click the map to set points';
        instructionBanner.className = 'mx-6 mt-4 p-3 bg-blue-50 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-800 rounded-lg';
    } else if (hasStart && !hasEnd) {
        instructionBanner.classList.remove('hidden');
        instructionText.innerHTML = 'Now set your <strong>end point</strong> (type or click)';
        instructionBanner.className = 'mx-6 mt-4 p-3 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-lg';
    } else if (!hasStart && hasEnd) {
        instructionBanner.classList.remove('hidden');
        instructionText.innerHTML = 'Now set your <strong>start point</strong> (type or click)';
        instructionBanner.className = 'mx-6 mt-4 p-3 bg-green-50 dark:bg-green-900/30 border border-green-200 dark:border-green-800 rounded-lg';
    } else {
        // Both points set - hide banner as it's no longer needed
        instructionBanner.classList.add('hidden');
        return;
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
    
    let html = '<h5 class="font-semibold mb-2 text-gray-700 dark:text-gray-300">Edge Features (First 5):</h5>';
    html += '<div class="space-y-3">';
    
    edges.forEach((edge, idx) => {
        // Determine gradient direction indicator
        let gradientIcon = '➡️';
        if (edge.uphill_gradient > 1) gradientIcon = '⬆️';
        else if (edge.downhill_gradient > 1) gradientIcon = '⬇️';
        
        // Format elevation change
        const elevChange = edge.to_elevation && edge.from_elevation 
            ? (edge.to_elevation - edge.from_elevation).toFixed(1)
            : null;
        const elevSign = elevChange > 0 ? '+' : '';
        
        html += `
            <div class="p-3 bg-white dark:bg-gray-700 rounded-lg border border-gray-200 dark:border-gray-600 shadow-sm">
                <!-- Header: Edge number, highway type, length -->
                <div class="flex justify-between items-center mb-2 pb-2 border-b border-gray-100 dark:border-gray-600">
                    <span class="font-semibold text-sm text-gray-800 dark:text-gray-200">#${idx + 1} ${edge.highway}</span>
                    <span class="text-xs text-gray-500 dark:text-gray-400">${edge.length_m}m</span>
                </div>
                
                <!-- Normalised Scores (0-1, lower = better) -->
                <div class="mb-2">
                    <div class="text-xs text-gray-500 dark:text-gray-400 mb-1">Normalised Scores (0=best, 1=worst):</div>
                    <div class="grid grid-cols-5 gap-2 text-xs">
                        <div class="text-center" title="Greenness (0=green)">
                            <span class="text-green-600 dark:text-green-400">🌿</span>
                            <div class="font-mono ${edge.norm_green !== null && edge.norm_green < 0.3 ? 'text-green-600 font-bold' : ''}">${edge.norm_green ?? '-'}</div>
                        </div>
                        <div class="text-center" title="Water proximity (0=near)">
                            <span class="text-blue-600 dark:text-blue-400">💧</span>
                            <div class="font-mono ${edge.norm_water !== null && edge.norm_water < 0.3 ? 'text-blue-600 font-bold' : ''}">${edge.norm_water ?? '-'}</div>
                        </div>
                        <div class="text-center" title="Social/POIs (0=near)">
                            <span class="text-amber-600 dark:text-amber-400">🏛️</span>
                            <div class="font-mono ${edge.norm_social !== null && edge.norm_social < 0.3 ? 'text-amber-600 font-bold' : ''}">${edge.norm_social ?? '-'}</div>
                        </div>
                        <div class="text-center" title="Quietness (0=quiet)">
                            <span class="text-purple-600 dark:text-purple-400">🔇</span>
                            <div class="font-mono ${edge.norm_quiet !== null && edge.norm_quiet < 0.3 ? 'text-purple-600 font-bold' : ''}">${edge.norm_quiet ?? '-'}</div>
                        </div>
                        <div class="text-center" title="Slope difficulty (0=easy)">
                            <span class="text-red-600 dark:text-red-400">⛰️</span>
                            <div class="font-mono ${edge.norm_slope !== null && edge.norm_slope < 0.3 ? 'text-red-600 font-bold' : ''}">${edge.norm_slope ?? '-'}</div>
                        </div>
                    </div>
                </div>
                
                <!-- Elevation Data -->
                <div class="pt-2 border-t border-gray-100 dark:border-gray-600">
                    <div class="text-xs text-gray-500 dark:text-gray-400 mb-1">Elevation:</div>
                    <div class="flex justify-between text-xs">
                        <span title="From → To elevation">
                            ${gradientIcon} ${edge.from_elevation ?? '?'}m → ${edge.to_elevation ?? '?'}m
                            ${elevChange !== null ? `<span class="${elevChange > 0 ? 'text-red-500' : 'text-green-500'}">(${elevSign}${elevChange}m)</span>` : ''}
                        </span>
                        <span title="Tobler cost (1.0=flat, >1=slower)" class="font-mono ${edge.slope_time_cost > 1.2 ? 'text-red-500 font-bold' : edge.slope_time_cost < 0.95 ? 'text-green-500 font-bold' : ''}">
                            ⏱️ ${edge.slope_time_cost ?? '1.0'}×
                        </span>
                    </div>
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
    
    // Add scenic routing weights if enabled
    const scenicWeights = getScenicWeights();
    if (scenicWeights) {
        payload.use_wsm = true;
        payload.weights = scenicWeights;
        console.log('[App] Scenic routing enabled with weights:', scenicWeights);
    }
    
    // UI Loading State
    setLoadingState('Calculating...');
    
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
        
        // Handle async processing (202 Accepted)
        if (response.status === 202 && data.status === 'processing') {
            console.log('[App] Graph building in progress, starting polling...');
            await pollForTaskCompletion(data.task_id, payload);
            return;
        }
        
        // Handle sync success (200 OK)
        if (response.ok) {
            handleRouteSuccess(data);
        } else {
            errorMsg.textContent = data.error || 'An error occurred.';
            errorMsg.classList.remove('hidden');
        }
    } catch (err) {
        console.error('[App] Network error:', err);
        errorMsg.textContent = 'Network error. Please try again.';
        errorMsg.classList.remove('hidden');
    } finally {
        clearLoadingState();
    }
});

// ============================================================================
// Async Task Polling
// ============================================================================
const POLL_INTERVAL_MS = 2000;  // Poll every 2 seconds
const MAX_POLL_TIME_MS = 300000; // 5 minute timeout

/**
 * Poll for task completion and then retry the route request.
 * 
 * @param {string} taskId - The Celery task ID.
 * @param {object} originalPayload - The original route request payload.
 */
async function pollForTaskCompletion(taskId, originalPayload) {
    const startTime = Date.now();
    let pollCount = 0;
    
    const poll = async () => {
        pollCount++;
        const elapsed = Date.now() - startTime;
        
        // Timeout check
        if (elapsed > MAX_POLL_TIME_MS) {
            console.error('[App] Task polling timeout');
            errorMsg.innerHTML = `
                Graph building timed out after 5 minutes. 
                <button onclick="retryWithSync()" class="underline text-blue-600">Retry with sync mode</button>
            `;
            errorMsg.classList.remove('hidden');
            clearLoadingState();
            return;
        }
        
        try {
            const response = await fetch(`/api/task/${taskId}`);
            const data = await response.json();
            
            console.log(`[App] Task poll #${pollCount}: ${data.status}`);
            
            if (data.status === 'complete') {
                // Graph is ready, retry the route request
                setLoadingState('Graph ready, calculating route...');
                await retryRouteRequest(originalPayload);
                return;
            }
            
            if (data.status === 'failed') {
                errorMsg.textContent = data.error || 'Graph building failed.';
                errorMsg.classList.remove('hidden');
                clearLoadingState();
                return;
            }
            
            // Still processing - update UI and continue polling
            const mins = Math.floor(elapsed / 60000);
            const secs = Math.floor((elapsed % 60000) / 1000);
            setLoadingState(`Building graph... ${mins}:${secs.toString().padStart(2, '0')}`);
            
            // Schedule next poll
            setTimeout(poll, POLL_INTERVAL_MS);
            
        } catch (err) {
            console.error('[App] Poll error:', err);
            // Continue polling on network errors
            setTimeout(poll, POLL_INTERVAL_MS);
        }
    };
    
    // Start polling
    poll();
}

/**
 * Retry the route request after graph build completion.
 */
async function retryRouteRequest(payload) {
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
            handleRouteSuccess(data);
        } else {
            errorMsg.textContent = data.error || 'Route calculation failed.';
            errorMsg.classList.remove('hidden');
        }
    } catch (err) {
        console.error('[App] Retry error:', err);
        errorMsg.textContent = 'Failed to calculate route after graph build.';
        errorMsg.classList.remove('hidden');
    } finally {
        clearLoadingState();
    }
}

/**
 * Handle successful route response.
 */
function handleRouteSuccess(data) {
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
        if (data.debug_info.edge_preview) {
            renderEdgePreview(data.debug_info.edge_preview);
        }
        debugContent.textContent = JSON.stringify(data.debug_info, null, 2);
        debugInfo.classList.remove('hidden');
    } else {
        debugInfo.classList.add('hidden');
        const edgePreviewContainer = document.getElementById('edge-preview-container');
        if (edgePreviewContainer) edgePreviewContainer.classList.add('hidden');
    }
}

/**
 * Set loading state on the UI.
 */
function setLoadingState(message) {
    btnText.textContent = message;
    btnSpinner.classList.remove('hidden');
    findRouteBtn.disabled = true;
    errorMsg.classList.add('hidden');
    routeStats.classList.add('hidden');
}

/**
 * Clear loading state.
 */
function clearLoadingState() {
    btnText.textContent = 'Find Route';
    btnSpinner.classList.add('hidden');
    findRouteBtn.disabled = false;
}

/**
 * Retry with synchronous mode (fallback for timeout).
 * Exposed globally for onclick handler.
 */
window.retryWithSync = async function() {
    errorMsg.classList.add('hidden');
    setLoadingState('Retrying (sync mode)...');
    
    const payload = {
        start_lat: startState.lat,
        start_lon: startState.lon,
        end_lat: endState.lat,
        end_lon: endState.lon,
        force_sync: true  // Hint to server (if supported)
    };
    
    // Add scenic weights
    const scenicWeights = getScenicWeights();
    if (scenicWeights) {
        payload.use_wsm = true;
        payload.weights = scenicWeights;
    }
    
    await retryRouteRequest(payload);
};

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
