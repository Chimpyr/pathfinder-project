/**
 * Map Controller Module
 * 
 * Handles interactive Leaflet map for click-to-select destination feature.
 * Manages start/end markers, route display, and coordinate callbacks.
 * 
 * @author ScenicPathFinder
 */

/**
 * MapController class - manages the interactive map state and interactions.
 */
class MapController {
    /**
     * Initialise the map controller.
     * 
     * @param {string} containerId - ID of the map container element.
     * @param {Object} options - Configuration options.
     * @param {Array} options.center - Initial map centre [lat, lon].
     * @param {number} options.zoom - Initial zoom level.
     * @param {Function} options.onStartSet - Callback when start point is set.
     * @param {Function} options.onEndSet - Callback when end point is set.
     */
    constructor(containerId, options = {}) {
        this.containerId = containerId;
        this.options = {
            center: options.center || [51.4545, -2.5879], // Bristol default
            zoom: options.zoom || 13,
            onStartSet: options.onStartSet || (() => {}),
            onEndSet: options.onEndSet || (() => {}),
            onMarkersReady: options.onMarkersReady || (() => {}),
            onMarkersCleared: options.onMarkersCleared || (() => {})
        };
        
        this.map = null;
        this.startMarker = null;
        this.endMarker = null;
        this.routeLayer = null;
        this.debugLayers = [];  // Debug edge feature overlays
        
        // Interaction state: 'idle' | 'setting_start' | 'setting_end' | 'ready'
        this.state = 'idle';
        
        this._init();
    }
    
    /**
     * Initialise the Leaflet map and event handlers.
     * @private
     */
    _init() {
        // Create map instance
        this.map = L.map(this.containerId, {
            zoomControl: true,
            attributionControl: true
        }).setView(this.options.center, this.options.zoom);
        
        // Add OpenStreetMap tile layer
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
            maxZoom: 19
        }).addTo(this.map);
        
        // Set up click handler
        this.map.on('click', (e) => this._handleMapClick(e));
        
        // Start in 'setting_start' mode by default
        this.state = 'setting_start';
        
        console.log('[MapController] Initialised');
    }
    
    /**
     * Handle map click events for placing markers.
     * Smart logic: fills whichever point is missing.
     * @private
     * @param {L.LeafletMouseEvent} e - The click event.
     */
    _handleMapClick(e) {
        const { lat, lng } = e.latlng;
        
        // Smart logic: fill whichever point is missing
        if (!this.startMarker) {
            // No start marker - set start
            this.setStartPoint(lat, lng);
            if (this.endMarker) {
                this.state = 'ready';
                this.options.onMarkersReady();
            } else {
                this.state = 'setting_end';
            }
        } else if (!this.endMarker) {
            // Start exists, no end - set end
            this.setEndPoint(lat, lng);
            this.state = 'ready';
            this.options.onMarkersReady();
        } else {
            // Both exist - replace the end marker (more intuitive for adjustments)
            this.setEndPoint(lat, lng);
        }
    }
    
    /**
     * Create a custom marker icon.
     * @private
     * @param {string} colour - Marker colour ('green' or 'red').
     * @returns {L.Icon} Leaflet icon instance.
     */
    _createIcon(colour) {
        const iconUrl = colour === 'green' 
            ? 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-green.png'
            : 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-red.png';
        
        return L.icon({
            iconUrl: iconUrl,
            shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
            iconSize: [25, 41],
            iconAnchor: [12, 41],
            popupAnchor: [1, -34],
            shadowSize: [41, 41]
        });
    }
    
    /**
     * Set the start point marker.
     * 
     * @param {number} lat - Latitude.
     * @param {number} lon - Longitude.
     */
    setStartPoint(lat, lon) {
        // Remove existing start marker if present
        if (this.startMarker) {
            this.map.removeLayer(this.startMarker);
        }
        
        // Create new draggable marker
        this.startMarker = L.marker([lat, lon], {
            icon: this._createIcon('green'),
            draggable: true
        }).addTo(this.map);
        
        // Centre map on the new marker
        this.map.panTo([lat, lon]);
        
        this.startMarker.bindPopup('Start Point').openPopup();
        
        // Handle drag end
        this.startMarker.on('dragend', (e) => {
            const pos = e.target.getLatLng();
            this.options.onStartSet(pos.lat, pos.lng);
        });
        
        // Trigger callback
        this.options.onStartSet(lat, lon);
        
        console.log(`[MapController] Start point set: ${lat.toFixed(6)}, ${lon.toFixed(6)}`);
    }
    
    /**
     * Set the end point marker.
     * 
     * @param {number} lat - Latitude.
     * @param {number} lon - Longitude.
     */
    setEndPoint(lat, lon) {
        // Remove existing end marker if present
        if (this.endMarker) {
            this.map.removeLayer(this.endMarker);
        }
        
        // Create new draggable marker
        this.endMarker = L.marker([lat, lon], {
            icon: this._createIcon('red'),
            draggable: true
        }).addTo(this.map);
        
        // Centre map on the new marker
        this.map.panTo([lat, lon]);
        
        this.endMarker.bindPopup('End Point');
        
        // Handle drag end
        this.endMarker.on('dragend', (e) => {
            const pos = e.target.getLatLng();
            this.options.onEndSet(pos.lat, pos.lng);
        });
        
        // Trigger callback
        this.options.onEndSet(lat, lon);
        
        console.log(`[MapController] End point set: ${lat.toFixed(6)}, ${lon.toFixed(6)}`);
    }
    
    /**
     * Get current start coordinates.
     * @returns {Object|null} {lat, lon} or null if not set.
     */
    getStartCoords() {
        if (!this.startMarker) return null;
        const pos = this.startMarker.getLatLng();
        return { lat: pos.lat, lon: pos.lng };
    }
    
    /**
     * Get current end coordinates.
     * @returns {Object|null} {lat, lon} or null if not set.
     */
    getEndCoords() {
        if (!this.endMarker) return null;
        const pos = this.endMarker.getLatLng();
        return { lat: pos.lat, lon: pos.lng };
    }
    
    /**
     * Check if both markers are placed.
     * @returns {boolean} True if ready for routing.
     */
    isReady() {
        return this.startMarker !== null && this.endMarker !== null;
    }
    
    /**
     * Display a route on the map.
     * 
     * @param {Array} coordinates - Array of [lat, lon] pairs.
     */
    displayRoute(coordinates) {
        // Remove existing route layer
        if (this.routeLayer) {
            this.map.removeLayer(this.routeLayer);
        }
        
        if (!coordinates || coordinates.length === 0) {
            console.warn('[MapController] No coordinates provided for route');
            return;
        }
        
        // Create polyline
        this.routeLayer = L.polyline(coordinates, {
            color: '#3b82f6', // Blue
            weight: 5,
            opacity: 0.8,
            lineJoin: 'round'
        }).addTo(this.map);
        
        // Fit map to show entire route
        this.map.fitBounds(this.routeLayer.getBounds(), {
            padding: [50, 50]
        });
        
        console.log(`[MapController] Route displayed with ${coordinates.length} points`);
    }
    
    /**
     * Clear all markers and route.
     */
    clear() {
        if (this.startMarker) {
            this.map.removeLayer(this.startMarker);
            this.startMarker = null;
        }
        if (this.endMarker) {
            this.map.removeLayer(this.endMarker);
            this.endMarker = null;
        }
        if (this.routeLayer) {
            this.map.removeLayer(this.routeLayer);
            this.routeLayer = null;
        }
        
        // Clear debug layers
        this.clearDebugLayers();
        
        this.state = 'setting_start';
        this.options.onMarkersCleared();
        
        console.log('[MapController] Cleared all markers and route');
    }
    
    /**
     * Display debug edge features as coloured overlays on the map.
     * 
     * Each edge segment is coloured based on its dominant feature (lowest cost).
     * Green = greenness, Blue = water proximity, Amber = social POIs.
     * Tooltips show all feature values on hover.
     * 
     * @param {Array} edgeFeatures - Array of edge feature objects from API.
     */
    displayEdgeFeatures(edgeFeatures) {
        // Clear any existing debug layers first
        this.clearDebugLayers();
        
        if (!edgeFeatures || edgeFeatures.length === 0) {
            console.log('[MapController] No edge features to display');
            return;
        }
        
        edgeFeatures.forEach((edge, idx) => {
            // Determine dominant feature (lowest normalised cost = best)
            const features = {
                green: edge.norm_green,
                water: edge.norm_water,
                social: edge.norm_social
            };
            
            // Find best feature (lowest non-null cost)
            let bestFeature = null;
            let bestValue = Infinity;
            
            for (const [name, value] of Object.entries(features)) {
                if (value !== null && value !== undefined && value < bestValue) {
                    bestValue = value;
                    bestFeature = name;
                }
            }
            
            // Colour mapping for feature types
            const colours = {
                green: '#22c55e',   // Green for greenness
                water: '#3b82f6',   // Blue for water proximity
                social: '#f59e0b',  // Amber for social POIs
                default: '#6b7280'  // Grey for no features or unknown
            };
            
            const colour = colours[bestFeature] || colours.default;
            
            // Create segment polyline with thicker, semi-transparent styling
            const segment = L.polyline(
                [edge.from_coord, edge.to_coord],
                {
                    color: colour,
                    weight: 8,
                    opacity: 0.7,
                    className: 'debug-edge-segment'
                }
            ).addTo(this.map);
            
            // Format elevation change
            const elevChange = edge.to_elevation && edge.from_elevation 
                ? (edge.to_elevation - edge.from_elevation).toFixed(1)
                : null;
            const elevSign = elevChange > 0 ? '+' : '';
            
            // Build tooltip content with normalised feature values
            const tooltipContent = `
                <strong>Edge ${idx + 1}</strong><br>
                Highway: ${edge.highway}<br>
                Length: ${edge.length_m}m<br>
                <hr style="margin: 4px 0; border-color: #ddd;">
                <strong>Normalised (0=best):</strong><br>
                🌿 Green: ${edge.norm_green ?? 'N/A'}<br>
                💧 Water: ${edge.norm_water ?? 'N/A'}<br>
                🏛️ Social: ${edge.norm_social ?? 'N/A'}<br>
                🔇 Quiet: ${edge.norm_quiet ?? 'N/A'}<br>
                ⛰️ Slope: ${edge.norm_slope ?? 'N/A'}<br>
                <hr style="margin: 4px 0; border-color: #ddd;">
                <strong>Elevation:</strong><br>
                📍 ${edge.from_elevation ?? '?'}m → ${edge.to_elevation ?? '?'}m ${elevChange !== null ? `(${elevSign}${elevChange}m)` : ''}<br>
                ⏱️ Tobler: ${edge.slope_time_cost ?? '1.0'}×
            `;
            segment.bindTooltip(tooltipContent, { sticky: true });
            
            this.debugLayers.push(segment);
        });
        
        console.log(`[MapController] Displayed ${edgeFeatures.length} debug edge features`);
    }
    
    /**
     * Clear debug visualisation layers from the map.
     */
    clearDebugLayers() {
        if (this.debugLayers && this.debugLayers.length > 0) {
            this.debugLayers.forEach(layer => this.map.removeLayer(layer));
            this.debugLayers = [];
        }
    }
    
    /**
     * Reset to allow setting new start point.
     */
    resetToStart() {
        this.state = 'setting_start';
    }
}

// Export for use in main.js
window.MapController = MapController;
