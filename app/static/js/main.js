// Theme Toggle Logic
const themeToggle = document.getElementById('theme-toggle');
const html = document.documentElement;

// Check local storage or system preference
if (localStorage.theme === 'dark' || (!('theme' in localStorage) && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
    html.classList.add('dark');
} else {
    html.classList.remove('dark');
}

themeToggle.addEventListener('click', () => {
    html.classList.toggle('dark');
    if (html.classList.contains('dark')) {
        localStorage.theme = 'dark';
    } else {
        localStorage.theme = 'light';
    }
});

// Form Handling
const form = document.getElementById('route-form');
const mapContainer = document.getElementById('map-container');
const btnText = document.getElementById('btn-text');
const btnSpinner = document.getElementById('btn-spinner');
const errorMsg = document.getElementById('error-message');
const routeStats = document.getElementById('route-stats');
const statDistance = document.getElementById('stat-distance');
const statTime = document.getElementById('stat-time');
const statPace = document.getElementById('stat-pace');
const debugInfo = document.getElementById('debug-info');
const debugContent = document.getElementById('debug-content');

form.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    // UI Loading State
    btnText.textContent = 'Calculating...';
    btnSpinner.classList.remove('hidden');
    errorMsg.classList.add('hidden');
    routeStats.classList.add('hidden');
    
    const formData = new FormData(form);

    try {
        const response = await fetch('/', {
            method: 'POST',
            body: formData,
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        });

        const data = await response.json();

        if (response.ok) {
            const iframe = document.createElement('iframe');
            iframe.srcdoc = data.map_html;
            iframe.style.width = '100%';
            iframe.style.height = '100%';
            iframe.style.border = 'none';
            
            mapContainer.innerHTML = '';
            mapContainer.appendChild(iframe);

            // Update Stats
            if (data.stats) {
                statDistance.textContent = data.stats.distance_km;
                statTime.textContent = data.stats.time_min;
                statPace.textContent = data.stats.pace_kmh;
                routeStats.classList.remove('hidden');
            }

            // Update Debug Info
            if (data.debug_info) {
                debugContent.textContent = JSON.stringify(data.debug_info, null, 2);
                debugInfo.classList.remove('hidden');
            } else {
                debugInfo.classList.add('hidden');
            }

        } else {
            errorMsg.textContent = data.error || 'An error occurred.';
            errorMsg.classList.remove('hidden');
        }
    } catch (err) {
        errorMsg.textContent = 'Network error. Please try again.';
        errorMsg.classList.remove('hidden');
    } finally {
        btnText.textContent = 'Find Route';
        btnSpinner.classList.add('hidden');
    }
});
