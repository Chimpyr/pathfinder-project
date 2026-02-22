/**
 * Saved UI Module
 * Handles the Saved panel: fetching, rendering, and interacting with saved pins and queries.
 */
import { mapController } from './map_manager.js';
import { showToast, isAuthenticated } from './ui_common.js';
import { setStartFromCoords, setEndFromCoords } from './input_handlers.js';
import { appState } from './state.js';

export function initSavedUI() {
    const loginPrompt   = document.getElementById("saved-login-prompt");
    const savedContent  = document.getElementById("saved-content");
    const tabBtns       = document.querySelectorAll(".saved-tab");
    const pinsTab       = document.getElementById("saved-tab-pins");
    const routesTab     = document.getElementById("saved-tab-routes");

    if (!loginPrompt || !savedContent) return;

    // Track which pin card is currently selected
    let selectedPinCardId = null;

    // ── Tab Switching ──────────────────────────────────────────────────
    tabBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            const tab = btn.dataset.savedTab;

            tabBtns.forEach(b => b.classList.toggle("active", b === btn));

            if (tab === "pins") {
                pinsTab.classList.remove("hidden");
                routesTab.classList.add("hidden");
            } else {
                pinsTab.classList.add("hidden");
                routesTab.classList.remove("hidden");
            }
        });
    });

    // ── Refresh data when Saved panel becomes active ─────────────────
    const savedNavBtn = document.querySelector('[data-view="saved-view"]');
    if (savedNavBtn) {
        savedNavBtn.addEventListener("click", () => refreshSavedData());
    }

    // Initial check – if user is already logged in on page load
    refreshSavedData();

    // ── Live Update Events ────────────────────────────────────────────
    // Other modules dispatch these when a pin or query is saved
    document.addEventListener("saved-pin-added", () => fetchPins());
    document.addEventListener("saved-query-added", () => fetchQueries());

    // Hide/show "Set end" buttons when routing mode changes
    document.addEventListener("routing-mode-changed", (e) => {
        const isLoop = e.detail.mode === "loop";
        document.querySelectorAll(".saved-pin-end-btn").forEach(btn => {
            btn.style.display = isLoop ? "none" : "";
        });
    });

    // ── Core Functions ───────────────────────────────────────────────

    async function refreshSavedData() {
        const loggedIn = await isAuthenticated();

        if (loggedIn) {
            loginPrompt.classList.add("hidden");
            savedContent.classList.remove("hidden");
            fetchPins();
            fetchQueries();
        } else {
            loginPrompt.classList.remove("hidden");
            savedContent.classList.add("hidden");
        }
    }

    // ── PINS ─────────────────────────────────────────────────────────

    async function fetchPins() {
        try {
            const res = await fetch("/api/pins");
            if (!res.ok) return;
            const data = await res.json();
            renderPins(data.pins || []);
        } catch (err) {
            console.error("[SavedUI] Failed to fetch pins:", err);
        }
    }

    function renderPins(pins) {
        const list  = document.getElementById("saved-pins-list");
        const empty = document.getElementById("saved-pins-empty");

        if (!list) return;
        list.innerHTML = "";

        if (pins.length === 0) {
            empty.classList.remove("hidden");
            return;
        }
        empty.classList.add("hidden");

        pins.forEach(pin => {
            const card = document.createElement("div");
            card.className = "saved-card";
            card.dataset.pinId = pin.id;

            const created = new Date(pin.created_at);
            const dateStr = created.toLocaleDateString("en-GB", {
                day: "numeric", month: "short", year: "numeric",
            });

            card.innerHTML = `
                <div class="saved-card-body">
                    <div class="saved-card-icon">
                        <i class="fas fa-map-pin"></i>
                    </div>
                    <div class="saved-card-info">
                        <div class="saved-card-title-row">
                            <span class="saved-card-title">${escapeHtml(pin.label)}</span>
                            <button class="saved-card-rename" title="Rename pin" data-pin-id="${pin.id}">
                                <i class="fas fa-pencil-alt"></i>
                            </button>
                        </div>
                        <div class="saved-card-subtitle">${pin.latitude.toFixed(5)}, ${pin.longitude.toFixed(5)}</div>
                        <div class="saved-card-actions">
                            <button class="saved-pin-route-btn" data-action="start" title="Use as start location">
                                <i class="fas fa-map-marker-alt" style="color:#22c55e;"></i> Set start
                            </button>
                            <button class="saved-pin-route-btn saved-pin-end-btn" data-action="end" title="Use as end location" ${appState.routingMode === 'loop' ? 'style="display:none"' : ''}>
                                <i class="fas fa-map-marker" style="color:#ef4444;"></i> Set end
                            </button>
                        </div>
                        <div class="saved-card-meta">${dateStr}</div>
                    </div>
                    <button class="saved-card-delete" title="Delete pin" data-pin-id="${pin.id}">
                        <i class="fas fa-trash-alt"></i>
                    </button>
                </div>
            `;

            // Hover → show temp marker
            card.addEventListener("mouseenter", () => {
                if (mapController) {
                    mapController.showTempPinMarker(pin.latitude, pin.longitude, pin.label);
                }
            });

            // Mouse leave → remove temp marker (only if not selected)
            card.addEventListener("mouseleave", () => {
                if (selectedPinCardId !== pin.id && mapController) {
                    mapController.removeTempPinMarker();
                }
            });

            // Click → toggle persistent selection
            card.addEventListener("click", (e) => {
                // Don't trigger on delete/rename/route buttons
                if (e.target.closest(".saved-card-delete") || e.target.closest(".saved-card-rename") || e.target.closest(".saved-pin-route-btn")) return;

                if (selectedPinCardId === pin.id) {
                    // Deselect
                    selectedPinCardId = null;
                    card.classList.remove("selected");
                    if (mapController) mapController.removeTempPinMarker();
                } else {
                    // Deselect previous
                    const prev = list.querySelector(".saved-card.selected");
                    if (prev) prev.classList.remove("selected");

                    selectedPinCardId = pin.id;
                    card.classList.add("selected");
                    if (mapController) {
                        mapController.showTempPinMarker(pin.latitude, pin.longitude, pin.label);
                    }
                }
            });

            // Delete button
            card.querySelector(".saved-card-delete").addEventListener("click", async (e) => {
                e.stopPropagation();
                if (!confirm(`Delete pin "${pin.label}"?`)) return;

                try {
                    const res = await fetch(`/api/pins/${pin.id}`, { method: "DELETE" });
                    if (res.ok) {
                        showToast("Pin deleted", "success");
                        if (selectedPinCardId === pin.id) {
                            selectedPinCardId = null;
                            if (mapController) mapController.removeTempPinMarker();
                        }
                        fetchPins();
                    } else {
                        showToast("Failed to delete pin", "error");
                    }
                } catch {
                    showToast("Network error", "error");
                }
            });
            // Rename button
            card.querySelector(".saved-card-rename").addEventListener("click", (e) => {
                e.stopPropagation();
                startRename(card, pin);
            });

            // Pin routing buttons (Use as Start / End)
            card.querySelectorAll(".saved-pin-route-btn").forEach(btn => {
                btn.addEventListener("click", (e) => {
                    e.stopPropagation();
                    const action = btn.dataset.action;
                    if (action === "start") {
                        setStartFromCoords(pin.latitude, pin.longitude);
                        showToast(`Start set to "${pin.label}"`, "success");
                    } else {
                        setEndFromCoords(pin.latitude, pin.longitude);
                        showToast(`End set to "${pin.label}"`, "success");
                    }
                    // Switch to Finder view
                    document.querySelector('[data-view="finder-view"]')?.click();
                });
            });

            list.appendChild(card);
        });
    }

    function startRename(card, pin) {
        const titleRow = card.querySelector(".saved-card-title-row");
        if (!titleRow || titleRow.querySelector(".saved-rename-input")) return;

        const titleSpan = titleRow.querySelector(".saved-card-title");
        const renameBtn = titleRow.querySelector(".saved-card-rename");
        const oldLabel = pin.label;

        // Hide existing elements
        titleSpan.style.display = "none";
        renameBtn.style.display = "none";

        // Create inline input
        const input = document.createElement("input");
        input.type = "text";
        input.className = "saved-rename-input";
        input.value = oldLabel;
        input.maxLength = 100;
        titleRow.insertBefore(input, titleSpan);

        // Create confirm/cancel buttons
        const actions = document.createElement("span");
        actions.className = "saved-rename-actions";
        actions.innerHTML = `
            <button class="saved-rename-confirm" title="Save"><i class="fas fa-check"></i></button>
            <button class="saved-rename-cancel" title="Cancel"><i class="fas fa-times"></i></button>
        `;
        titleRow.appendChild(actions);

        input.focus();
        input.select();

        const finishRename = async (save) => {
            const newLabel = input.value.trim();
            input.remove();
            actions.remove();
            titleSpan.style.display = "";
            renameBtn.style.display = "";

            if (save && newLabel && newLabel !== oldLabel) {
                try {
                    const res = await fetch(`/api/pins/${pin.id}`, {
                        method: "PATCH",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ label: newLabel }),
                    });
                    if (res.ok) {
                        pin.label = newLabel;
                        titleSpan.textContent = newLabel;
                        showToast("Pin renamed", "success");
                    } else {
                        showToast("Failed to rename", "error");
                    }
                } catch {
                    showToast("Network error", "error");
                }
            }
        };

        actions.querySelector(".saved-rename-confirm").addEventListener("click", (e) => {
            e.stopPropagation();
            finishRename(true);
        });
        actions.querySelector(".saved-rename-cancel").addEventListener("click", (e) => {
            e.stopPropagation();
            finishRename(false);
        });
        input.addEventListener("keydown", (e) => {
            if (e.key === "Enter") finishRename(true);
            if (e.key === "Escape") finishRename(false);
        });
        input.addEventListener("click", (e) => e.stopPropagation());
    }

    // ── QUERIES / ROUTES ─────────────────────────────────────────────

    async function fetchQueries() {
        try {
            const res = await fetch("/api/queries");
            if (!res.ok) return;
            const data = await res.json();
            renderQueries(data.queries || []);
        } catch (err) {
            console.error("[SavedUI] Failed to fetch queries:", err);
        }
    }

    function renderQueries(queries) {
        const list  = document.getElementById("saved-queries-list");
        const empty = document.getElementById("saved-queries-empty");

        if (!list) return;
        list.innerHTML = "";

        if (queries.length === 0) {
            empty.classList.remove("hidden");
            return;
        }
        empty.classList.add("hidden");

        queries.forEach(query => {
            const card = document.createElement("div");
            card.className = "saved-card saved-query-card";
            card.dataset.queryId = query.id;

            const created = new Date(query.created_at);
            const dateStr = created.toLocaleDateString("en-GB", {
                day: "numeric", month: "short", year: "numeric",
            });

            // Build route type badge
            const typeBadge = query.is_loop
                ? `<span class="saved-badge saved-badge-loop"><i class="fas fa-sync-alt mr-1"></i>Loop</span>`
                : `<span class="saved-badge saved-badge-route"><i class="fas fa-route mr-1"></i>A→B</span>`;

            // Format distance
            const distStr = query.distance_km ? `${query.distance_km.toFixed(1)} km` : "—";

            // Build start/end display
            const startStr = `${query.start_lat.toFixed(4)}, ${query.start_lon.toFixed(4)}`;
            const endStr = (query.end_lat != null && query.end_lon != null)
                ? `${query.end_lat.toFixed(4)}, ${query.end_lon.toFixed(4)}`
                : "Same as start";

            // Build weight pills (only show non-zero/non-default)
            const weightPills = buildWeightPills(query.weights);

            card.innerHTML = `
                <div class="saved-card-body saved-query-body">
                    <div class="saved-card-icon saved-query-icon">
                        <i class="fas ${query.is_loop ? 'fa-sync-alt' : 'fa-route'}"></i>
                    </div>
                    <div class="saved-card-info">
                        <div class="saved-card-title-row">
                            <span class="saved-card-title">${escapeHtml(query.name)}</span>
                            <button class="saved-card-rename" title="Rename route" data-query-id="${query.id}">
                                <i class="fas fa-pencil-alt"></i>
                            </button>
                        </div>
                        <div class="saved-query-locations">
                            <span class="saved-query-point"><span class="saved-dot saved-dot-start"></span>${startStr}</span>
                            <span class="saved-query-arrow">→</span>
                            <span class="saved-query-point"><span class="saved-dot saved-dot-end"></span>${endStr}</span>
                        </div>
                        <div class="saved-query-details">
                            ${typeBadge}
                            <span class="saved-query-dist"><i class="fas fa-ruler-horizontal mr-1"></i>${distStr}</span>
                        </div>
                        ${weightPills ? `<div class="saved-query-weights">${weightPills}</div>` : ""}
                        <div class="saved-card-meta">${dateStr}</div>
                    </div>
                    <button class="saved-card-delete" title="Delete route" data-query-id="${query.id}">
                        <i class="fas fa-trash-alt"></i>
                    </button>
                </div>
            `;

            // Delete button
            card.querySelector(".saved-card-delete").addEventListener("click", async (e) => {
                e.stopPropagation();
                if (!confirm(`Delete route "${query.name}"?`)) return;

                try {
                    const res = await fetch(`/api/queries/${query.id}`, { method: "DELETE" });
                    if (res.ok) {
                        showToast("Route deleted", "success");
                        fetchQueries();
                    } else {
                        showToast("Failed to delete route", "error");
                    }
                } catch {
                    showToast("Network error", "error");
                }
            });

            // Click route card → autofill Finder with saved settings
            card.addEventListener("click", (e) => {
                if (e.target.closest(".saved-card-delete") || e.target.closest(".saved-card-rename")) return;
                loadQueryIntoFinder(query);
            });

            // Rename button
            card.querySelector(".saved-card-rename").addEventListener("click", (e) => {
                e.stopPropagation();
                startQueryRename(card, query);
            });

            list.appendChild(card);
        });
    }

    function startQueryRename(card, query) {
        const titleRow = card.querySelector(".saved-card-title-row");
        if (!titleRow || titleRow.querySelector(".saved-rename-input")) return;

        const titleSpan = titleRow.querySelector(".saved-card-title");
        const renameBtn = titleRow.querySelector(".saved-card-rename");
        const oldName = query.name;

        titleSpan.style.display = "none";
        renameBtn.style.display = "none";

        const input = document.createElement("input");
        input.type = "text";
        input.className = "saved-rename-input";
        input.value = oldName;
        input.maxLength = 100;
        titleRow.insertBefore(input, titleSpan);

        const actions = document.createElement("span");
        actions.className = "saved-rename-actions";
        actions.innerHTML = `
            <button class="saved-rename-confirm" title="Save"><i class="fas fa-check"></i></button>
            <button class="saved-rename-cancel" title="Cancel"><i class="fas fa-times"></i></button>
        `;
        titleRow.appendChild(actions);

        input.focus();
        input.select();

        const finishRename = async (save) => {
            const newName = input.value.trim();
            input.remove();
            actions.remove();
            titleSpan.style.display = "";
            renameBtn.style.display = "";

            if (save && newName && newName !== oldName) {
                try {
                    const res = await fetch(`/api/queries/${query.id}`, {
                        method: "PATCH",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ name: newName }),
                    });
                    if (res.ok) {
                        query.name = newName;
                        titleSpan.textContent = newName;
                        showToast("Route renamed", "success");
                    } else {
                        showToast("Failed to rename", "error");
                    }
                } catch {
                    showToast("Network error", "error");
                }
            }
        };

        actions.querySelector(".saved-rename-confirm").addEventListener("click", (e) => {
            e.stopPropagation();
            finishRename(true);
        });
        actions.querySelector(".saved-rename-cancel").addEventListener("click", (e) => {
            e.stopPropagation();
            finishRename(false);
        });
        input.addEventListener("keydown", (e) => {
            if (e.key === "Enter") finishRename(true);
            if (e.key === "Escape") finishRename(false);
        });
        input.addEventListener("click", (e) => e.stopPropagation());
    }

    /**
     * Load a saved query's parameters into the Finder panel.
     * Sets coordinates, routing mode, and scenic weights.
     */
    function loadQueryIntoFinder(query) {
        // 1. Set routing mode
        const modeBtn = query.is_loop
            ? document.getElementById("mode-loop")
            : document.getElementById("mode-standard");
        if (modeBtn) modeBtn.click();

        // 2. Set coordinates
        setStartFromCoords(query.start_lat, query.start_lon);
        if (!query.is_loop && query.end_lat != null && query.end_lon != null) {
            setEndFromCoords(query.end_lat, query.end_lon);
        }

        // 3. Set scenic weights if present
        if (query.weights && typeof query.weights === "object") {
            const w = query.weights;

            // Enable scenic routing toggle
            const scenicToggle = document.getElementById("use-scenic-routing");
            const hasScenic = Object.entries(w).some(([k, v]) => {
                if (k === "distance") return false;
                return (typeof v === "boolean" ? v : v > 0);
            });

            if (scenicToggle && hasScenic) {
                scenicToggle.checked = true;
                scenicToggle.dispatchEvent(new Event("change"));
            }

            // Set slider values
            const sliderMap = {
                distance: "weight-distance",
                quietness: "weight-quietness",
                greenness: "weight-greenness",
                water: "weight-water",
                nature: "weight-nature",
                flatness: "weight-flatness",
            };

            for (const [key, elId] of Object.entries(sliderMap)) {
                if (w[key] !== undefined && w[key] !== null) {
                    const el = document.getElementById(elId);
                    if (el) {
                        el.value = w[key];
                        el.dispatchEvent(new Event("input"));
                    }
                }
            }

            // Set toggles
            const socialEl = document.getElementById("weight-social");
            if (socialEl && w.social !== undefined) {
                socialEl.checked = !!w.social;
            }

            const groupNatureEl = document.getElementById("group-nature-toggle");
            if (groupNatureEl && w.group_nature !== undefined) {
                groupNatureEl.checked = !!w.group_nature;
                groupNatureEl.dispatchEvent(new Event("change"));
            }

            // Restore advanced option toggles
            const advToggles = [
                ['prefer_pedestrian', 'prefer-pedestrian-toggle'],
                ['prefer_paved', 'prefer-paved-toggle'],
                ['prefer_lit', 'prefer-lit-toggle'],
                ['heavily_avoid_unlit', 'heavily-avoid-unlit-toggle'],
                ['avoid_unsafe', 'avoid-unsafe-toggle'],
            ];
            for (const [key, elId] of advToggles) {
                if (w[key] !== undefined) {
                    const el = document.getElementById(elId);
                    if (el) el.checked = !!w[key];
                }
            }
        }

        // 4. Switch to Finder view
        document.querySelector('[data-view="finder-view"]')?.click();

        showToast(`Loaded "${query.name}" into Finder`, "success");
    }

    // ── Helpers ──────────────────────────────────────────────────────

    function buildWeightPills(weights) {
        if (!weights || typeof weights !== "object") return "";

        // Scenic preference definitions
        const preferences = [
            { key: "greenness",  icon: "🌿", name: "Greenery",  type: "slider" },
            { key: "water",      icon: "💧", name: "Water",     type: "slider" },
            { key: "quietness",  icon: "🤫", name: "Quietness", type: "slider" },
            { key: "flatness",   icon: "⛰️", name: "Flat",      type: "slider" },
            { key: "nature",     icon: "🌳", name: "Nature",    type: "slider" },
            { key: "social",     icon: "🏛️", name: "Social",    type: "toggle" },
            { key: "group_nature", icon: "🌿💧", name: "Combined Scenery", type: "toggle" },
            { key: "prefer_pedestrian", icon: "🚶", name: "Paths/Trails", type: "toggle" },
            { key: "prefer_paved",      icon: "🛤️", name: "Paved",        type: "toggle" },
            { key: "prefer_lit",        icon: "💡", name: "Lit streets",  type: "toggle" },
            { key: "heavily_avoid_unlit", icon: "🌑", name: "Avoid unlit", type: "toggle" },
            { key: "avoid_unsafe",      icon: "⚠️", name: "Avoid unsafe", type: "toggle" },
        ];

        const pills = [];
        for (const pref of preferences) {
            const val = weights[pref.key];
            if (val === undefined || val === null) continue;

            if (pref.type === "toggle") {
                // Only show if turned ON
                if (val === true) {
                    pills.push(`<span class="weight-pill weight-pill-on">${pref.icon} ${pref.name}</span>`);
                }
            } else {
                // Slider: show if value > 0
                const num = parseFloat(val);
                if (num > 0) {
                    // Convert to human-readable level
                    const level = num >= 4 ? "High" : num >= 2 ? "Med" : "Low";
                    pills.push(`<span class="weight-pill">${pref.icon} ${pref.name}: ${level}</span>`);
                }
            }
        }

        if (pills.length === 0) {
            return `<span class="weight-pill weight-pill-default">📏 Shortest distance only</span>`;
        }
        return pills.join("");
    }

    function escapeHtml(str) {
        const div = document.createElement("div");
        div.textContent = str;
        return div.innerHTML;
    }
}
