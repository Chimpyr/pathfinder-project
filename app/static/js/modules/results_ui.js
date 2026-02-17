/**
 * Results UI (Route Cards & Stats)
 */
import { routeState, loopState } from './state.js';
import { ROUTE_CONFIG } from './config.js';
import { mapController } from './map_manager.js';

// DOM Elements
const routeOptionsList = document.getElementById("route-options-list");
const routeOptionsContainer = document.getElementById("route-options");
const routesEmptyState = document.getElementById("routes-empty-state");
const routeStatsContainer = document.getElementById("route-stats");
const statDistance = document.getElementById("stat-distance");
const statTime = document.getElementById("stat-time");

/**
 * Render route option cards in the sidebar.
 */
export function renderRouteOptions(routes) {
    if (!routeOptionsList || !routeOptionsContainer) return;

    let html = "";
    const orderedTypes = ["balanced", "baseline", "extremist"];

    for (const type of orderedTypes) {
        const routeData = routes[type];
        const config = ROUTE_CONFIG[type];
        if (!config || !routeData) continue;

        const isSelected = routeState.selected === type;
        const isVisible = routeState.visibility[type];
        const isDuplicate = routeState.duplicates?.[type];

        const distanceKm = routeData.stats?.distance_km || "?";
        const timeMin = routeData.stats?.time_min || "?";

        const duplicateBadge = isDuplicate
            ? `<span class="route-duplicate-badge">Same as ${ROUTE_CONFIG[isDuplicate]?.name || isDuplicate}</span>`
            : "";

        html += `
            <div class="route-option-card ${isSelected ? "selected" : ""} ${isDuplicate ? "is-duplicate" : ""}" 
                 data-route-type="${type}">
                <div class="flex items-center justify-between">
                    <div class="flex items-center gap-2">
                        <button class="route-visibility-toggle" 
                                data-type="${type}"
                                title="Toggle visibility">
                            <i class="fas ${isVisible ? "fa-eye" : "fa-eye-slash"} text-gray-400 hover:text-gray-600"></i>
                        </button>
                        <span class="route-colour-dot" style="background-color: ${config.colour}"></span>
                        <div>
                            <span class="font-medium text-gray-700 dark:text-gray-200">${config.name}</span>
                            <span class="text-xs text-gray-400 ml-1">(${config.subtitle})</span>
                            ${duplicateBadge}
                        </div>
                    </div>
                    ${isSelected ? '<i class="fas fa-check text-primary-500"></i>' : ""}
                </div>
                <div class="text-xs text-gray-500 dark:text-gray-400 mt-1 ml-8">
                    ${distanceKm} km • ${timeMin} min
                </div>
            </div>
        `;
    }

    routeOptionsList.innerHTML = html;
    routeOptionsContainer.classList.remove("hidden");
    if (routesEmptyState) routesEmptyState.classList.add("hidden");
    if (routeStatsContainer) routeStatsContainer.classList.remove("hidden");

    // Add listeners
    document.querySelectorAll('.route-option-card').forEach(card => {
        card.addEventListener('click', (e) => {
            // Check if click was on visibility toggle
            if (e.target.closest('.route-visibility-toggle')) return;
            handleRouteSelect(card.dataset.routeType);
        });
    });

    document.querySelectorAll('.route-visibility-toggle').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            handleRouteVisibilityToggle(btn.dataset.type);
        });
    });
}

function handleRouteSelect(routeType) {
    routeState.selected = routeType;
    if (mapController) mapController.highlightRoute(routeType);
    updateStatsForRoute(routeType);
    renderRouteOptions(routeState.routes); // Re-render to update selected state
}

function handleRouteVisibilityToggle(routeType) {
    routeState.visibility[routeType] = !routeState.visibility[routeType];
    if (mapController) mapController.setRouteVisibility(routeType, routeState.visibility[routeType]);
    renderRouteOptions(routeState.routes); // Re-render to update icon
}

export function updateStatsForRoute(routeType) {
    const routeData = routeState.routes?.[routeType];
    if (!routeData?.stats) return;

    if (statDistance) statDistance.textContent = routeData.stats.distance_km;
    if (statTime) statTime.textContent = routeData.stats.time_min;
    
    if (routeStatsContainer) routeStatsContainer.classList.remove("hidden");
}

/**
 * Render loop option cards (Multi-Loop support)
 */
export function renderLoopOptions(loops) {
    if (!routeOptionsList || !routeOptionsContainer || !loops) return;

    let html = "";
    
    loops.forEach(loop => {
        const isSelected = loopState.selectedId === loop.id;
        // Default visibility to true if not set in state, or use state
        const isVisible = loopState.visibility[loop.id] !== false; 
        
        // Loop colour from API or default
        const colour = loop.colour || "#3B82F6";

        html += `
            <div class="loop-option-card px-4 py-3 rounded-lg border cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors mb-2 ${isSelected ? "border-primary-500 bg-primary-50 dark:bg-primary-900/20" : "border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-700"}" 
                 data-loop-id="${loop.id}">
                <div class="flex items-center justify-between">
                    <div class="flex items-center gap-2">
                        <button class="loop-visibility-toggle p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-500" 
                                data-loop-id="${loop.id}"
                                title="Toggle visibility">
                            <i class="fas ${isVisible ? "fa-eye" : "fa-eye-slash"} text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"></i>
                        </button>
                        <span class="w-3 h-3 rounded-full" style="background-color: ${colour}"></span>
                        <div>
                            <span class="font-medium text-gray-700 dark:text-gray-200">${loop.label || "Loop"}</span>
                        </div>
                    </div>
                    ${isSelected ? '<i class="fas fa-check text-primary-500"></i>' : ""}
                </div>
                <div class="text-xs text-gray-500 dark:text-gray-400 mt-1 ml-8 flex gap-3">
                    <span>${loop.distance_km} km</span>
                    <span>${loop.time_min} min</span>
                    ${loop.quality_score ? `<span title="Quality Score (0-1)\n60% Distance Accuracy\n40% Scenic Quality">★ ${loop.quality_score}</span>` : ""}
                </div>
            </div>
        `;
    });

    html += `
        <div class="text-xs text-gray-400 mt-3 px-1 italic border-t border-gray-100 dark:border-gray-700 pt-2">
            <i class="fas fa-info-circle mr-1"></i> 
            Quality Score = 60% Distance + 40% Scenery
        </div>
    `;

    routeOptionsList.innerHTML = html;
    routeOptionsContainer.classList.remove("hidden");
    if (routesEmptyState) routesEmptyState.classList.add("hidden");
    if (routeStatsContainer) routeStatsContainer.classList.remove("hidden");

    // Add listeners
    document.querySelectorAll('.loop-option-card').forEach(card => {
        card.addEventListener('click', (e) => {
            if (e.target.closest('.loop-visibility-toggle')) return;
            handleLoopSelect(card.dataset.loopId, loops);
        });
    });

    document.querySelectorAll('.loop-visibility-toggle').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const loopId = btn.dataset.loopId;
            handleLoopVisibilityToggle(loopId, loops);
        });
    });
}

function handleLoopSelect(loopId, loops) {
    loopState.selectedId = loopId;
    
    // Highlight on map
    if (mapController) mapController.highlightLoop(loopId);
    
    // Update main stats
    const selectedLoop = loops.find(l => l.id === loopId);
    if (selectedLoop) {
        if (statDistance) statDistance.textContent = selectedLoop.distance_km;
        if (statTime) statTime.textContent = selectedLoop.time_min;
    }

    renderLoopOptions(loops); // Re-render to update UI selection
}

function handleLoopVisibilityToggle(loopId, loops) {
    const isVisible = loopState.visibility[loopId] !== false;
    loopState.visibility[loopId] = !isVisible;
    
    if (mapController) mapController.setLoopVisibility(loopId, !isVisible);
    renderLoopOptions(loops);
}


export function hideResults() {
    if (routeOptionsContainer) routeOptionsContainer.classList.add("hidden");
    if (routeStatsContainer) routeStatsContainer.classList.add("hidden");
    if (routesEmptyState) routesEmptyState.classList.remove("hidden");
}
