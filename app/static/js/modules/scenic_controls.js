/**
 * Scenic Routing Controls
 */

const useScenicToggle = document.getElementById("use-scenic-routing");
const scenicSliders = document.getElementById("scenic-sliders");
const groupNatureToggle = document.getElementById("group-nature-toggle");

// Sliders
const weightDistance = document.getElementById("weight-distance");
const weightQuietness = document.getElementById("weight-quietness");
const weightGreenness = document.getElementById("weight-greenness");
const weightWater = document.getElementById("weight-water");
const weightSocial = document.getElementById("weight-social");
const weightFlatness = document.getElementById("weight-flatness");
const weightNature = document.getElementById("weight-nature");

export function initScenicControls() {
    if (useScenicToggle) {
        useScenicToggle.addEventListener("change", updateScenicCollapseState);
        
        // Also toggle on header click
        const scenicHeader = document.getElementById("scenic-preferences-header");
        if (scenicHeader) {
            scenicHeader.addEventListener("click", () => {
                useScenicToggle.checked = !useScenicToggle.checked;
                updateScenicCollapseState();
            });
        }
    }

    if (groupNatureToggle) {
        groupNatureToggle.addEventListener("change", updateNatureGrouping);
    }

    // Initialize value displays for standard range inputs
    [weightDistance, weightQuietness, weightGreenness, weightWater, weightNature].forEach(slider => {
        if (slider) {
            slider.addEventListener("input", () => {
                const valueSpan = document.getElementById(`${slider.id}-value`);
                if (valueSpan) valueSpan.textContent = slider.value;
            });
        }
    });

    // Special handler for Slope slider to show text labels
    if (weightFlatness) {
        weightFlatness.addEventListener("input", () => {
             const valueSpan = document.getElementById("weight-flatness-value");
             const val = parseInt(weightFlatness.value);
             if (valueSpan) {
                 if (val === 0) valueSpan.textContent = "Neutral";
                 else if (val > 0) valueSpan.textContent = `Avoid +${val}`;
                 else valueSpan.textContent = `Prefer +${Math.abs(val)}`;
             }
        });
    }
}

function updateScenicCollapseState() {
    if (!useScenicToggle || !scenicSliders) return;
    
    if (useScenicToggle.checked) {
        scenicSliders.classList.remove("max-h-0", "opacity-0");
        scenicSliders.classList.add("max-h-[800px]", "opacity-100");
    } else {
        scenicSliders.classList.remove("max-h-[800px]", "opacity-100");
        scenicSliders.classList.add("max-h-0", "opacity-0");
    }
}

function updateNatureGrouping() {
    const grouped = groupNatureToggle.checked;
    const greeneryGroup = document.getElementById("greenery-slider-group");
    const waterGroup = document.getElementById("water-slider-group");
    const natureGroup = document.getElementById("nature-slider-group");

    if (grouped) {
        if (greeneryGroup) greeneryGroup.classList.add("hidden");
        if (waterGroup) waterGroup.classList.add("hidden");
        if (natureGroup) natureGroup.classList.remove("hidden");
    } else {
        if (greeneryGroup) greeneryGroup.classList.remove("hidden");
        if (waterGroup) waterGroup.classList.remove("hidden");
        if (natureGroup) natureGroup.classList.add("hidden");
    }
}

/**
 * Get current scenic weights configuration
 */
export function getScenicWeights() {
    if (!useScenicToggle || !useScenicToggle.checked) return null;

    const isNatureGrouped = groupNatureToggle && groupNatureToggle.checked;
    let greennessVal, waterVal;

    if (isNatureGrouped) {
        greennessVal = parseInt(weightNature.value);
        waterVal = 0;
    } else {
        greennessVal = parseInt(weightGreenness.value);
        waterVal = parseInt(weightWater.value);
    }

    const socialVal = weightSocial && weightSocial.checked ? 5 : 0;
    
    // Read slope value from slider (-5 to 5)
    const slopeVal = weightFlatness ? parseInt(weightFlatness.value) : 0;

    return {
        distance: parseInt(weightDistance.value),
        quietness: parseInt(weightQuietness.value),
        greenness: greennessVal,
        water: waterVal,
        social: socialVal,
        slope: slopeVal,
    };
}
