/**
 * Shared UI Utilities & Helpers
 */
import { appState } from './state.js';

// DOM Elements (Lazy loaded or passed in would be better, but getters work for singletons)
const getBtnText = () => document.getElementById("btn-text");
const getBtnSpinner = () => document.getElementById("btn-spinner");
const getFindRouteBtn = () => document.getElementById("find-route-btn");
const getErrorMsg = () => document.getElementById("error-message");
const getRouteStats = () => document.getElementById("route-stats");

/**
 * Set loading state on the UI.
 * @param {string} message - Loading message to display
 */
export function setLoadingState(message) {
    const btnText = getBtnText();
    const btnSpinner = getBtnSpinner();
    const findRouteBtn = getFindRouteBtn();
    const errorMsg = getErrorMsg();
    const routeStats = getRouteStats();

    if (btnText) btnText.textContent = message;
    if (btnSpinner) btnSpinner.classList.remove("hidden");
    if (findRouteBtn) findRouteBtn.disabled = true;
    if (errorMsg) errorMsg.classList.add("hidden");
    if (routeStats) routeStats.classList.add("hidden");
}

/**
 * Clear loading state.
 */
export function clearLoadingState() {
    const btnText = getBtnText();
    const btnSpinner = getBtnSpinner();
    const findRouteBtn = getFindRouteBtn();

    if (btnText) {
        btnText.textContent = appState.routingMode === "loop" ? "Find Loop" : "Find Route";
    }
    if (btnSpinner) btnSpinner.classList.add("hidden");
    if (findRouteBtn) findRouteBtn.disabled = false;
}

/**
 * Format coordinates for display.
 * @param {number} lat 
 * @param {number} lon 
 * @returns {string} Formatted string
 */
export function formatCoords(lat, lon) {
    if (lat === null || lon === null) return "";
    return `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
}

/**
 * Initialize Theme Toggle
 */
export function initThemeToggle() {
    const themeToggle = document.getElementById("theme-toggle");
    const html = document.documentElement;

    // Set initial theme
    if (
        localStorage.theme === "dark" ||
        (!("theme" in localStorage) &&
            window.matchMedia("(prefers-color-scheme: dark)").matches)
    ) {
        html.classList.add("dark");
    } else {
        html.classList.remove("dark");
    }

    // click listener
    if (themeToggle) {
        themeToggle.addEventListener("click", () => {
            html.classList.toggle("dark");
            localStorage.theme = html.classList.contains("dark") ? "dark" : "light";
        });
    }

    // Handlers for placeholder views (stats/settings pages)
    const themeToggleStats = document.getElementById("theme-toggle-stats");
    const themeToggleSettings = document.getElementById("theme-toggle-settings");

    [themeToggleStats, themeToggleSettings].forEach((toggle) => {
        if (toggle) {
            toggle.addEventListener("click", () => {
                html.classList.toggle("dark");
                localStorage.theme = html.classList.contains("dark") ? "dark" : "light";
            });
        }
    });
}
