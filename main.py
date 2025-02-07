import streamlit as st
import numpy as np
from datetime import datetime
import matplotlib.pyplot as plt
from hodograph_plotter import HodographPlotter
from data_processor import WindProfile
from radar_sites import get_sorted_sites, get_site_by_id
import io

def main():
    st.title("Hodograph Analysis Tool")
    st.sidebar.header("Data Source")

    # Initialize session state for wind profile
    if 'wind_profile' not in st.session_state:
        st.session_state.wind_profile = WindProfile()

    # Radar site selection
    sites = get_sorted_sites()
    site_options = [f"{site.id} - {site.name}" for site in sites]
    selected_site = st.sidebar.selectbox(
        "Select Radar Site",
        site_options,
        format_func=lambda x: x
    )

    # Extract site ID from selection
    site_id = selected_site.split(" - ")[0] if selected_site else None

    # Fetch data button
    if st.sidebar.button("Fetch Latest Data"):
        if site_id:
            with st.spinner(f'Fetching latest data from {site_id}...'):
                try:
                    from vad_reader import download_vad
                    vad = download_vad(site_id, cache_path="temp_data")

                    if vad:
                        st.session_state.wind_profile.heights = vad['altitude']
                        st.session_state.wind_profile.speeds = vad['wind_spd']
                        st.session_state.wind_profile.directions = vad['wind_dir']
                        st.session_state.wind_profile.times = [vad['time']] * len(vad['altitude'])
                        st.success(f"Successfully loaded data from {site_id}")
                    else:
                        st.error("Could not fetch radar data")
                except Exception as e:
                    st.error(f"Error fetching data: {str(e)}")

    # Display current data
    if len(st.session_state.wind_profile.heights) > 0:
        st.subheader("Current Observations")

        # Create data table
        data = {
            "Height (m)": st.session_state.wind_profile.heights,
            "Speed (kts)": st.session_state.wind_profile.speeds,
            "Direction (°)": st.session_state.wind_profile.directions
        }
        st.dataframe(data)

        # Plot controls
        st.subheader("Plot Controls")
        col1, col2 = st.columns(2)
        with col1:
            max_speed = st.slider("Maximum Speed (knots)", 
                                min_value=30, 
                                max_value=100, 
                                value=60, 
                                step=10)
        with col2:
            height_colors = st.checkbox("Color code by height", value=True)

        # Create hodograph plot
        plotter = HodographPlotter()
        plotter.setup_plot(max_speed=max_speed)
        plotter.plot_profile(st.session_state.wind_profile, height_colors=height_colors)

        # Convert plot to Streamlit
        buf = io.BytesIO()
        plotter.get_plot()[0].savefig(buf, format='png', bbox_inches='tight')
        st.image(buf)

        # Clear data button
        if st.button("Clear Data"):
            st.session_state.wind_profile.clear_data()
            st.experimental_rerun()

    else:
        st.info("Select a radar site and click 'Fetch Latest Data' to generate a hodograph.")

if __name__ == "__main__":
    main()