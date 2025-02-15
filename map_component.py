import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import folium
from streamlit_folium import folium_static
from math import radians, sin, cos, sqrt, atan2


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
        # Clean up column names and drop empty columns
        df.columns = df.columns.str.strip()
        df = df.dropna(axis=1, how='all')
        # Ensure required columns exist
        required_columns = ['ID', 'Name', 'Latitude', 'Longitude']
        if not all(col in df.columns for col in required_columns):
            st.error("METAR CSV file is missing required columns")
            return pd.DataFrame()
        return df
    except Exception as e:
        st.error(f"Error loading METAR sites: {str(e)}")
        return pd.DataFrame()


def handle_site_selection():
    """Handle the site selection from the map"""
    from streamlit.components.v1 import html

    # Create a hidden component to handle the JavaScript event
    html(
        """
        <script>
        window.addEventListener('message', function(e) {
            if (e.data.type === 'site_selected') {
                // Send the site ID to Streamlit
                window.Streamlit.setComponentValue(e.data.siteId);
            }
        });
        </script>
        """,
        height=0,
    )