/**
 * API Interactions
 */
import { CONFIG } from './config.js';

/**
 * Generic POST request wrapper
 */
async function postData(url = "", data = {}) {
    const response = await fetch(url, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify(data),
    });
    return response;
}

/**
 * Create a generic task (fire and forget or initial start)
 */
export async function createRouteTask(payload) {
    return await postData("/api/route", payload);
}

export async function createLoopTask(payload) {
    const response = await fetch("/api/loop", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
    });
    return response;
}

/**
 * Poll a task status until completion or timeout.
 * @param {string} taskId 
 * @param {Function} onSuccess 
 * @param {Function} onError 
 * @param {number} maxTimeMs 
 */
export function pollTask(taskId, onSuccess, onError, maxTimeMs = CONFIG.MAX_POLL_TIME_MS) {
    const startTime = Date.now();

    const checkStatus = async () => {
        try {
            const response = await fetch(`/api/task/${taskId}`);
            const data = await response.json();

            if (data.state === "SUCCESS") {
                onSuccess(data.result);
            } else if (data.state === "FAILURE") {
                onError(data.status || "Task failed");
            } else {
                // PENDING or PROCESSING
                const elapsed = Date.now() - startTime;
                if (elapsed > maxTimeMs) {
                    onError("Task timed out");
                } else {
                    setTimeout(checkStatus, CONFIG.POLL_INTERVAL_MS);
                }
            }
        } catch (err) {
            console.error("[API] Poll error:", err);
            onError("Network error during polling");
        }
    };

    checkStatus();
}

/**
 * Geocode an address (API only, no UI side effects)
 * @param {string} address 
 * @returns {Promise<Object>} {lat, lon, error}
 */
export async function fetchGeocode(address) {
    try {
        const response = await fetch("/api/geocode", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ address }),
        });
        const data = await response.json();
        if (response.ok && data.lat && data.lon) {
            return { lat: data.lat, lon: data.lon };
        } else {
            return { error: data.error || "Geocoding failed" };
        }
    } catch (err) {
        return { error: err.message };
    }
}

/**
 * Submit feedback for a route
 */
export async function submitFeedback(routeType, rating) {
    // Fire and forget
    fetch("/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            route_type: routeType,
            rating: rating,
            timestamp: new Date().toISOString(),
        }),
    }).catch((err) => console.warn("[Feedback] Failed to send:", err));
}

export async function getCachedTiles() {
    const response = await fetch("/api/cached-tiles");
    return await response.json();
}
