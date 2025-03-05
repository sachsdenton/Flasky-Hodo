import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import folium
from streamlit_folium import folium_static
from math import radians, sin, cos, sqrt, atan2
from radar_sites import get_sorted_sites
from mrms_handler import MRMSHandler
from warning_utils import fetch_active_warnings, get_warning_color, get_warning_popup_content

def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculate distance between two points in nautical miles using geopy"""
    from geopy.distance import distance
    # Convert from nautical miles to km and back for consistency
    dist_nm = distance((lat1, lon1), (lat2, lon2)).nautical
    return dist_nm

def load_metar_sites():
    """Load METAR sites from CSV file"""
    try:
        df = pd.read_csv('attached_assets/metar_sites.csv')
        df.columns = df.columns.str.strip()
        df = df.dropna(axis=1, how='all')
        required_columns = ['ID', 'Name', 'Latitude', 'Longitude']
        if not all(col in df.columns for col in required_columns):
            st.error("METAR CSV file is missing required columns")
            return pd.DataFrame()
        return df
    except Exception as e:
        st.error(f"Error loading METAR sites: {str(e)}")
        return pd.DataFrame()

def create_map(center_lat=39.8283, center_lon=-98.5795, zoom_start=4, show_mrms=False, show_warnings=False):
    """Create a folium map with radar sites"""
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=zoom_start,
        width='100%'
    )

    # Add base tile layer with reduced max zoom for better performance
    folium.TileLayer(
        'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
        attr='© OpenStreetMap contributors',
        name='OpenStreetMap',
        max_zoom=10
    ).add_to(m)

    if show_mrms:
        mrms = MRMSHandler()
        mrms_metadata = mrms.get_reflectivity_metadata()
        folium.TileLayer(
            mrms.get_tile_url(),
            attr=mrms_metadata['attribution'],
            name='MRMS Reflectivity',
            opacity=0.7,
            overlay=True
        ).add_to(m)

    # Add radar site markers with simplified style
    sites = get_sorted_sites()
    for site in sites:
        # Simple circle marker instead of custom icon
        folium.CircleMarker(
            location=[site.lat, site.lon],
            radius=4,
            color='red',
            fill=True,
            popup=f"{site.id} - {site.name}",
            tooltip=f"{site.id}",
            weight=2
        ).add_to(m)
    
    # Add warnings if enabled
    if show_warnings:
        m = add_warnings_to_map(m, show_warnings)

    # Add layer control if MRMS or warnings are enabled
    if show_mrms or show_warnings:
        folium.LayerControl().add_to(m)

    return m

def add_warnings_to_map(m, show_warnings=True):
    """Add active severe thunderstorm and tornado warnings to the map.
    
    Args:
        m: The folium map object
        show_warnings: Whether to show warnings on the map
        
    Returns:
        The map with warnings added
    """
    if not show_warnings:
        return m
        
    # Create a FeatureGroup for warnings so they can be toggled
    warnings_group = folium.FeatureGroup(name="Warnings")
    
    # Fetch active warnings
    warnings = fetch_active_warnings()
    
    # Add warnings to the map
    for warning in warnings:
        # Check if we have valid geometry
        if not warning.get("geometry") or warning["geometry"].get("type") != "Polygon":
            continue
            
        # Get coordinates of the polygon
        coordinates = warning["geometry"].get("coordinates", [])
        if not coordinates or not coordinates[0]:
            continue
            
        # Create a polygon for the warning area
        coords = coordinates[0]
        # Folium expects [lat, lon] but GeoJSON provides [lon, lat]
        polygon_coords = [[point[1], point[0]] for point in coords]
        
        # Add polygon to map
        warning_color = get_warning_color(warning["event"])
        popup_content = get_warning_popup_content(warning)
        
        folium.Polygon(
            locations=polygon_coords,
            color=warning_color,
            fill=True,
            fill_color=warning_color,
            fill_opacity=0.3,
            weight=2,
            popup=folium.Popup(popup_content, max_width=300),
            tooltip=warning["event"]
        ).add_to(warnings_group)
    
    # Add the warnings group to the map
    warnings_group.add_to(m)
    
    # Add layer control if it doesn't exist already
    if not any(isinstance(child, folium.LayerControl) for child in m._children.values()):
        folium.LayerControl().add_to(m)
    
    return m

def handle_site_selection():
    """Handle the site selection from the map"""
    m = create_map()
    folium_static(m)