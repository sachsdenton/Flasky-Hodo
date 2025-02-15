import streamlit.components.v1 as components
import streamlit as st
import pandas as pd
import folium
from streamlit_folium import folium_static

def load_metar_sites():
    """Load METAR sites from CSV file"""
    df = pd.read_csv('attached_assets/METAR Sites US.csv')
    # Clean up column names and drop empty columns
    df.columns = df.columns.str.strip()
    df = df.dropna(axis=1, how='all')
    # Ensure required columns exist
    required_columns = ['ID', 'STATE', 'NAME', 'LAT', 'LON']
    if not all(col in df.columns for col in required_columns):
        st.error("METAR CSV file is missing required columns")
        return pd.DataFrame()
    return df

def create_map_component():
    """Create a folium map with METAR sites"""
    # Initialize session state for selected site if not exists
    if 'selected_site' not in st.session_state:
        st.session_state.selected_site = None

    # Load METAR sites data
    sites_df = load_metar_sites()

    if sites_df.empty:
        st.error("Could not load METAR sites data")
        return None

    # Create a base map centered on US
    m = folium.Map(location=[39.8283, -98.5795], zoom_start=4)

    # Add METAR sites as markers
    for _, row in sites_df.iterrows():
        site_id = row['ID']
        state = row['STATE']
        name = row['NAME']
        lat = float(row['LAT'])
        lon = float(row['LON'])

        # Create popup content
        popup_content = f"""
        <div style='width:200px'>
            <b>Station:</b> {site_id}<br>
            <b>Name:</b> {name}<br>
            <b>State:</b> {state}<br>
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