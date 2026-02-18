/**
 * Settings UI Module
 * Handles application settings interactions
 */
import { mapController } from './map_manager.js';

export function initSettingsUI() {
    console.log("[SettingsUI] Initializing...");
    
    initMapAppearance();
}

function initMapAppearance() {
    const styleInputs = document.querySelectorAll('input[name="map-style"]');
    
    if (!styleInputs.length) {
        console.warn("[SettingsUI] No map style inputs found");
        return;
    }

    // Load saved preference
    const savedStyle = localStorage.getItem('mapStyle') || 'osm';
    
    // Set initial state on map
    // Note: mapController should be initialized by now if called from main.js after initMap
    if (mapController) {
        mapController.setTileLayer(savedStyle);
    } else {
        console.warn("[SettingsUI] mapController not ready yet");
    }
    
    // Update UI radio button
    const radio = document.querySelector(`input[name="map-style"][value="${savedStyle}"]`);
    if (radio) {
        radio.checked = true;
    }

    // Add listeners
    styleInputs.forEach(input => {
        input.addEventListener('change', (e) => {
            const styleId = e.target.value;
            
            console.log(`[SettingsUI] Map style changed to: ${styleId}`);
            
            if (mapController) {
                mapController.setTileLayer(styleId);
            }
            
            // Persist preference
            localStorage.setItem('mapStyle', styleId);
        });
    });
}
