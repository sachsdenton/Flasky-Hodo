import streamlit.components.v1 as components
import streamlit as st
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

def create_map_component(radar_site=None):
    """Create a folium map with METAR sites"""
    # Initialize session state for selected site if not exists
    if 'selected_site' not in st.session_state:
        st.session_state.selected_site = None

    # Load METAR sites data
    sites_df = load_metar_sites()

    if sites_df.empty:
        st.error("Could not load METAR sites data")
        return None

    # If radar site is selected, filter METAR sites within 120nmi
    if radar_site:
        radar_lat = radar_site['latitude']
        radar_lon = radar_site['longitude']

        # Calculate distances and filter sites
        sites_df['distance'] = sites_df.apply(
            lambda row: calculate_distance(
                radar_lat, radar_lon,
                row['Latitude'], row['Longitude']
            ),
            axis=1
        )
        sites_df = sites_df[sites_df['distance'] <= 120]

        # Center map on radar site
        map_center = [radar_lat, radar_lon]
        zoom_start = 8
    else:
        # Default US-centered view
        map_center = [39.8283, -98.5795]
        zoom_start = 4

    # Create the base map
    m = folium.Map(location=map_center, zoom_start=zoom_start)

    # Add radar site marker if selected
    if radar_site:
        folium.CircleMarker(
            location=[radar_lat, radar_lon],
            radius=8,
            color='blue',
            fill=True,
            popup=f"Radar: {radar_site['id']}",
        ).add_to(m)

        # Add 120nmi range circle
        folium.Circle(
            location=[radar_lat, radar_lon],
            radius=222240,  # 120nmi in meters
            color='blue',
            fill=False,
            weight=1,
        ).add_to(m)

    # Add METAR sites as markers
    for _, row in sites_df.iterrows():
        site_id = row['ID']
        name = row['Name']
        lat = float(row['Latitude'])
        lon = float(row['Longitude'])

        # Create popup content
        popup_content = f"""
        <div style='width:200px'>
            <b>Station:</b> {site_id}<br>
            <b>Name:</b> {name}<br>
            <button onclick="parent.postMessage(
                {{type: 'site_selected', siteId: '{site_id}'}},
                '*'
            )">Select Site</button>
        </div>
        """

        folium.Marker(
            location=[lat, lon],
            popup=folium.Popup(popup_content, max_width=300),
            icon=folium.Icon(color='red', icon='info-sign')
        ).add_to(m)

    # Display the map
    folium_static(m)

    # Handle site selection
    components_value = handle_site_selection()
    if components_value and components_value != st.session_state.selected_site:
        st.session_state.selected_site = components_value
        return components_value

    return st.session_state.selected_site

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