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
let interactiveHodograph = null;
let loopController = null;

// Initialize the application
document.addEventListener('DOMContentLoaded', function() {
    initializeMap();
    loadRadarSites();
    setupEventListeners();
    setupTabNavigation();
    loadWarnings();
    setupScrubberKeyboardShortcuts();

    // Set initial tab state based on screen size
    if (window.innerWidth <= 1024) {
        switchMobileTab('controls');
    }
    
    // Handle window resize for responsive layout
    window.addEventListener('resize', handleResize);
});

// Keyboard shortcuts for the VAD loop scrubber:
//   ","  → previous frame
//   "."  → next frame
// Both wrap around at the ends, matching the prev/next button behavior.
function setupScrubberKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
        if (e.key !== ',' && e.key !== '.') return;
        // Don't hijack typing in form fields (e.g. METAR/storm inputs).
        const t = e.target;
        if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' ||
                  t.tagName === 'SELECT' || t.isContentEditable)) {
            return;
        }
        // Ignore modifier-key chords so OS shortcuts (Cmd-., etc.) still work.
        if (e.ctrlKey || e.metaKey || e.altKey) return;

        const ctl = loopController;
        if (!ctl) return;
        const loaded = getLoadedFrames(ctl);
        if (loaded.length < 2) return;

        const cur = loaded.findIndex(f => f.file_id === ctl.currentFileId);
        const baseIdx = cur === -1 ? loaded.length - 1 : cur;
        const delta = e.key === '.' ? 1 : -1;
        applyFrameByLoadedIndex(wrapIndex(baseIdx + delta, loaded.length));
        e.preventDefault();
    });
}

// Handle window resize events
function handleResize() {
    const isMobile = window.innerWidth <= 1024;
    const wasInitializedForMobile = map && map.getContainer().id === 'mobileMap';
    
    // If screen size category changed, reinitialize map
    if (isMobile && !wasInitializedForMobile) {
        // Switching to mobile layout
        if (currentTab === 'map' || currentTab === 'controls') {
            switchMobileTab('controls');
        }
    } else if (!isMobile && wasInitializedForMobile) {
        // Switching to desktop layout - reinitialize map in desktop container
        reinitializeDesktopMap();
    }
    
    // Always invalidate map size after resize
    setTimeout(() => {
        if (map) map.invalidateSize();
    }, 300);
}

// Reinitialize map for desktop layout
function reinitializeDesktopMap() {
    if (map) {
        map.remove();
        map = null;
    }
    
    // Create new map in desktop container
    map = L.map('map').setView([39.8283, -98.5795], 4);
    
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors',
        maxZoom: 10
    }).addTo(map);
    
    // Re-add all existing markers and layers
    if (radarSites.length > 0) {
        addRadarSitesToMap();
    }
    if (selectedSite && metarMarkers.length > 0) {
        loadNearbyMetarSites(selectedSite);
    }
    if (warningLayers.length > 0) {
        loadWarnings();
    }
}

// Initialize mobile map (recreate map instance for mobile container)
function initializeMobileMap() {
    const mobileMapContainer = document.getElementById('mobileMap');
    
    if (mobileMapContainer) {
        // Remove existing map if it exists
        if (map) {
            map.remove();
            map = null;
        }
        
        // Create new map in mobile container
        map = L.map('mobileMap').setView([39.8283, -98.5795], 4);
        
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap contributors',
            maxZoom: 10
        }).addTo(map);
        
        // Re-add all existing markers and layers
        if (radarSites.length > 0) {
            addRadarSitesToMap();
        }
        if (metarMarkers.length > 0) {
            // Re-add METAR markers if they exist
            recreateMetarMarkers();
        }
        if (warningLayers.length > 0) {
            // Re-add warning layers
            recreateWarningLayers();
        }
    }
}

// Recreate METAR markers for mobile map
function recreateMetarMarkers() {
    // Clear existing markers first
    metarMarkers.forEach(marker => {
        try {
            map.removeLayer(marker);
        } catch (e) {
            // Marker might not be on current map instance
        }
    });
    metarMarkers = [];
    
    // If we have a selected site, reload nearby METAR sites
    if (selectedSite) {
        loadNearbyMetarSites(selectedSite);
    }
}

// Recreate warning layers for mobile map
function recreateWarningLayers() {
    // Clear existing warning layers
    warningLayers.forEach(layer => {
        try {
            map.removeLayer(layer);
        } catch (e) {
            // Layer might not be on current map instance
        }
    });
    warningLayers = [];
    
    // Reload warnings
    loadWarnings();
}

// Copy hodograph content to mobile view
function copyHodographToMobile() {
    const desktopDisplay = document.getElementById('hodographDisplay');
    const mobileDisplay = document.getElementById('mobileHodographDisplay');
    const desktopDetails = document.getElementById('analysisDetails');
    const mobileDetails = document.getElementById('mobileAnalysisDetails');
    const desktopParams = document.getElementById('parametersDisplay');
    const mobileParams = document.getElementById('mobileParametersDisplay');
    
    if (desktopDisplay && mobileDisplay) {
        mobileDisplay.innerHTML = desktopDisplay.innerHTML;
    }
    if (desktopDetails && mobileDetails) {
        mobileDetails.innerHTML = desktopDetails.innerHTML;
    }
    if (desktopParams && mobileParams) {
        mobileParams.innerHTML = desktopParams.innerHTML;
    }
}

// Initialize Leaflet map
function initializeMap() {
    // Determine which container to use based on screen size
    const isMobile = window.innerWidth <= 1024;
    const mapContainer = isMobile ? 'mobileMap' : 'map';
    
    // Only initialize if map doesn't exist
    if (!map) {
        map = L.map(mapContainer).setView([39.8283, -98.5795], 4);
        
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap contributors',
            maxZoom: 10
        }).addTo(map);
    }
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

    // Selecting a different site invalidates the previous loop frames.
    teardownLoopController();
    
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
                const event = warning.event || (warning.properties && warning.properties.event) || 'Unknown';
                const headline = warning.headline || (warning.properties && warning.properties.headline) || '';
                const areaDesc = warning.areaDesc || (warning.properties && warning.properties.areaDesc) || '';
                const color = getWarningColor(event);
                
                const layer = L.geoJSON(warning.geometry, {
                    style: {
                        color: color,
                        weight: 2,
                        opacity: 0.8,
                        fillOpacity: 0.3
                    }
                });
                
                layer.bindPopup(`
                    <b>${event}</b><br>
                    <strong>Area:</strong> ${areaDesc}<br>
                    <strong>Headline:</strong> ${headline}
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

    // Analyst mode toggle
    document.getElementById('analystMode').addEventListener('change', function() {
        document.getElementById('analystControls').style.display = this.checked ? 'block' : 'none';
        if (interactiveHodograph && !this.checked) {
            interactiveHodograph = null;
        }
        // Loop frames are mode-specific (canvas vs image), so tear them down.
        teardownLoopController();
    });

    // Analyst feature toggles
    const featureMap = {
        'showSpeedRings': 'speedRings',
        'showHeightMarkers': 'heightMarkers',
        'showSRH': 'srhShading',
        'showShearVector': 'shearVector',
        'showCriticalAngle': 'criticalAngle',
        'showStormMotionMarker': 'stormMotionMarker',
        'showSurfaceWindMarker': 'surfaceWindMarker',
        'showParamText': 'paramText'
    };
    Object.entries(featureMap).forEach(([elemId, featureName]) => {
        document.getElementById(elemId).addEventListener('change', function() {
            if (interactiveHodograph) {
                interactiveHodograph.toggleFeature(featureName, this.checked);
            }
        });
    });
    document.getElementById('showHalfKm').addEventListener('change', function() {
        if (interactiveHodograph) {
            interactiveHodograph.toggleFeature('halfKmMarkers', this.checked);
        }
    });

    document.getElementById('refreshHodographBtn').addEventListener('click', function() {
        if (interactiveHodograph) {
            interactiveHodograph.resetView();
            showMessage('View reset to default', 'info');
        } else {
            generateCompleteAnalysis();
        }
    });
    
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

    // Archives panel refresh button
    const archivesRefreshBtn = document.getElementById('archivesRefreshBtn');
    if (archivesRefreshBtn) {
        archivesRefreshBtn.addEventListener('click', loadArchivesList);
    }
}

// Setup tab navigation
function setupTabNavigation() {
    // Desktop tab navigation
    const tabButtons = document.querySelectorAll('.tab-btn');
    
    tabButtons.forEach(button => {
        button.addEventListener('click', function() {
            if (this.disabled) return;
            
            const targetTab = this.getAttribute('data-tab');
            switchTab(targetTab);
        });
    });
    
    // Mobile tab navigation
    const mobileTabButtons = document.querySelectorAll('.mobile-tab-btn');
    
    mobileTabButtons.forEach(button => {
        button.addEventListener('click', function() {
            if (this.disabled) return;
            
            const targetTab = this.getAttribute('data-tab');
            switchMobileTab(targetTab);
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
    } else if (tabName === 'archives') {
        document.getElementById('archivesPane').classList.add('active');
        loadArchivesList();
    }

    currentTab = tabName;
}

// Switch between mobile tabs
function switchMobileTab(tabName) {
    // Update mobile tab buttons
    document.querySelectorAll('.mobile-tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    document.querySelector(`.mobile-tab-btn[data-tab="${tabName}"]`).classList.add('active');
    
    // Update panel visibility - mobile panels
    document.querySelectorAll('.controls-panel, .mobile-map-panel, .mobile-hodograph-panel').forEach(panel => {
        panel.classList.remove('active');
    });
    
    if (tabName === 'controls') {
        document.getElementById('controlsPanel').classList.add('active');
    } else if (tabName === 'map') {
        document.getElementById('mapPanel').classList.add('active');
        // Initialize mobile map if needed
        initializeMobileMap();
        // Refresh map size when switching to map tab
        setTimeout(() => {
            if (map) map.invalidateSize();
        }, 300);
    } else if (tabName === 'hodograph') {
        document.getElementById('hodographPanel').classList.add('active');
        // Copy hodograph content to mobile view
        copyHodographToMobile();
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
                    metarData.station_id = metarStation; // Add station ID to metarData
                    metarInfo = `METAR: ${metarResult.speed}kts @ ${metarResult.direction}°`;
                    showMessage(`METAR data loaded: ${metarResult.speed}kts @ ${metarResult.direction}°`, 'info');
                }
            } catch (error) {
                console.log('METAR data not available or invalid station');
            }
        }
        
        // Step 3: Get storm motion if provided. Compass directions wrap, so
        // accept any numeric direction and normalize to [0, 360).
        let stormInfo = '';
        const rawStormDirection = parseFloat(document.getElementById('stormDirection').value);
        const stormSpeed = parseFloat(document.getElementById('stormSpeed').value);

        if (!isNaN(rawStormDirection) && !isNaN(stormSpeed) &&
            stormSpeed >= 0 && stormSpeed <= 100) {
            const stormDirection = ((rawStormDirection % 360) + 360) % 360;
            stormMotion = { direction: stormDirection, speed: stormSpeed };
            stormInfo = `Storm Motion: ${stormSpeed}kts @ ${stormDirection}°`;
        } else if (!isNaN(rawStormDirection) || !isNaN(stormSpeed)) {
            showMessage('Storm motion ignored: enter a numeric direction and a speed between 0–100 kt.', 'warning');
        }
        
        showLoading('Generating hodograph...');

        // Stop any in-flight loop from a prior render before starting a new one.
        teardownLoopController();

        const isAnalystMode = document.getElementById('analystMode').checked;

        if (isAnalystMode) {
            // Fetch raw data and render interactively on canvas
            const dataParams = new URLSearchParams({ site_id: selectedSite.id });
            if (stormMotion) {
                dataParams.append('storm_direction', stormMotion.direction);
                dataParams.append('storm_speed', stormMotion.speed);
            }
            if (metarData) {
                dataParams.append('metar_direction', metarData.direction);
                dataParams.append('metar_speed', metarData.speed);
                dataParams.append('metar_station', metarData.station_id);
            }
            
            const dataResponse = await fetch(`/api/wind-profile-data?${dataParams}`);
            const profileData = await dataResponse.json();
            
            if (profileData.error) {
                showMessage('Data Error: ' + profileData.error, 'error');
            } else {
                const display = document.getElementById('hodographDisplay');
                display.innerHTML = '<div id="interactiveHodographContainer"></div>';
                
                const container = document.getElementById('interactiveHodographContainer');
                interactiveHodograph = new InteractiveHodograph(container);
                
                interactiveHodograph.features.halfKmMarkers = document.getElementById('showHalfKm').checked;
                interactiveHodograph.features.speedRings = document.getElementById('showSpeedRings').checked;
                interactiveHodograph.features.heightMarkers = document.getElementById('showHeightMarkers').checked;
                interactiveHodograph.features.srhShading = document.getElementById('showSRH').checked;
                interactiveHodograph.features.shearVector = document.getElementById('showShearVector').checked;
                interactiveHodograph.features.criticalAngle = document.getElementById('showCriticalAngle').checked;
                interactiveHodograph.features.stormMotionMarker = document.getElementById('showStormMotionMarker').checked;
                interactiveHodograph.features.surfaceWindMarker = document.getElementById('showSurfaceWindMarker').checked;
                interactiveHodograph.features.paramText = document.getElementById('showParamText').checked;

                if (stormMotion) interactiveHodograph.setStormMotion(stormMotion.direction, stormMotion.speed);
                if (metarData) interactiveHodograph.setMetar(metarData.direction, metarData.speed, metarData.station_id);
                
                interactiveHodograph.setData(profileData);
                
                document.getElementById('parametersDisplay').innerHTML = '<p><em>Scroll to zoom, drag to pan, hover points for details. Use the toggles to show/hide features.</em></p>';
                
                let analysisDetailsHtml = `<strong>Site:</strong> ${selectedSite.id} - ${selectedSite.name} <span style="color:#3498db;font-weight:bold;">[Interactive Mode]</span>`;
                if (metarInfo) analysisDetailsHtml += ` | ${metarInfo}`;
                if (stormInfo) analysisDetailsHtml += ` | ${stormInfo}`;
                document.getElementById('analysisDetails').innerHTML = analysisDetailsHtml;
                
                document.getElementById('hodographTab').disabled = false;
                document.getElementById('mobileHodographTab').disabled = false;
                document.getElementById('refreshHodographBtn').disabled = false;
                
                if (window.innerWidth <= 1024) {
                    switchMobileTab('hodograph');
                } else {
                    switchTab('hodograph');
                }
                
                showMessage('Interactive hodograph generated — scroll to zoom, drag to pan', 'success');

                startLoopController({
                    mode: 'analyst',
                    siteId: selectedSite.id,
                    stormMotion: stormMotion,
                    metarData: metarData,
                    showHalfKm: document.getElementById('showHalfKm').checked
                });
            }
        } else {
            // Standard mode: server-rendered static image
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
                params.append('metar_station', metarData.station_id);
            }
            
            const hodographResponse = await fetch(`/api/hodograph?${params}`);
            const hodographData = await hodographResponse.json();
            
            if (hodographData.error) {
                showMessage('Hodograph Error: ' + hodographData.error, 'error');
            } else {
                interactiveHodograph = null;
                document.getElementById('hodographDisplay').innerHTML = `
                    <img src="data:image/png;base64,${hodographData.image}" alt="Hodograph" />
                `;
                
                document.getElementById('parametersDisplay').innerHTML = '<p><em>Meteorological parameters are displayed directly on the hodograph plot above.</em></p>';
                
                let analysisDetailsHtml = `<strong>Site:</strong> ${selectedSite.id} - ${selectedSite.name}`;
                if (metarInfo) analysisDetailsHtml += ` | ${metarInfo}`;
                if (stormInfo) analysisDetailsHtml += ` | ${stormInfo}`;
                document.getElementById('analysisDetails').innerHTML = analysisDetailsHtml;
                
                document.getElementById('hodographTab').disabled = false;
                document.getElementById('mobileHodographTab').disabled = false;
                document.getElementById('refreshHodographBtn').disabled = false;
                
                if (window.innerWidth <= 1024) {
                    switchMobileTab('hodograph');
                } else {
                    switchTab('hodograph');
                }
                
                showMessage('Complete hodograph analysis generated successfully', 'success');

                startLoopController({
                    mode: 'standard',
                    siteId: selectedSite.id,
                    stormMotion: stormMotion,
                    metarData: metarData,
                    showHalfKm: document.getElementById('showHalfKm').checked
                });
            }
        }

        hideLoading();
    } catch (error) {
        showMessage('Error generating analysis: ' + error.message, 'error');
        hideLoading();
    }
}

// =====================================================================
// VAD loop / scrubber controller
// =====================================================================

const SCRUBBER_IDS = ['hodographScrubber', 'mobileHodographScrubber'];

function teardownLoopController() {
    if (loopController) {
        if (loopController.playTimerId) {
            clearInterval(loopController.playTimerId);
        }
        loopController.aborted = true;
    }
    loopController = null;
    SCRUBBER_IDS.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.style.display = 'none';
    });
}

async function startLoopController(opts) {
    // Each invocation gets its own state object so async work from a previous
    // generation is harmless once a new one starts.
    const ctl = {
        mode: opts.mode,
        siteId: opts.siteId,
        stormMotion: opts.stormMotion,
        metarData: opts.metarData,
        showHalfKm: !!opts.showHalfKm,
        // 'live' loops fetch from the upstream NEXRAD listing; 'archive'
        // loops replay a previously-saved snapshot from local storage.
        source: opts.source || 'live',
        archiveId: opts.archiveId || null,
        // All frames from the manifest (oldest first). `payload` is filled
        // in as prefetches resolve; failed frames keep payload === null.
        frames: [],
        currentFileId: null, // the currently displayed frame's file_id
        playTimerId: null,
        playing: false,
        aborted: false,
        prefetchDone: false
    };
    loopController = ctl;

    // Phase 1: only show the loading indicator. Controls stay hidden until
    // we have at least 2 successfully loaded frames.
    showLoadingIndicator(ctl.source === 'archive'
        ? 'Loading archived frames…'
        : 'Loading recent frames…');

    const historyUrl = ctl.source === 'archive'
        ? `/api/archive-history/${opts.siteId}/${ctl.archiveId}`
        : `/api/vad-history/${opts.siteId}?count=7`;

    let manifest;
    try {
        const resp = await fetch(historyUrl);
        manifest = await resp.json();
    } catch (e) {
        if (ctl.aborted) return;
        showLoadingIndicator(ctl.source === 'archive'
            ? 'Archive unavailable'
            : 'Recent frames unavailable');
        return;
    }
    if (ctl.aborted || loopController !== ctl) return;
    if (!manifest || !Array.isArray(manifest.frames) || manifest.frames.length === 0) {
        showLoadingIndicator('No recent frames available');
        return;
    }

    // Convention: oldest at slider=0, newest at slider=N-1.
    ctl.frames = manifest.frames.slice().reverse().map(f => ({
        file_id: f.file_id,
        valid_time: f.valid_time,
        payload: null
    }));
    // The rendered hodograph should land on the newest scan in the manifest.
    const newestFrame = ctl.frames[ctl.frames.length - 1];
    ctl.currentFileId = newestFrame.file_id;
    // The initial main render came from a separate code path and may not
    // exactly match this manifest's newest scan. We swap the display over to
    // the manifest's newest payload as soon as it arrives so the slider's
    // "latest" position and the rendered hodograph stay in sync.
    ctl.displaySyncedToLoop = false;

    // Prefetch frame payloads in parallel
    const frameUrl = (fileId) => buildFramePayloadUrl(ctl, fileId);
    const tasks = ctl.frames.map(frame => fetch(frameUrl(frame.file_id))
        .then(r => r.ok ? r.json() : null)
        .then(payload => {
            if (ctl.aborted || loopController !== ctl) return;
            if (payload && !payload.error) {
                frame.payload = payload;
                if (frame === newestFrame && !ctl.displaySyncedToLoop) {
                    // Snap the display to the newest frame as soon as it
                    // loads. This both updates the visible hodograph and
                    // re-renders the scrubber.
                    ctl.displaySyncedToLoop = true;
                    const loaded = getLoadedFrames(ctl);
                    const idx = loaded.findIndex(f => f.file_id === frame.file_id);
                    if (idx !== -1) {
                        applyFrameByLoadedIndex(idx);
                        return;
                    }
                }
                // Re-evaluate visibility: as soon as we cross the 2-loaded
                // threshold, the scrubber pops in.
                renderScrubber();
            }
        })
        .catch(() => {})
    );

    Promise.allSettled(tasks).then(() => {
        if (ctl.aborted || loopController !== ctl) return;
        ctl.prefetchDone = true;
        const loaded = getLoadedFrames(ctl);
        if (loaded.length < 2) {
            showLoadingIndicator(loaded.length === 0
                ? 'No additional frames available'
                : 'Only one frame available');
            return;
        }
        // If the newest frame failed but other frames loaded, fall back to
        // the newest frame we *do* have so the user still lands on the most
        // recent available scan.
        if (!ctl.displaySyncedToLoop) {
            ctl.displaySyncedToLoop = true;
            applyFrameByLoadedIndex(loaded.length - 1);
        } else {
            renderScrubber();
        }
    });
}

function getLoadedFrames(ctl) {
    if (!ctl) return [];
    return ctl.frames.filter(f => f.payload);
}

function buildFramePayloadUrl(ctl, fileId) {
    const params = new URLSearchParams();
    if (ctl.stormMotion) {
        params.append('storm_direction', ctl.stormMotion.direction);
        params.append('storm_speed', ctl.stormMotion.speed);
    }
    if (ctl.metarData) {
        params.append('metar_direction', ctl.metarData.direction);
        params.append('metar_speed', ctl.metarData.speed);
        if (ctl.metarData.station_id) {
            params.append('metar_station', ctl.metarData.station_id);
        }
    }
    const isArchive = ctl.source === 'archive';
    if (ctl.mode === 'standard') {
        params.append('show_half_km', ctl.showHalfKm);
        return isArchive
            ? `/api/archive/hodograph-frame/${ctl.siteId}/${ctl.archiveId}/${fileId}?${params.toString()}`
            : `/api/hodograph-frame/${ctl.siteId}/${fileId}?${params.toString()}`;
    }
    return isArchive
        ? `/api/archive/wind-profile-frame/${ctl.siteId}/${ctl.archiveId}/${fileId}?${params.toString()}`
        : `/api/wind-profile-frame/${ctl.siteId}/${fileId}?${params.toString()}`;
}

function showLoadingIndicator(text) {
    // Phase-1 visibility: only the status row is shown; controls and
    // timestamp stay hidden until ≥2 frames are loaded.
    SCRUBBER_IDS.forEach(id => {
        const root = document.getElementById(id);
        if (!root) return;
        root.style.display = 'flex';
        const status = root.querySelector('.scrubber-status');
        if (status) {
            status.textContent = text;
            status.style.display = '';
        }
        const controls = root.querySelector('.scrubber-controls');
        if (controls) controls.style.display = 'none';
        const ts = root.querySelector('.scrubber-timestamp');
        if (ts) ts.style.display = 'none';
    });
}

function renderScrubber() {
    const ctl = loopController;
    if (!ctl) return;
    const loaded = getLoadedFrames(ctl);
    const total = loaded.length;

    if (total < 2) {
        // Not enough loaded frames yet — keep showing the loading row.
        if (ctl.prefetchDone && total === 0) {
            showLoadingIndicator('No additional frames available');
        } else if (ctl.prefetchDone && total === 1) {
            showLoadingIndicator('Only one frame available');
        } else {
            showLoadingIndicator('Loading recent frames…');
        }
        return;
    }

    // Resolve the slider index from the currently displayed file_id; fall
    // back to the newest loaded frame if the current frame failed to load.
    let idx = loaded.findIndex(f => f.file_id === ctl.currentFileId);
    if (idx === -1) {
        idx = loaded.length - 1;
        ctl.currentFileId = loaded[idx].file_id;
    }
    const current = loaded[idx];

    SCRUBBER_IDS.forEach(id => {
        const root = document.getElementById(id);
        if (!root) return;
        root.style.display = 'flex';

        const status = root.querySelector('.scrubber-status');
        if (status) {
            status.textContent = `${total} frames loaded`;
            status.style.display = '';
        }
        const controls = root.querySelector('.scrubber-controls');
        if (controls) controls.style.display = '';
        const tsEl = root.querySelector('.scrubber-timestamp');
        if (tsEl) tsEl.style.display = '';

        const slider = root.querySelector('.scrubber-slider');
        if (slider) {
            slider.max = Math.max(0, total - 1);
            if (parseInt(slider.value, 10) !== idx) slider.value = idx;
            slider.disabled = false;
            if (!slider.dataset.bound) {
                slider.addEventListener('input', onSliderInput);
                slider.dataset.bound = '1';
            }
        }

        root.querySelectorAll('[data-scrubber-action]').forEach(btn => {
            const action = btn.getAttribute('data-scrubber-action');
            btn.disabled = false;
            if (action === 'play') {
                btn.textContent = ctl.playing ? '❚❚' : '▶';
                btn.classList.toggle('is-playing', ctl.playing);
            }
            if (action === 'save') {
                // Archive replays are already saved — hide the button so
                // users don't pile up duplicate entries.
                btn.style.display = ctl.source === 'archive' ? 'none' : '';
            }
            if (!btn.dataset.bound) {
                btn.addEventListener('click', onScrubberButton);
                btn.dataset.bound = '1';
            }
        });

        const counter = root.querySelector('.scrubber-counter');
        if (counter) counter.textContent = `${idx + 1} of ${total}`;

        if (tsEl) tsEl.textContent = current ? `Valid: ${current.valid_time}` : '–';
    });
}

function onSliderInput(e) {
    const ctl = loopController;
    if (!ctl) return;
    const idx = parseInt(e.target.value, 10);
    applyFrameByLoadedIndex(idx);
}

function onScrubberButton(e) {
    const ctl = loopController;
    if (!ctl) return;
    const action = e.currentTarget.getAttribute('data-scrubber-action');

    // Save is the one action that doesn't require ≥2 loaded frames; it
    // captures whatever's currently in memory.
    if (action === 'save') {
        saveCurrentLoop();
        return;
    }

    const loaded = getLoadedFrames(ctl);
    if (loaded.length < 2) return;
    const cur = loaded.findIndex(f => f.file_id === ctl.currentFileId);
    const baseIdx = cur === -1 ? loaded.length - 1 : cur;
    if (action === 'prev') {
        applyFrameByLoadedIndex(wrapIndex(baseIdx - 1, loaded.length));
    } else if (action === 'next') {
        applyFrameByLoadedIndex(wrapIndex(baseIdx + 1, loaded.length));
    } else if (action === 'play') {
        togglePlay();
    }
}

function wrapIndex(i, n) {
    if (!n) return 0;
    return ((i % n) + n) % n;
}

function togglePlay() {
    const ctl = loopController;
    if (!ctl) return;
    const loaded = getLoadedFrames(ctl);
    if (loaded.length < 2) return;
    if (ctl.playing) {
        ctl.playing = false;
        if (ctl.playTimerId) clearInterval(ctl.playTimerId);
        ctl.playTimerId = null;
    } else {
        ctl.playing = true;
        ctl.playTimerId = setInterval(() => {
            if (!loopController) return;
            const lf = getLoadedFrames(loopController);
            if (lf.length < 2) return;
            const cur = lf.findIndex(f => f.file_id === loopController.currentFileId);
            const baseIdx = cur === -1 ? lf.length - 1 : cur;
            applyFrameByLoadedIndex(wrapIndex(baseIdx + 1, lf.length));
        }, 600);
    }
    renderScrubber();
}

function applyFrameByLoadedIndex(idx) {
    const ctl = loopController;
    if (!ctl) return;
    const loaded = getLoadedFrames(ctl);
    if (idx < 0 || idx >= loaded.length) return;
    const frame = loaded[idx];
    ctl.currentFileId = frame.file_id;
    if (ctl.mode === 'analyst') {
        if (interactiveHodograph) {
            interactiveHodograph.setData(frame.payload, true);
        }
    } else {
        const payload = frame.payload;
        ['hodographDisplay', 'mobileHodographDisplay'].forEach(id => {
            const container = document.getElementById(id);
            if (!container) return;
            let img = container.querySelector('img');
            if (!img) {
                container.innerHTML = '';
                img = document.createElement('img');
                img.alt = 'Hodograph';
                container.appendChild(img);
            }
            img.src = `data:image/png;base64,${payload.image}`;
        });
    }
    renderScrubber();
}

// =====================================================================
// Archives — save, list, load, delete
// =====================================================================

async function saveCurrentLoop() {
    const ctl = loopController;
    if (!ctl || ctl.source === 'archive') return;
    // Save every frame whose payload successfully prefetched. The server
    // skips any whose raw VAD file is no longer in the on-disk cache.
    const fileIds = getLoadedFrames(ctl).map(f => f.file_id);
    if (fileIds.length === 0) {
        showMessage('No loaded frames to save yet.', 'warning');
        return;
    }

    const body = {
        site_id: ctl.siteId,
        file_ids: fileIds,
        metar: ctl.metarData ? {
            station: ctl.metarData.station_id || null,
            direction: ctl.metarData.direction,
            speed: ctl.metarData.speed,
        } : null,
        storm_motion: ctl.stormMotion ? {
            direction: ctl.stormMotion.direction,
            speed: ctl.stormMotion.speed,
        } : null,
    };

    // Disable the save buttons during the round-trip so double-clicks
    // can't queue duplicate POSTs.
    const saveBtns = document.querySelectorAll('[data-scrubber-action="save"]');
    saveBtns.forEach(b => { b.disabled = true; });
    try {
        const resp = await fetch('/api/archive/save', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body),
        });
        const data = await resp.json();
        if (!resp.ok || data.error) {
            showMessage('Save failed: ' + (data.error || resp.statusText), 'error');
            return;
        }
        const id = data.manifest && data.manifest.archive_id;
        const count = data.manifest && data.manifest.frames ? data.manifest.frames.length : fileIds.length;
        showMessage(`Saved ${count} frame${count === 1 ? '' : 's'} as ${id}`, 'success');
    } catch (err) {
        showMessage('Save failed: ' + err.message, 'error');
    } finally {
        saveBtns.forEach(b => { b.disabled = false; });
    }
}

async function loadArchivesList() {
    const tree = document.getElementById('archivesTree');
    if (!tree) return;
    tree.innerHTML = '<p class="archives-empty">Loading archives…</p>';
    try {
        const resp = await fetch('/api/archive/list');
        const data = await resp.json();
        if (!resp.ok || data.error) {
            tree.innerHTML = `<p class="archives-empty">Error: ${data.error || resp.statusText}</p>`;
            return;
        }
        renderArchivesTree(data.sites || []);
    } catch (err) {
        tree.innerHTML = `<p class="archives-empty">Error: ${err.message}</p>`;
    }
}

function renderArchivesTree(sites) {
    const tree = document.getElementById('archivesTree');
    if (!tree) return;
    if (!sites.length) {
        tree.innerHTML = '<p class="archives-empty">No saved loops yet. Generate a hodograph and click 💾 Save to archive one.</p>';
        return;
    }

    tree.innerHTML = '';
    for (const site of sites) {
        const siteEl = document.createElement('div');
        siteEl.className = 'archive-site';

        const header = document.createElement('div');
        header.className = 'archive-site-header';
        header.innerHTML = `
            <span>${escapeHtml(site.site_id)}</span>
            <span class="archive-site-count">${site.archives.length} loop${site.archives.length === 1 ? '' : 's'}</span>
        `;
        header.addEventListener('click', () => siteEl.classList.toggle('is-collapsed'));
        siteEl.appendChild(header);

        const body = document.createElement('div');
        body.className = 'archive-site-body';
        for (const archive of site.archives) {
            body.appendChild(renderArchiveEntry(site.site_id, archive));
        }
        siteEl.appendChild(body);
        tree.appendChild(siteEl);
    }
}

function renderArchiveEntry(siteId, manifest) {
    const entry = document.createElement('div');
    entry.className = 'archive-entry';

    const main = document.createElement('div');
    main.className = 'archive-entry-main';

    const title = document.createElement('div');
    title.className = 'archive-entry-title';
    title.textContent = manifest.archive_id;
    main.appendChild(title);

    const meta = document.createElement('div');
    meta.className = 'archive-entry-meta';
    const parts = [
        `${manifest.frames ? manifest.frames.length : 0} frames`,
        `valid ${manifest.newest_valid_time || '—'}`,
    ];
    if (manifest.metar && manifest.metar.station) {
        parts.push(`METAR ${escapeHtml(manifest.metar.station)} ${manifest.metar.speed}@${manifest.metar.direction}`);
    }
    if (manifest.storm_motion) {
        parts.push(`Storm ${manifest.storm_motion.speed}@${manifest.storm_motion.direction}`);
    }
    meta.innerHTML = parts.map(p => `<span>${p}</span>`).join('');
    main.appendChild(meta);

    entry.appendChild(main);

    const actions = document.createElement('div');
    actions.className = 'archive-entry-actions';

    const loadBtn = document.createElement('button');
    loadBtn.type = 'button';
    loadBtn.className = 'archive-load-btn';
    loadBtn.textContent = 'Load';
    loadBtn.addEventListener('click', () => loadArchiveById(siteId, manifest.archive_id));
    actions.appendChild(loadBtn);

    const delBtn = document.createElement('button');
    delBtn.type = 'button';
    delBtn.className = 'archive-delete-btn';
    delBtn.textContent = 'Delete';
    delBtn.addEventListener('click', async () => {
        if (!confirm(`Delete archive ${manifest.archive_id}?`)) return;
        try {
            const resp = await fetch(`/api/archive/${siteId}/${manifest.archive_id}`, {method: 'DELETE'});
            const data = await resp.json();
            if (!resp.ok || data.error) {
                showMessage('Delete failed: ' + (data.error || resp.statusText), 'error');
                return;
            }
            showMessage('Archive deleted.', 'success');
            loadArchivesList();
        } catch (err) {
            showMessage('Delete failed: ' + err.message, 'error');
        }
    });
    actions.appendChild(delBtn);

    entry.appendChild(actions);
    return entry;
}

async function loadArchiveById(siteId, archiveId) {
    showLoading('Loading archive…');
    try {
        const resp = await fetch('/api/archive/load', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({site_id: siteId, archive_id: archiveId}),
        });
        const data = await resp.json();
        if (!resp.ok || data.error) {
            hideLoading();
            showMessage('Load failed: ' + (data.error || resp.statusText), 'error');
            return;
        }

        // Populate the input fields so the user can see what was archived.
        const site = await ensureSiteSelected(siteId, data.site_name);
        document.getElementById('metarStation').value =
            (data.metar && data.metar.station) ? data.metar.station : '';
        if (data.storm_motion) {
            document.getElementById('stormDirection').value = data.storm_motion.direction;
            document.getElementById('stormSpeed').value = data.storm_motion.speed;
            stormMotion = {
                direction: data.storm_motion.direction,
                speed: data.storm_motion.speed,
            };
        } else {
            document.getElementById('stormDirection').value = '';
            document.getElementById('stormSpeed').value = '';
            stormMotion = null;
        }
        metarData = data.metar ? {
            station_id: data.metar.station || null,
            direction: data.metar.direction,
            speed: data.metar.speed,
        } : null;

        // Tear down any existing loop and start an archive-mode one.
        teardownLoopController();
        interactiveHodograph = null;

        // Switch to the hodograph tab and prepare the display container.
        document.getElementById('hodographTab').disabled = false;
        document.getElementById('mobileHodographTab').disabled = false;
        switchTab('hodograph');
        switchMobileTab('hodograph');

        const isAnalyst = document.getElementById('analystMode').checked;
        const display = document.getElementById('hodographDisplay');
        if (isAnalyst) {
            display.innerHTML = '<div id="interactiveHodographContainer"></div>';
            const container = document.getElementById('interactiveHodographContainer');
            interactiveHodograph = new InteractiveHodograph(container);
            interactiveHodograph.features.halfKmMarkers = document.getElementById('showHalfKm').checked;
            interactiveHodograph.features.speedRings = document.getElementById('showSpeedRings').checked;
            interactiveHodograph.features.heightMarkers = document.getElementById('showHeightMarkers').checked;
            interactiveHodograph.features.srhShading = document.getElementById('showSRH').checked;
            interactiveHodograph.features.shearVector = document.getElementById('showShearVector').checked;
            interactiveHodograph.features.criticalAngle = document.getElementById('showCriticalAngle').checked;
            interactiveHodograph.features.stormMotionMarker = document.getElementById('showStormMotionMarker').checked;
            interactiveHodograph.features.surfaceWindMarker = document.getElementById('showSurfaceWindMarker').checked;
            interactiveHodograph.features.paramText = document.getElementById('showParamText').checked;
            if (stormMotion) interactiveHodograph.setStormMotion(stormMotion.direction, stormMotion.speed);
            if (metarData) interactiveHodograph.setMetar(metarData.direction, metarData.speed);
        } else {
            display.innerHTML = '<p>Loading archived hodograph…</p>';
        }

        startLoopController({
            mode: isAnalyst ? 'analyst' : 'standard',
            source: 'archive',
            archiveId: archiveId,
            siteId: siteId,
            stormMotion: stormMotion,
            metarData: metarData,
            showHalfKm: document.getElementById('showHalfKm').checked,
        });

        hideLoading();
        showMessage(`Loaded archive ${archiveId}`, 'success');
    } catch (err) {
        hideLoading();
        showMessage('Load failed: ' + err.message, 'error');
    }
}

// Make sure the sidebar reflects the archived site even if the user never
// clicked it on the map. Returns the (possibly newly-set) selectedSite.
async function ensureSiteSelected(siteId, siteName) {
    if (selectedSite && selectedSite.id === siteId) return selectedSite;
    selectedSite = {id: siteId, name: siteName || siteId};
    const info = document.getElementById('siteInfo');
    if (info) {
        info.innerHTML = `<p><strong>${escapeHtml(siteId)}</strong>${siteName ? ' — ' + escapeHtml(siteName) : ''}</p>`;
    }
    document.getElementById('plotHodographBtn').disabled = false;
    return selectedSite;
}

function escapeHtml(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, ch => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[ch]));
}

// Reset application
async function resetApplication() {
    try {
        showLoading('Resetting application...');

        // Tear down loop scrubber and any in-flight prefetches first.
        teardownLoopController();
        interactiveHodograph = null;

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
        document.getElementById('mobileHodographTab').disabled = true;
        
        // Reset to map tab (or controls on mobile)
        if (window.innerWidth <= 1024) {
            switchMobileTab('controls');
        } else {
            switchTab('map');
        }
        
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