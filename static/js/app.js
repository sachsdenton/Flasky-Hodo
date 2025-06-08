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
let vadDataLoaded = false;
let currentTab = 'map';

// Initialize the application
document.addEventListener('DOMContentLoaded', function() {
    initializeMap();
    loadRadarSites();
    setupEventListeners();
    setupTabNavigation();
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
    vadDataLoaded = false;
    
    // Update UI
    document.getElementById('siteInfo').innerHTML = `
        <p><strong>Site:</strong> ${site.id}</p>
        <p><strong>Location:</strong> ${site.name}</p>
        <p><strong>Coordinates:</strong> ${site.lat.toFixed(3)}, ${site.lon.toFixed(3)}</p>
        <p><strong>Elevation:</strong> ${site.elevation.toFixed(0)} ft</p>
    `;
    
    document.getElementById('plotHodographBtn').disabled = true;
    
    // Center map on selected site
    map.setView([site.lat, site.lon], 8);
    
    // Load nearby METAR sites
    loadNearbyMetarSites(site);
    
    // Automatically load VAD data
    loadVadDataAutomatically(site);
    
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
    
    // Plot hodograph button (now handles everything)
    document.getElementById('plotHodographBtn').addEventListener('click', generateCompleteAnalysis);
    
    // Show warnings checkbox
    document.getElementById('showWarnings').addEventListener('change', function() {
        if (this.checked) {
            loadWarnings();
        } else {
            warningLayers.forEach(layer => map.removeLayer(layer));
            warningLayers = [];
        }
    });
}

// Setup tab navigation
function setupTabNavigation() {
    const tabButtons = document.querySelectorAll('.tab-btn');
    
    tabButtons.forEach(button => {
        button.addEventListener('click', function() {
            if (this.disabled) return;
            
            const targetTab = this.getAttribute('data-tab');
            switchTab(targetTab);
        });
    });
}

// Switch between tabs
function switchTab(tabName) {
    // Update tab buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');
    
    // Update tab content
    document.querySelectorAll('.tab-pane').forEach(pane => {
        pane.classList.remove('active');
    });
    
    if (tabName === 'map') {
        document.getElementById('mapTab').classList.add('active');
        // Refresh map size when switching back to map tab
        setTimeout(() => {
            if (map) map.invalidateSize();
        }, 300);
    } else if (tabName === 'hodograph') {
        document.getElementById('hodographPane').classList.add('active');
    }
    
    currentTab = tabName;
}

// Automatically load VAD data when site is selected
async function loadVadDataAutomatically(site) {
    try {
        document.getElementById('vadStatus').innerHTML = '<p style="color: #3498db;">Loading VAD data...</p>';
        
        const response = await fetch(`/api/vad-data/${site.id}`);
        const data = await response.json();
        
        if (data.error) {
            document.getElementById('vadStatus').innerHTML = `<p style="color: #e74c3c;">VAD Error: ${data.error}</p>`;
            vadDataLoaded = false;
        } else {
            document.getElementById('vadStatus').innerHTML = `<p style="color: #27ae60;">VAD data loaded: ${data.data_points} points</p>`;
            vadDataLoaded = true;
            document.getElementById('plotHodographBtn').disabled = false;
            showMessage(`VAD data loaded for ${site.id}: ${data.data_points} points`, 'success');
        }
        
    } catch (error) {
        document.getElementById('vadStatus').innerHTML = `<p style="color: #e74c3c;">Error loading VAD data</p>`;
        vadDataLoaded = false;
        showMessage('Error loading VAD data: ' + error.message, 'error');
    }
}





// Generate complete analysis (VAD + METAR + Storm Motion + Hodograph)
async function generateCompleteAnalysis() {
    if (!selectedSite) {
        showMessage('Please select a radar site first', 'error');
        return;
    }
    
    try {
        showLoading('Loading VAD data and generating analysis...');
        
        // Step 1: Load VAD data
        const vadResponse = await fetch(`/api/vad-data/${selectedSite.id}`);
        const vadData = await vadResponse.json();
        
        if (vadData.error) {
            showMessage('VAD Error: ' + vadData.error, 'error');
            hideLoading();
            return;
        }
        
        showMessage(`VAD data loaded: ${vadData.data_points} points`, 'info');
        
        // Step 2: Load METAR data if station provided
        let metarInfo = '';
        const metarStation = document.getElementById('metarStation').value.trim().toUpperCase();
        if (metarStation) {
            try {
                const metarResponse = await fetch(`/api/metar/${metarStation}`);
                const metarResult = await metarResponse.json();
                
                if (!metarResult.error) {
                    metarData = metarResult;
                    metarInfo = `METAR: ${metarResult.speed}kts @ ${metarResult.direction}°`;
                    showMessage(`METAR data loaded: ${metarResult.speed}kts @ ${metarResult.direction}°`, 'info');
                }
            } catch (error) {
                console.log('METAR data not available or invalid station');
            }
        }
        
        // Step 3: Get storm motion if provided
        let stormInfo = '';
        const stormDirection = parseFloat(document.getElementById('stormDirection').value);
        const stormSpeed = parseFloat(document.getElementById('stormSpeed').value);
        
        if (!isNaN(stormDirection) && !isNaN(stormSpeed) && 
            stormDirection >= 0 && stormDirection <= 360 && 
            stormSpeed >= 0 && stormSpeed <= 100) {
            stormMotion = { direction: stormDirection, speed: stormSpeed };
            stormInfo = `Storm Motion: ${stormSpeed}kts @ ${stormDirection}°`;
        }
        
        showLoading('Generating hodograph...');
        
        // Step 4: Generate hodograph
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
        
        const hodographResponse = await fetch(`/api/hodograph?${params}`);
        const hodographData = await hodographResponse.json();
        
        if (hodographData.error) {
            showMessage('Hodograph Error: ' + hodographData.error, 'error');
        } else {
            // Display hodograph image in the new tab
            document.getElementById('hodographDisplay').innerHTML = `
                <img src="data:image/png;base64,${hodographData.image}" alt="Hodograph" />
            `;
            
            // Display parameters if available
            if (hodographData.parameters && Object.keys(hodographData.parameters).length > 0) {
                let parametersHtml = '<h4>Storm Parameters</h4>';
                
                // Storm Relative Helicity
                if (hodographData.parameters.srh_0_5 !== null && hodographData.parameters.srh_0_5 !== undefined) {
                    parametersHtml += `<p><span>SRH 0-0.5km:</span><span>${hodographData.parameters.srh_0_5} m²/s²</span></p>`;
                }
                if (hodographData.parameters.srh_0_1 !== null && hodographData.parameters.srh_0_1 !== undefined) {
                    parametersHtml += `<p><span>SRH 0-1km:</span><span>${hodographData.parameters.srh_0_1} m²/s²</span></p>`;
                }
                if (hodographData.parameters.srh_0_3 !== null && hodographData.parameters.srh_0_3 !== undefined) {
                    parametersHtml += `<p><span>SRH 0-3km:</span><span>${hodographData.parameters.srh_0_3} m²/s²</span></p>`;
                }
                
                // Wind Shear Magnitude
                parametersHtml += '<h4>Wind Shear</h4>';
                if (hodographData.parameters.shear_1km !== null && hodographData.parameters.shear_1km !== undefined) {
                    parametersHtml += `<p><span>0-1km Shear:</span><span>${hodographData.parameters.shear_1km} kt</span></p>`;
                }
                if (hodographData.parameters.shear_3km !== null && hodographData.parameters.shear_3km !== undefined) {
                    parametersHtml += `<p><span>0-3km Shear:</span><span>${hodographData.parameters.shear_3km} kt</span></p>`;
                }
                if (hodographData.parameters.shear_6km !== null && hodographData.parameters.shear_6km !== undefined) {
                    parametersHtml += `<p><span>0-6km Shear:</span><span>${hodographData.parameters.shear_6km} kt</span></p>`;
                }
                
                // Shear Depth and Magnitude (effective bulk shear)
                if (hodographData.parameters.shear_depth !== null && hodographData.parameters.shear_depth !== undefined) {
                    parametersHtml += `<p><span>Shear Depth:</span><span>${hodographData.parameters.shear_depth} m</span></p>`;
                }
                if (hodographData.parameters.shear_magnitude !== null && hodographData.parameters.shear_magnitude !== undefined) {
                    parametersHtml += `<p><span>Effective Shear:</span><span>${hodographData.parameters.shear_magnitude} kt</span></p>`;
                }
                
                // Critical Angle
                if (hodographData.parameters.critical_angle !== null && hodographData.parameters.critical_angle !== undefined) {
                    parametersHtml += '<h4>Critical Angle</h4>';
                    parametersHtml += `<p><span>Surface-Storm-Radar:</span><span>${hodographData.parameters.critical_angle}°</span></p>`;
                }
                
                // Bunkers Storm Motion
                if (hodographData.parameters.bunkers) {
                    parametersHtml += '<h4>Bunkers Storm Motion</h4>';
                    if (hodographData.parameters.bunkers.right_mover) {
                        const rm = hodographData.parameters.bunkers.right_mover;
                        parametersHtml += `<p><span>Right Mover:</span><span>${Math.round(rm.direction)}° at ${Math.round(rm.speed)} kt</span></p>`;
                    }
                    if (hodographData.parameters.bunkers.left_mover) {
                        const lm = hodographData.parameters.bunkers.left_mover;
                        parametersHtml += `<p><span>Left Mover:</span><span>${Math.round(lm.direction)}° at ${Math.round(lm.speed)} kt</span></p>`;
                    }
                }
                
                document.getElementById('parametersDisplay').innerHTML = parametersHtml;
            }
            
            // Update analysis details in header
            let analysisDetailsHtml = `<strong>Site:</strong> ${selectedSite.id} - ${selectedSite.name}`;
            if (metarInfo) analysisDetailsHtml += ` | ${metarInfo}`;
            if (stormInfo) analysisDetailsHtml += ` | ${stormInfo}`;
            document.getElementById('analysisDetails').innerHTML = analysisDetailsHtml;
            
            // Enable and switch to hodograph tab
            document.getElementById('hodographTab').disabled = false;
            switchTab('hodograph');
            
            showMessage('Complete hodograph analysis generated successfully', 'success');
        }
        
        hideLoading();
    } catch (error) {
        showMessage('Error generating analysis: ' + error.message, 'error');
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
        document.getElementById('vadStatus').innerHTML = '';
        document.getElementById('analysisDetails').innerHTML = '';
        document.getElementById('hodographDisplay').innerHTML = '<p>Generate hodograph analysis to view results</p>';
        document.getElementById('parametersDisplay').innerHTML = '';
        
        document.getElementById('plotHodographBtn').disabled = true;
        document.getElementById('hodographTab').disabled = true;
        
        // Reset to map tab
        switchTab('map');
        
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