import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import folium
from streamlit_folium import folium_static
from math import radians, sin, cos, sqrt, atan2
from mrms_handler import MRMSHandler
from radar_sites import get_sorted_sites

def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculate distance between two points in nautical miles"""
    R = 3440.065  # Earth's radius in nautical miles
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    distance = R * c
    return distance

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

def create_map(center_lat=39.8283, center_lon=-98.5795, zoom_start=4, show_mrms=True):
    """Create a folium map with optional MRMS overlay and radar sites"""
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=zoom_start,
        width='100%'
    )

    # Add base tile layer
    folium.TileLayer(
        'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
        attr='© OpenStreetMap contributors',
        name='OpenStreetMap'
    ).add_to(m)

    if show_mrms:
        mrms = MRMSHandler()
        mrms_metadata = mrms.get_reflectivity_metadata()

        # Add MRMS reflectivity layer
        folium.TileLayer(
            mrms.get_tile_url(),
            attr=mrms_metadata['attribution'],
            name='MRMS Reflectivity',
            opacity=mrms_metadata['opacity'],
            overlay=True
        ).add_to(m)

    # Add radar site markers
    sites = get_sorted_sites()
    for site in sites:
        popup_content = f"""
        <div>
            <b>{site.id}</b><br>
            {site.name}
        </div>
        """

        # Create a custom icon using the PNG image
        icon = folium.CustomIcon(
            icon_image='attached_assets/pngegg.png',
            icon_size=(15, 20),  # Reduced size from (30, 40)
            icon_anchor=(7, 20),  # Adjusted anchor point for new size
            popup_anchor=(0, -20)  # Adjusted popup position for new size
        )

        marker = folium.Marker(
            location=[site.lat, site.lon],
            popup=folium.Popup(popup_content, max_width=300),
            tooltip=f"{site.id} - {site.name}",
            icon=icon
        )
        marker._name = f"site_{site.id}"
        marker.add_to(m)

    # Add layer control
    folium.LayerControl().add_to(m)

    return m

def handle_site_selection():
    """Handle the site selection from the map"""
    from streamlit.components.v1 import html

    m = create_map() # Use the new map creation function
    folium_static(m)

    html(
        """
        <script>
        window.addEventListener('message', function(e) {
            if (e.data.type === 'site_selected') {
                window.Streamlit.setComponentValue(e.data.siteId);
            }
        });
        </script>
        """,
        height=0,
    )