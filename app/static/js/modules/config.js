/**
 * Configuration Constants
 */

export const CONFIG = {
    GEOCODE_DEBOUNCE_MS: 800,
    MAX_POLL_TIME_MS: 300000, // 5 minutes
    POLL_INTERVAL_MS: 2000,
};

export const ROUTE_CONFIG = {
    baseline: {
        name: "Direct",
        subtitle: "Shortest Route",
        colour: "#6B7280",
        icon: "📏",
    },
    extremist: {
        name: "Scenic",
        subtitle: "Maximum Scenery",
        colour: "#EF4444",
        icon: "🌿",
    },
    balanced: {
        name: "Balanced",
        subtitle: "Custom Mix",
        colour: "#3B82F6",
        icon: "⚖️",
    },
};
