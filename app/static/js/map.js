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
      onMarkersCleared: options.onMarkersCleared || (() => {}),
    };

    this.map = null;
    this.startMarker = null;
    this.endMarker = null;
    this.routeLayer = null; // Single route (legacy)
    this.routeLayers = {}; // Multi-route: { baseline: layer, extremist: layer, balanced: layer }
    this.selectedRoute = null; // Currently highlighted route type
    this.loopLayers = {}; // Multi-loop: { loop_id: layer }
    this.selectedLoop = null; // Currently highlighted loop id
    this.debugLayers = []; // Debug edge feature overlays

    // Route colour configuration
    this.routeColours = {
      baseline: "#6B7280", // Grey
      extremist: "#EF4444", // Red
      balanced: "#3B82F6", // Blue
    };

    // Interaction state: 'idle' | 'setting_start' | 'setting_end' | 'ready'
    this.state = "idle";

    // Tile Layer Definitions
    this.tileLayers = {
      osm: {
        url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        attr: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      },
      carto_light: {
        url: "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
        attr: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
      },
      carto_dark: {
        url: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
        attr: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
      },
      carto_voyager: {
        url: "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
        attr: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
      },
    };

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
      attributionControl: true,
    }).setView(this.options.center, this.options.zoom);

    // Set initial tile layer (default to OSM)
    this.currentTileLayer = null;
    this.setTileLayer("osm");

    // Set up click handler
    this.map.on("click", (e) => this._handleMapClick(e));

    // Right-click context menu for saving pins
    this._contextMarker = null;
    this.map.on("contextmenu", (e) => this._handleContextMenu(e));

    // Start in 'setting_start' mode by default
    this.state = "setting_start";

    console.log("[MapController] Initialised");
  }

  /**
   * Change the base tile layer.
   *
   * @param {string} styleId - Key from this.tileLayers (e.g. 'osm', 'carto_dark')
   */
  setTileLayer(styleId) {
    if (!this.tileLayers[styleId]) {
      console.warn(
        `[MapController] Unknown tile style: ${styleId}, falling back to OSM`,
      );
      styleId = "osm";
    }

    // Don't reload if already active
    if (this.currentTileLayer === styleId) return;

    // Remove existing layer
    if (this.baseLayer) {
      this.map.removeLayer(this.baseLayer);
    }

    const def = this.tileLayers[styleId];
    this.baseLayer = L.tileLayer(def.url, {
      attribution: def.attr,
      maxZoom: 19,
    }).addTo(this.map);

    // Ensure tiles are behind everything else
    this.baseLayer.bringToBack();

    this.currentTileLayer = styleId;
    console.log(`[MapController] Switched tile layer to: ${styleId}`);
  }

  /**
   * Handle map click events for placing markers.
   * Smart logic: fills whichever point is missing.
   * In loop mode, only start marker is used.
   * @private
   * @param {L.LeafletMouseEvent} e - The click event.
   */
  _handleMapClick(e) {
    const { lat, lng } = e.latlng;

    // Check if we're in loop mode (global variable from main.js)
    const isLoopMode =
      typeof routingMode !== "undefined" && routingMode === "loop";

    if (isLoopMode) {
      // Loop mode: only set/replace start marker
      this.setStartPoint(lat, lng);
      this.state = "ready";
      this.options.onMarkersReady();
      return;
    }

    // Standard mode: smart logic - fill whichever point is missing
    if (!this.startMarker) {
      // No start marker - set start
      this.setStartPoint(lat, lng);
      if (this.endMarker) {
        this.state = "ready";
        this.options.onMarkersReady();
      } else {
        this.state = "setting_end";
      }
    } else if (!this.endMarker) {
      // Start exists, no end - set end
      this.setEndPoint(lat, lng);
      this.state = "ready";
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
    const iconUrl =
      colour === "green"
        ? "https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-green.png"
        : "https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-red.png";

    return L.icon({
      iconUrl: iconUrl,
      shadowUrl:
        "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png",
      iconSize: [25, 41],
      iconAnchor: [12, 41],
      popupAnchor: [1, -34],
      shadowSize: [41, 41],
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
      icon: this._createIcon("green"),
      draggable: true,
    }).addTo(this.map);

    // Centre map on the new marker
    this.map.panTo([lat, lon]);

    this.startMarker
      .bindPopup(this._buildPinPopup("Start Point", lat, lon))
      .openPopup();

    // Handle drag end
    this.startMarker.on("dragend", (e) => {
      const pos = e.target.getLatLng();
      this.options.onStartSet(pos.lat, pos.lng);
      // Update popup content with new coords
      this.startMarker.setPopupContent(
        this._buildPinPopup("Start Point", pos.lat, pos.lng),
      );
    });

    // Trigger callback
    this.options.onStartSet(lat, lon);

    console.log(
      `[MapController] Start point set: ${lat.toFixed(6)}, ${lon.toFixed(6)}`,
    );
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
      icon: this._createIcon("red"),
      draggable: true,
    }).addTo(this.map);

    // Centre map on the new marker
    this.map.panTo([lat, lon]);

    this.endMarker.bindPopup(this._buildPinPopup("End Point", lat, lon));

    // Handle drag end
    this.endMarker.on("dragend", (e) => {
      const pos = e.target.getLatLng();
      this.options.onEndSet(pos.lat, pos.lng);
      // Update popup content with new coords
      this.endMarker.setPopupContent(
        this._buildPinPopup("End Point", pos.lat, pos.lng),
      );
    });

    // Trigger callback
    this.options.onEndSet(lat, lon);

    console.log(
      `[MapController] End point set: ${lat.toFixed(6)}, ${lon.toFixed(6)}`,
    );
  }

  /**
   * Build a rich HTML popup with an editable name field and "Save Pin" button.
   * Auto-fills the name via reverse geocoding (Nominatim).
   * @param {string} label - Display label (e.g. "Start Point").
   * @param {number} lat - Latitude.
   * @param {number} lon - Longitude.
   * @returns {HTMLElement} Popup content element.
   */
  _buildPinPopup(label, lat, lon) {
    const container = document.createElement("div");
    container.style.minWidth = "200px";

    // Generate a sensible default from coordinates
    const coordLabel = `Pin at ${lat.toFixed(4)}, ${lon.toFixed(4)}`;

    container.innerHTML = `
      <div style="font-weight:600;font-size:13px;margin-bottom:2px;">${label}</div>
      <div style="font-size:11px;color:#6b7280;margin-bottom:8px;">${lat.toFixed(5)}, ${lon.toFixed(5)}</div>
      <input type="text" class="popup-pin-name-input" placeholder="Name this pin…" value="" maxlength="100"
             style="width:100%;padding:4px 8px;font-size:12px;border:1px solid #d1d5db;border-radius:6px;outline:none;margin-bottom:6px;box-sizing:border-box;">
      <div style="font-size:10px;color:#9ca3af;margin-bottom:6px;font-style:italic;" class="popup-pin-geocode-hint">Looking up location…</div>
      <button class="popup-save-pin-btn" data-lat="${lat}" data-lon="${lon}" data-label="${coordLabel}">
        <i class="fas fa-thumbtack"></i> Save Pin
      </button>
    `;

    const input = container.querySelector(".popup-pin-name-input");
    const hint = container.querySelector(".popup-pin-geocode-hint");
    const btn = container.querySelector(".popup-save-pin-btn");

    // Reverse geocode to suggest a meaningful name
    this._reverseGeocode(lat, lon).then((placeName) => {
      if (placeName) {
        input.value = placeName;
        hint.textContent = "Suggested name from location";
      } else {
        input.value = coordLabel;
        hint.textContent = "";
      }
    });

    // Check if a pin is already saved at this location
    this._isPinAlreadySaved(lat, lon).then((alreadySaved) => {
      if (alreadySaved) {
        input.style.display = "none";
        hint.style.display = "none";
        btn.classList.add("saved");
        btn.innerHTML = '<i class="fas fa-check"></i> Already saved';
      }
    });

    btn.addEventListener("click", () => this._savePinFromPopup(btn, input));
    return container;
  }

  /**
   * Check whether a pin already exists near the given coordinates.
   * Uses a ~10m tolerance to account for floating-point differences.
   * @param {number} lat
   * @param {number} lon
   * @returns {Promise<boolean>}
   */
  async _isPinAlreadySaved(lat, lon) {
    try {
      const res = await fetch("/api/pins");
      if (!res.ok) return false;
      const data = await res.json();
      const tolerance = 0.0001; // ~11 metres
      return (data.pins || []).some(
        (p) =>
          Math.abs(p.latitude - lat) < tolerance &&
          Math.abs(p.longitude - lon) < tolerance,
      );
    } catch {
      return false;
    }
  }

  /**
   * Reverse geocode coordinates to a human-readable place name.
   * Uses Nominatim (OpenStreetMap) — free, no API key needed.
   * @param {number} lat
   * @param {number} lon
   * @returns {Promise<string|null>}
   */
  async _reverseGeocode(lat, lon) {
    try {
      const res = await fetch(
        `https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lon}&format=json&zoom=18&addressdetails=1`,
        { headers: { "Accept-Language": "en" } },
      );
      if (!res.ok) return null;
      const data = await res.json();
      // Build a concise name: road + suburb/neighbourhood, or display_name truncated
      const addr = data.address || {};
      const parts = [
        addr.road || addr.pedestrian || addr.footway || addr.path || "",
        addr.suburb ||
          addr.neighbourhood ||
          addr.hamlet ||
          addr.village ||
          addr.town ||
          "",
      ].filter(Boolean);
      return parts.length > 0
        ? parts.join(", ")
        : (data.display_name || "").split(",").slice(0, 2).join(",").trim() ||
            null;
    } catch {
      return null;
    }
  }

  /**
   * Handle "Save Pin" click from a popup button.
   * @param {HTMLElement} btn - The clicked button.
   * @param {HTMLInputElement} [nameInput] - Optional name input field.
   */
  async _savePinFromPopup(btn, nameInput) {
    if (btn.classList.contains("saved")) return;

    // Auth check
    try {
      const authRes = await fetch("/auth/me");
      if (!authRes.ok) {
        this._showMapToast("Sign in to save pins", "info");
        return;
      }
    } catch {
      this._showMapToast("Sign in to save pins", "info");
      return;
    }

    const lat = parseFloat(btn.dataset.lat);
    const lon = parseFloat(btn.dataset.lon);
    // Prefer user-typed name, then fall back to data attribute
    const label =
      nameInput && nameInput.value.trim()
        ? nameInput.value.trim()
        : btn.dataset.label || `Pin at ${lat.toFixed(4)}, ${lon.toFixed(4)}`;

    btn.innerHTML = '<i class="fas fa-circle-notch fa-spin"></i>';
    try {
      const res = await fetch("/api/pins", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ label, latitude: lat, longitude: lon }),
      });
      if (res.ok) {
        btn.classList.add("saved");
        btn.innerHTML = '<i class="fas fa-check"></i> Saved';
        this._showMapToast("Pin saved!", "success");
        document.dispatchEvent(new CustomEvent("saved-pin-added"));
        if (this._contextMarker) {
          this._contextMarker._pinSaved = true;
        }
      } else {
        const data = await res.json();
        this._showMapToast(data.error || "Failed to save", "error");
        btn.innerHTML = '<i class="fas fa-thumbtack"></i> Save Pin';
      }
    } catch {
      this._showMapToast("Network error", "error");
      btn.innerHTML = '<i class="fas fa-thumbtack"></i> Save Pin';
    }
  }

  /**
   * Handle right-click context menu on map for pin saving.
   * @param {L.LeafletMouseEvent} e
   */
  _handleContextMenu(e) {
    // Remove previous context marker
    if (this._contextMarker) {
      this.map.removeLayer(this._contextMarker);
      this._contextMarker = null;
    }

    const { lat, lng } = e.latlng;
    this._contextMarker = L.marker([lat, lng], {
      icon: L.divIcon({
        className: "context-pin-icon",
        html: '<i class="fas fa-map-pin" style="font-size:24px;color:var(--primary-color);text-shadow:0 1px 3px rgba(0,0,0,0.3);"></i>',
        iconSize: [24, 24],
        iconAnchor: [12, 24],
        popupAnchor: [0, -24],
      }),
    }).addTo(this.map);

    const popup = this._buildPinPopup(
      `Pin at ${lat.toFixed(4)}, ${lng.toFixed(4)}`,
      lat,
      lng,
    );
    this._contextMarker.bindPopup(popup).openPopup();

    // Remove context marker when popup is closed
    this._contextMarker.on("popupclose", () => {
      if (this._contextMarker && !this._contextMarker._pinSaved) {
        this.map.removeLayer(this._contextMarker);
        this._contextMarker = null;
      }
    });
  }

  /**
   * Show a toast from map context (uses the same toast system).
   * @param {string} message
   * @param {string} type
   */
  _showMapToast(message, type) {
    // Dispatch a custom event that the main app can listen to,
    // or directly create a toast element.
    let container = document.getElementById("toast-container");
    if (!container) {
      container = document.createElement("div");
      container.id = "toast-container";
      container.className = "toast-container";
      document.body.appendChild(container);
    }
    const icons = {
      success: "fa-check-circle",
      error: "fa-exclamation-circle",
      info: "fa-info-circle",
    };
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `<i class="fas ${icons[type] || icons.info}"></i><span>${message}</span>`;
    container.appendChild(toast);
    setTimeout(() => {
      toast.classList.add("toast-out");
      toast.addEventListener("animationend", () => toast.remove());
    }, 3000);
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
   * Display a single route on the map (legacy single-route mode).
   *
   * @param {Array} coordinates - Array of [lat, lon] pairs.
   */
  displayRoute(coordinates) {
    // Remove existing route layer
    if (this.routeLayer) {
      this.map.removeLayer(this.routeLayer);
    }

    if (!coordinates || coordinates.length === 0) {
      console.warn("[MapController] No coordinates provided for route");
      return;
    }

    // Create polyline
    this.routeLayer = L.polyline(coordinates, {
      color: "#3b82f6", // Blue
      weight: 5,
      opacity: 0.8,
      lineJoin: "round",
    }).addTo(this.map);

    // Fit map to show entire route
    this.map.fitBounds(this.routeLayer.getBounds(), {
      padding: [50, 50],
    });

    console.log(
      `[MapController] Route displayed with ${coordinates.length} points`,
    );
  }

  /**
   * Display multiple routes on the map (multi-route mode).
   *
   * @param {Object} routes - Routes data: { baseline: {...}, extremist: {...}, balanced: {...} }
   *                          Each route has: coordinates, stats, colour
   */
  displayMultipleRoutes(routes) {
    // Clear existing route layers
    this.clearRouteLayers();

    if (!routes) {
      console.warn("[MapController] No routes provided");
      return;
    }

    let allBounds = null;

    // Create route layers for each type
    for (const [type, routeData] of Object.entries(routes)) {
      if (
        !routeData ||
        !routeData.route_coords ||
        routeData.route_coords.length === 0
      ) {
        console.warn(`[MapController] No coordinates for ${type} route`);
        continue;
      }

      const colour = this.routeColours[type] || "#6B7280";

      // Create polyline with consistent styling
      const layer = L.polyline(routeData.route_coords, {
        color: colour,
        weight: 4,
        opacity: 0.7,
        lineJoin: "round",
      }).addTo(this.map);

      // Store reference
      this.routeLayers[type] = layer;

      // Accumulate bounds
      if (allBounds) {
        allBounds.extend(layer.getBounds());
      } else {
        allBounds = layer.getBounds();
      }
    }

    // Fit map to show all routes
    if (allBounds) {
      this.map.fitBounds(allBounds, { padding: [50, 50] });
    }

    // Default: highlight balanced route
    this.highlightRoute("balanced");

    console.log(
      `[MapController] Displayed ${Object.keys(this.routeLayers).length} routes`,
    );
  }

  /**
   * Set visibility of a specific route.
   *
   * @param {string} routeType - Route type: 'baseline', 'extremist', or 'balanced'.
   * @param {boolean} visible - Whether the route should be visible.
   */
  setRouteVisibility(routeType, visible) {
    const layer = this.routeLayers[routeType];
    if (!layer) return;

    if (visible) {
      if (!this.map.hasLayer(layer)) {
        layer.addTo(this.map);
      }
    } else {
      if (this.map.hasLayer(layer)) {
        this.map.removeLayer(layer);
      }
    }

    console.log(`[MapController] Route ${routeType} visibility: ${visible}`);
  }

  /**
   * Highlight a specific route as the selected/primary route.
   * Selected route is thicker and fully opaque; others are thinner.
   *
   * @param {string} routeType - Route type to highlight.
   */
  highlightRoute(routeType) {
    this.selectedRoute = routeType;

    for (const [type, layer] of Object.entries(this.routeLayers)) {
      if (!layer || !this.map.hasLayer(layer)) continue;

      if (type === routeType) {
        // Selected: thick and opaque
        layer.setStyle({ weight: 6, opacity: 1.0 });
        layer.bringToFront();
      } else {
        // Unselected: thinner and semi-transparent
        layer.setStyle({ weight: 4, opacity: 0.5 });
      }
    }

    console.log(`[MapController] Highlighted route: ${routeType}`);
  }

  /**
   * Display multiple loop candidates on the map.
   *
   * @param {Array} loops - Array of loop objects with route_coords, colour, id, label.
   */
  displayMultipleLoops(loops) {
    this.clearLoopLayers();

    if (!loops || loops.length === 0) {
      console.warn("[MapController] No loops provided");
      return;
    }

    let allBounds = null;

    for (const loop of loops) {
      if (!loop.route_coords || loop.route_coords.length === 0) {
        console.warn(`[MapController] No coordinates for loop ${loop.id}`);
        continue;
      }

      const colour = loop.colour || "#3B82F6";

      const layer = L.polyline(loop.route_coords, {
        color: colour,
        weight: 4,
        opacity: 0.7,
        lineJoin: "round",
      }).addTo(this.map);

      // Add hover tooltip with loop info
      const loopDistance =
        loop.distance !== undefined && loop.distance !== null
          ? `${loop.distance} ${loop.distance_unit || "km"}`
          : `${loop.distance_km || "?"} km`;

      layer.bindTooltip(
        `<strong>${loop.label || loop.id}</strong><br>${loopDistance} · ${loop.time_min || "?"} min`,
        { sticky: true },
      );

      this.loopLayers[loop.id] = layer;

      if (allBounds) {
        allBounds.extend(layer.getBounds());
      } else {
        allBounds = layer.getBounds();
      }
    }

    if (allBounds) {
      this.map.fitBounds(allBounds, { padding: [50, 50] });
    }

    // Highlight the first (best) loop
    if (loops.length > 0) {
      this.highlightLoop(loops[0].id);
    }

    console.log(
      `[MapController] Displayed ${Object.keys(this.loopLayers).length} loop candidates`,
    );
  }

  /**
   * Set visibility of a specific loop candidate.
   *
   * @param {string} loopId - Loop candidate ID.
   * @param {boolean} visible - Whether the loop should be visible.
   */
  setLoopVisibility(loopId, visible) {
    const layer = this.loopLayers[loopId];
    if (!layer) return;

    if (visible) {
      if (!this.map.hasLayer(layer)) {
        layer.addTo(this.map);
      }
    } else {
      if (this.map.hasLayer(layer)) {
        this.map.removeLayer(layer);
      }
    }

    console.log(`[MapController] Loop ${loopId} visibility: ${visible}`);
  }

  /**
   * Highlight a specific loop candidate as the selected one.
   *
   * @param {string} loopId - Loop ID to highlight.
   */
  highlightLoop(loopId) {
    this.selectedLoop = loopId;

    for (const [id, layer] of Object.entries(this.loopLayers)) {
      if (!layer || !this.map.hasLayer(layer)) continue;

      if (id === loopId) {
        layer.setStyle({ weight: 6, opacity: 1.0 });
        layer.bringToFront();
      } else {
        layer.setStyle({ weight: 4, opacity: 0.5 });
      }
    }

    console.log(`[MapController] Highlighted loop: ${loopId}`);
  }

  /**
   * Clear all loop candidate layers.
   */
  clearLoopLayers() {
    for (const layer of Object.values(this.loopLayers)) {
      if (layer && this.map.hasLayer(layer)) {
        this.map.removeLayer(layer);
      }
    }
    this.loopLayers = {};
    this.selectedLoop = null;
  }

  /**
   * Clear all multi-route layers.
   */
  clearRouteLayers() {
    for (const layer of Object.values(this.routeLayers)) {
      if (layer && this.map.hasLayer(layer)) {
        this.map.removeLayer(layer);
      }
    }
    this.routeLayers = {};
    this.selectedRoute = null;
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

    // Clear multi-route layers
    this.clearRouteLayers();

    // Clear loop layers
    this.clearLoopLayers();

    // Clear debug layers
    this.clearDebugLayers();

    this.state = "setting_start";
    this.options.onMarkersCleared();

    console.log("[MapController] Cleared all markers and routes");
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
      console.log("[MapController] No edge features to display");
      return;
    }

    edgeFeatures.forEach((edge, idx) => {
      // Determine dominant feature (lowest normalised cost = best)
      const features = {
        green: edge.norm_green,
        water: edge.norm_water,
        social: edge.norm_social,
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
        green: "#22c55e", // Green for greenness
        water: "#3b82f6", // Blue for water proximity
        social: "#f59e0b", // Amber for social POIs
        default: "#6b7280", // Grey for no features or unknown
      };

      const colour = colours[bestFeature] || colours.default;

      // Create segment polyline with thicker, semi-transparent styling
      const segment = L.polyline([edge.from_coord, edge.to_coord], {
        color: colour,
        weight: 8,
        opacity: 0.7,
        className: "debug-edge-segment",
      }).addTo(this.map);

      // Format elevation change
      const elevChange =
        edge.to_elevation && edge.from_elevation
          ? (edge.to_elevation - edge.from_elevation).toFixed(1)
          : null;
      const elevSign = elevChange > 0 ? "+" : "";

      // Build tooltip content with normalised feature values
      const tooltipContent = `
                <strong>Edge ${idx + 1}</strong><br>
                Highway: ${edge.highway}<br>
                Length: ${edge.length_m}m<br>
                <hr style="margin: 4px 0; border-color: #ddd;">
                <strong>Normalised (0=best):</strong><br>
                🌿 Green: ${edge.norm_green ?? "N/A"}<br>
                💧 Water: ${edge.norm_water ?? "N/A"}<br>
                🏛️ Social: ${edge.norm_social ?? "N/A"}<br>
                🔇 Quiet: ${edge.norm_quiet ?? "N/A"}<br>
                ⛰️ Slope: ${edge.norm_slope ?? "N/A"}<br>
                <hr style="margin: 4px 0; border-color: #ddd;">
                <strong>Elevation:</strong><br>
                📍 ${edge.from_elevation ?? "?"}m → ${edge.to_elevation ?? "?"}m ${elevChange !== null ? `(${elevSign}${elevChange}m)` : ""}<br>
                ⏱️ Tobler: ${edge.slope_time_cost ?? "1.0"}×
            `;
      segment.bindTooltip(tooltipContent, { sticky: true });

      this.debugLayers.push(segment);
    });

    console.log(
      `[MapController] Displayed ${edgeFeatures.length} debug edge features`,
    );
  }

  /**
   * Clear debug visualisation layers from the map.
   */
  clearDebugLayers() {
    if (this.debugLayers && this.debugLayers.length > 0) {
      this.debugLayers.forEach((layer) => this.map.removeLayer(layer));
      this.debugLayers = [];
    }
  }

  /**
   * Reset to allow setting new start point.
   */
  resetToStart() {
    this.state = "setting_start";
  }

  /**
   * Display cached tiles as overlay rectangles for debug visualization.
   *
   * @param {Array} tiles - Array of tile objects with tile_id and bbox.
   * @param {Array} highlightedTileIds - Optional array of tile IDs to highlight in orange (used in route).
   */
  displayCachedTiles(tiles, highlightedTileIds = []) {
    // Clear any existing tile layers first
    this.clearTileLayers();

    if (!tiles || tiles.length === 0) {
      console.log("[MapController] No cached tiles to display");
      return;
    }

    this.tileLayers = [];
    const highlightSet = new Set(highlightedTileIds);

    tiles.forEach((tile) => {
      const { tile_id, bbox, size_mb, created } = tile;
      const isHighlighted = highlightSet.has(tile_id);

      // Create rectangle bounds
      const bounds = [
        [bbox.min_lat, bbox.min_lon],
        [bbox.max_lat, bbox.max_lon],
      ];

      // Highlighted tiles (used in route) are orange, others are purple
      const color = isHighlighted ? "#F97316" : "#9333EA"; // Orange vs Purple
      const fillOpacity = isHighlighted ? 0.25 : 0.12;

      // Create rectangle with appropriate styling
      const rect = L.rectangle(bounds, {
        color: color,
        fillColor: color,
        fillOpacity: fillOpacity,
        weight: isHighlighted ? 3 : 2,
        dashArray: isHighlighted ? null : "5, 5", // Solid for highlighted, dashed for cached
      });

      // Format creation date
      const createdDate = created
        ? new Date(created * 1000).toLocaleString()
        : "Unknown";

      // Add tooltip with tile info
      const statusLabel = isHighlighted
        ? '<span style="color: #F97316; font-weight: bold;">🚀 Used in Route</span>'
        : '<span style="color: #9333EA;">📦 Cached</span>';

      rect.bindTooltip(
        `
                <div style="margin-bottom: 4px;">
                    ${statusLabel}
                </div>
                <div style="font-weight: bold; margin-bottom: 4px;">
                    🗃️ Tile: ${tile_id}
                </div>
                <div style="font-size: 11px;">
                    📦 Size: ${size_mb?.toFixed(1) || "?"} MB<br>
                    📅 Created: ${createdDate}
                </div>
            `,
        {
          sticky: true,
          className: "tile-tooltip",
        },
      );

      rect.addTo(this.map);
      this.tileLayers.push(rect);
    });

    const highlightCount = highlightedTileIds.length;
    console.log(
      `[MapController] Displayed ${tiles.length} cached tile(s), ${highlightCount} highlighted`,
    );
  }

  /**
   * Clear tile overlay layers from the map.
   */
  clearTileLayers() {
    if (this.tileLayers && this.tileLayers.length > 0) {
      this.tileLayers.forEach((layer) => this.map.removeLayer(layer));
      this.tileLayers = [];
    }
  }

  /**
   * Add the street lighting vector tile overlay from Martin tileserver.
   * @param {Object} options - Optional style overrides.
   * @param {string} options.litColor     - Hex colour for lit streets (default #FFD700).
   * @param {string} options.unlitColor   - Hex colour for unlit streets (default #1a1a1a).
   * @param {string} options.unknownColor - Hex colour for unknown streets (default #888888).
   * @param {number} options.litWeight    - Line weight for lit streets (default 2).
   */
  addLightingLayer(options = {}) {
    // Persist current options so updateLightingStyle can reference them
    this.lightingOptions = {
      litColor: options.litColor ?? this.lightingOptions?.litColor ?? "#FFD700",
      unlitColor:
        options.unlitColor ?? this.lightingOptions?.unlitColor ?? "#1a1a1a",
      unknownColor:
        options.unknownColor ?? this.lightingOptions?.unknownColor ?? "#888888",
      litWeight: options.litWeight ?? this.lightingOptions?.litWeight ?? 2,
      sourceFilter:
        options.sourceFilter ?? this.lightingOptions?.sourceFilter ?? "all",
      regimeFilter:
        options.regimeFilter ?? this.lightingOptions?.regimeFilter ?? "all",
    };

    const {
      litColor,
      unlitColor,
      unknownColor,
      litWeight,
      sourceFilter,
      regimeFilter,
    } = this.lightingOptions;

    // Remove existing layer before re-adding with new style
    if (this.lightingLayer) {
      this.map.removeLayer(this.lightingLayer);
      this.lightingLayer = null;
    }

    const protocol = window.location.protocol;
    const hostname = window.location.hostname;
    const useFilteredEndpoint =
      sourceFilter !== "all" || regimeFilter !== "all";
    const query = new URLSearchParams({
      source_filter: sourceFilter,
      regime_filter: regimeFilter,
    }).toString();
    const endpoint = useFilteredEndpoint
      ? `street_lighting_filtered/{z}/{x}/{y}.pbf?${query}`
      : "street_lighting/{z}/{x}/{y}.pbf";
    const url = `${protocol}//${hostname}:3000/${endpoint}`;

    console.log(
      `[MapController] Fetching lighting tiles from: ${url}`,
      this.lightingOptions,
    );

    this.lightingLayer = L.vectorGrid.protobuf(url, {
      vectorTileLayerStyles: {
        street_lighting: (properties) => {
          const status = properties.lit_status; // 'lit' | 'unlit' | 'unknown'
          const sourcePrimary = (properties.lit_source_primary || "osm")
            .toString()
            .toLowerCase();
          const sourceDetail = (properties.lit_source_detail || sourcePrimary)
            .toString()
            .toLowerCase();
          const osmLitRaw = (properties.osm_lit_raw || "")
            .toString()
            .trim()
            .toLowerCase();
          const hasExplicitOsmLitTag = [
            "yes",
            "true",
            "automatic",
            "24/7",
            "no",
          ].includes(osmLitRaw);
          const regime = (
            properties.lighting_regime ||
            (status === "lit"
              ? "all_night"
              : status === "unlit"
                ? "unlit"
                : "unknown")
          )
            .toString()
            .toLowerCase();

          const sourceMatches =
            sourceFilter === "all" ||
            (sourceFilter === "osm"
              ? sourcePrimary === "osm" ||
                sourceDetail === "osm" ||
                hasExplicitOsmLitTag
              : sourceFilter === sourcePrimary ||
                sourceFilter === sourceDetail);

          const regimeMatches =
            regimeFilter === "all" || regimeFilter === regime;

          if (!sourceMatches || !regimeMatches) {
            return {
              weight: 0,
              opacity: 0,
              color: "transparent",
            };
          }

          if (status === "lit") {
            return {
              weight: litWeight,
              color: litColor,
              opacity: 0.85,
            };
          } else if (status === "unlit") {
            return {
              weight: Math.max(1, litWeight - 1),
              color: unlitColor,
              opacity: 0.6,
            };
          } else {
            // 'unknown' — no lit tag, render subtly
            return {
              weight: litWeight,
              color: unknownColor,
              opacity: 0.25,
            };
          }
        },
      },
      interactive: true,
    });

    this.lightingLayer.addTo(this.map);
    console.log("[MapController] Street lighting layer added");
  }

  /**
   * Update street lighting style without toggling — re-renders with new options.
   * Only acts if the layer is currently visible.
   * @param {Object} options - Same options as addLightingLayer.
   */
  updateLightingStyle(options = {}) {
    if (!this.lightingLayer) return; // layer not active, nothing to do
    this.addLightingLayer(options); // re-create with merged options
  }

  /**
   * Remove the street lighting overlay from the map.
   */
  removeLightingLayer() {
    if (this.lightingLayer) {
      this.map.removeLayer(this.lightingLayer);
      this.lightingLayer = null;
      console.log("[MapController] Street lighting layer removed");
    }
  }

  // ═══════════════════════════════════════════════════════════════════
  //  TEMPORARY PIN MARKER (for Saved panel hover/click preview)
  // ═══════════════════════════════════════════════════════════════════

  /**
   * Show a temporary preview pin on the map.
   * Replaces any existing temp pin. Used by the Saved panel.
   * @param {number} lat
   * @param {number} lon
   * @param {string} [label]
   */
  showTempPinMarker(lat, lon, label = "") {
    this.removeTempPinMarker();

    this._tempPinMarker = L.marker([lat, lon], {
      icon: L.divIcon({
        className: "temp-pin-icon",
        html: '<i class="fas fa-map-pin" style="font-size:28px;color:#3b82f6;text-shadow:0 2px 6px rgba(59,130,246,0.4);"></i>',
        iconSize: [28, 28],
        iconAnchor: [14, 28],
        popupAnchor: [0, -28],
      }),
      interactive: false,
    }).addTo(this.map);

    if (label) {
      this._tempPinMarker.bindTooltip(label, {
        permanent: true,
        direction: "top",
        offset: [0, -8],
      });
    }

    this.map.panTo([lat, lon], { animate: true, duration: 0.4 });
  }

  /**
   * Remove the current temporary preview pin (if any).
   */
  removeTempPinMarker() {
    if (this._tempPinMarker) {
      this.map.removeLayer(this._tempPinMarker);
      this._tempPinMarker = null;
    }
  }
}

// Export for use in main.js
window.MapController = MapController;
