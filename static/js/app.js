// Global variables
let map;
let radarSites = [];
let metarSites = [];
let selectedSite = null;
let metarData = null;
let stormMotion = null;
let radarMarkers = [];
let metarMarkers = [];
let warningLayers = [];

// Initialize the application
document.addEventListener('DOMContentLoaded', function() {
    initializeMap();
    loadRadarSites();
    setupEventListeners();
    loadWarnings();
});

// Initialize Leaflet map
function initializeMap() {
    map = L.map('map').setView([39.8283, -98.5795], 4);
    
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors',
        maxZoom: 10
    }).addTo(map);
}

// Load radar sites from API
async function loadRadarSites() {
    try {
        showLoading('Loading radar sites...');
        const response = await fetch('/api/radar-sites');
        radarSites = await response.json();
        addRadarSitesToMap();
        hideLoading();
    } catch (error) {
        showMessage('Error loading radar sites: ' + error.message, 'error');
        hideLoading();
    }
}

// Add radar sites to map
function addRadarSitesToMap() {
    // Clear existing markers
    radarMarkers.forEach(marker => map.removeLayer(marker));
    radarMarkers = [];
    
    radarSites.forEach(site => {
        const marker = L.circleMarker([site.lat, site.lon], {
            radius: 4,
            color: 'red',
            fillColor: 'red',
            fillOpacity: 0.7,
            weight: 2
        });
        
        marker.bindPopup(`<b>${site.id}</b><br>${site.name}`);
        marker.bindTooltip(site.id);
        
        marker.on('click', function() {
            selectRadarSite(site);
        });
        
        marker.addTo(map);
        radarMarkers.push(marker);
    });
}

// Select a radar site
function selectRadarSite(site) {
    selectedSite = site;
    
    // Update UI
    document.getElementById('siteInfo').innerHTML = `
        <p><strong>Site:</strong> ${site.id}</p>
        <p><strong>Location:</strong> ${site.name}</p>
        <p><strong>Coordinates:</strong> ${site.lat.toFixed(3)}, ${site.lon.toFixed(3)}</p>
        <p><strong>Elevation:</strong> ${site.elevation.toFixed(0)} ft</p>
    `;
    
    document.getElementById('loadVadBtn').disabled = false;
    
    // Center map on selected site
    map.setView([site.lat, site.lon], 8);
    
    // Load nearby METAR sites
    loadNearbyMetarSites(site);
    
    showMessage(`Selected radar site: ${site.id}`, 'success');
}

// Load nearby METAR sites
async function loadNearbyMetarSites(radarSite) {
    try {
        const response = await fetch('/api/metar-sites');
        const allMetarSites = await response.json();
        
        // Clear existing METAR markers
        metarMarkers.forEach(marker => map.removeLayer(marker));
        metarMarkers = [];
        
        // Find METAR sites within 100 nautical miles
        const nearbyMetar = allMetarSites.filter(metar => {
            const distance = calculateDistance(radarSite.lat, radarSite.lon, metar.lat, metar.lon);
            return distance <= 100;
        });
        
        // Add METAR markers to map
        nearbyMetar.forEach(metar => {
            const marker = L.circleMarker([metar.lat, metar.lon], {
                radius: 3,
                color: 'blue',
                fillColor: 'blue',
                fillOpacity: 0.7,
                weight: 1
            });
            
            marker.bindPopup(`<b>${metar.id}</b><br>${metar.name}`);
            marker.bindTooltip(metar.id);
            
            marker.on('click', function() {
                document.getElementById('metarStation').value = metar.id;
            });
            
            marker.addTo(map);
            metarMarkers.push(marker);
        });
        
    } catch (error) {
        console.error('Error loading METAR sites:', error);
    }
}

// Calculate distance between two points (nautical miles)
function calculateDistance(lat1, lon1, lat2, lon2) {
    const R = 3440.065; // Earth's radius in nautical miles
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLon = (lon2 - lon1) * Math.PI / 180;
    const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
              Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
              Math.sin(dLon/2) * Math.sin(dLon/2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
    return R * c;
}

// Load weather warnings
async function loadWarnings() {
    try {
        if (!document.getElementById('showWarnings').checked) return;
        
        const response = await fetch('/api/warnings');
        const warnings = await response.json();
        
        // Clear existing warning layers
        warningLayers.forEach(layer => map.removeLayer(layer));
        warningLayers = [];
        
        warnings.forEach(warning => {
            if (warning.geometry && warning.geometry.coordinates) {
                const color = getWarningColor(warning.properties.event);
                
                const layer = L.geoJSON(warning.geometry, {
                    style: {
                        color: color,
                        weight: 2,
                        opacity: 0.8,
                        fillOpacity: 0.3
                    }
                });
                
                layer.bindPopup(`
                    <b>${warning.properties.event}</b><br>
                    <strong>Area:</strong> ${warning.properties.areaDesc}<br>
                    <strong>Headline:</strong> ${warning.properties.headline}
                `);
                
                layer.addTo(map);
                warningLayers.push(layer);
            }
        });
        
    } catch (error) {
        console.error('Error loading warnings:', error);
    }
}

// Get warning color based on event type
function getWarningColor(eventType) {
    switch (eventType.toLowerCase()) {
        case 'tornado warning':
            return '#FF0000';
        case 'severe thunderstorm warning':
            return '#FFA500';
        default:
            return '#FFFF00';
    }
}

// Setup event listeners
function setupEventListeners() {
    // Reset button
    document.getElementById('resetBtn').addEventListener('click', resetApplication);
    
    // Load VAD data button
    document.getElementById('loadVadBtn').addEventListener('click', loadVadData);
    
    // Load METAR data button
    document.getElementById('loadMetarBtn').addEventListener('click', loadMetarData);
    
    // Set storm motion button
    document.getElementById('setStormMotionBtn').addEventListener('click', setStormMotion);
    
    // Plot hodograph button
    document.getElementById('plotHodographBtn').addEventListener('click', plotHodograph);
    
    // Show warnings checkbox
    document.getElementById('showWarnings').addEventListener('change', function() {
        if (this.checked) {
            loadWarnings();
        } else {
            warningLayers.forEach(layer => map.removeLayer(layer));
            warningLayers = [];
        }
    });
    
    // METAR station input enter key
    document.getElementById('metarStation').addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            loadMetarData();
        }
    });
}

// Load VAD data for selected site
async function loadVadData() {
    if (!selectedSite) {
        showMessage('Please select a radar site first', 'error');
        return;
    }
    
    try {
        showLoading('Loading VAD data...');
        const response = await fetch(`/api/vad-data/${selectedSite.id}`);
        const data = await response.json();
        
        if (data.error) {
            showMessage('VAD Error: ' + data.error, 'error');
        } else {
            showMessage(`VAD data loaded: ${data.data_points} points, max height: ${data.max_height.toFixed(0)}m`, 'success');
            document.getElementById('plotHodographBtn').disabled = false;
        }
        
        hideLoading();
    } catch (error) {
        showMessage('Error loading VAD data: ' + error.message, 'error');
        hideLoading();
    }
}

// Load METAR data
async function loadMetarData() {
    const station = document.getElementById('metarStation').value.trim().toUpperCase();
    
    if (!station) {
        showMessage('Please enter a METAR station ID', 'error');
        return;
    }
    
    try {
        showLoading('Loading METAR data...');
        const response = await fetch(`/api/metar/${station}`);
        const data = await response.json();
        
        if (data.error) {
            showMessage('METAR Error: ' + data.error, 'error');
            document.getElementById('metarInfo').innerHTML = '';
            metarData = null;
        } else {
            metarData = data;
            document.getElementById('metarInfo').innerHTML = `
                <p><strong>Station:</strong> ${data.station}</p>
                <p><strong>Wind:</strong> ${data.speed}kts @ ${data.direction}°</p>
                <p><strong>Time:</strong> ${new Date(data.time).toLocaleString()}</p>
            `;
            showMessage(`METAR data loaded: ${data.speed}kts @ ${data.direction}°`, 'success');
        }
        
        hideLoading();
    } catch (error) {
        showMessage('Error loading METAR data: ' + error.message, 'error');
        hideLoading();
    }
}

// Set storm motion
function setStormMotion() {
    const direction = parseFloat(document.getElementById('stormDirection').value);
    const speed = parseFloat(document.getElementById('stormSpeed').value);
    
    if (isNaN(direction) || isNaN(speed)) {
        showMessage('Please enter both direction and speed for storm motion', 'error');
        return;
    }
    
    if (direction < 0 || direction > 360) {
        showMessage('Direction must be between 0 and 360 degrees', 'error');
        return;
    }
    
    if (speed < 0 || speed > 100) {
        showMessage('Speed must be between 0 and 100 knots', 'error');
        return;
    }
    
    stormMotion = { direction, speed };
    showMessage(`Storm motion set: ${speed}kts @ ${direction}°`, 'success');
}

// Plot hodograph
async function plotHodograph() {
    if (!selectedSite) {
        showMessage('Please select a radar site and load VAD data first', 'error');
        return;
    }
    
    try {
        showLoading('Generating hodograph...');
        
        // Build query parameters
        const params = new URLSearchParams({
            site_id: selectedSite.id,
            show_half_km: document.getElementById('showHalfKm').checked
        });
        
        if (stormMotion) {
            params.append('storm_direction', stormMotion.direction);
            params.append('storm_speed', stormMotion.speed);
        }
        
        if (metarData) {
            params.append('metar_direction', metarData.direction);
            params.append('metar_speed', metarData.speed);
        }
        
        const response = await fetch(`/api/hodograph?${params}`);
        const data = await response.json();
        
        if (data.error) {
            showMessage('Hodograph Error: ' + data.error, 'error');
        } else {
            // Display hodograph image
            document.getElementById('hodographContainer').innerHTML = `
                <img src="data:image/png;base64,${data.image}" alt="Hodograph" />
            `;
            
            // Display parameters if available
            if (data.parameters && Object.keys(data.parameters).length > 0) {
                let parametersHtml = '<h4>Storm Parameters</h4>';
                if (data.parameters.srh_0_5 !== undefined) {
                    parametersHtml += `<p><strong>SRH 0-0.5km:</strong> ${data.parameters.srh_0_5} m²/s²</p>`;
                }
                if (data.parameters.srh_0_1 !== undefined) {
                    parametersHtml += `<p><strong>SRH 0-1km:</strong> ${data.parameters.srh_0_1} m²/s²</p>`;
                }
                if (data.parameters.srh_0_3 !== undefined) {
                    parametersHtml += `<p><strong>SRH 0-3km:</strong> ${data.parameters.srh_0_3} m²/s²</p>`;
                }
                document.getElementById('parametersContainer').innerHTML = parametersHtml;
            }
            
            showMessage('Hodograph generated successfully', 'success');
        }
        
        hideLoading();
    } catch (error) {
        showMessage('Error generating hodograph: ' + error.message, 'error');
        hideLoading();
    }
}

// Reset application
async function resetApplication() {
    try {
        showLoading('Resetting application...');
        
        // Reset API data
        await fetch('/api/reset');
        
        // Reset UI
        selectedSite = null;
        metarData = null;
        stormMotion = null;
        
        document.getElementById('siteInfo').innerHTML = '<p>Click on a radar site on the map to select it</p>';
        document.getElementById('metarInfo').innerHTML = '';
        document.getElementById('hodographContainer').innerHTML = '<p>Load VAD data and click "Plot Hodograph" to generate analysis</p>';
        document.getElementById('parametersContainer').innerHTML = '';
        
        document.getElementById('loadVadBtn').disabled = true;
        document.getElementById('plotHodographBtn').disabled = true;
        
        document.getElementById('metarStation').value = '';
        document.getElementById('stormDirection').value = '';
        document.getElementById('stormSpeed').value = '';
        
        // Clear METAR markers
        metarMarkers.forEach(marker => map.removeLayer(marker));
        metarMarkers = [];
        
        // Reset map view
        map.setView([39.8283, -98.5795], 4);
        
        hideLoading();
        showMessage('Application reset successfully', 'success');
        
    } catch (error) {
        showMessage('Error resetting application: ' + error.message, 'error');
        hideLoading();
    }
}

// Utility functions for UI feedback
function showMessage(message, type = 'info') {
    const messagesContainer = document.getElementById('statusMessages');
    const messageDiv = document.createElement('div');
    messageDiv.className = `status-message status-${type}`;
    messageDiv.textContent = message;
    
    messagesContainer.appendChild(messageDiv);
    
    // Auto-remove after 5 seconds
    setTimeout(() => {
        if (messageDiv.parentNode) {
            messageDiv.parentNode.removeChild(messageDiv);
        }
    }, 5000);
}

function showLoading(text = 'Loading...') {
    document.getElementById('loadingText').textContent = text;
    document.getElementById('loadingOverlay').classList.add('active');
}

function hideLoading() {
    document.getElementById('loadingOverlay').classList.remove('active');
}