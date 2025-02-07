import streamlit as st
import numpy as np
from datetime import datetime
import matplotlib.pyplot as plt
from hodograph_plotter import HodographPlotter
from data_processor import WindProfile
from radar_sites import get_sorted_sites, get_site_by_id
import io
import time

def main():
    st.title("Hodograph Analysis Tool")
    st.sidebar.header("Data Source")

    # Initialize session state for wind profile and auto-refresh
    if 'wind_profile' not in st.session_state:
        st.session_state.wind_profile = WindProfile()
    if 'last_update_time' not in st.session_state:
        st.session_state.last_update_time = None
    if 'last_data_timestamp' not in st.session_state:
        st.session_state.last_data_timestamp = None

    # Auto-refresh control
    auto_refresh = st.sidebar.checkbox("Enable Auto-refresh", value=True)
    if auto_refresh:
        st.sidebar.text("Updates every 30 seconds")
        # Show last update time if available
        if st.session_state.last_update_time:
            st.sidebar.text(f"Last check: {st.session_state.last_update_time.strftime('%H:%M:%S')}")
        if st.session_state.last_data_timestamp:
            st.sidebar.text(f"Data time: {st.session_state.last_data_timestamp.strftime('%H:%M:%S')}")

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

    # Auto-refresh logic
    current_time = datetime.now()
    should_refresh = (
        auto_refresh and 
        site_id and  # Only refresh if a site is selected
        (st.session_state.last_update_time is None or 
        (current_time - st.session_state.last_update_time).total_seconds() >= 30)
    )

    # Fetch data button or auto-refresh
    fetch_clicked = st.sidebar.button("Fetch Latest Data")

    # Update data and plot if needed
    data_updated = False
    if fetch_clicked or should_refresh:
        if site_id:
            try:
                from vad_reader import download_vad
                # First just check if new data is available
                if fetch_clicked:
                    # If manual refresh, always fetch new data
                    with st.spinner(f'Fetching latest data from {site_id}...'):
                        vad = download_vad(site_id, cache_path="temp_data")
                        if vad:
                            st.session_state.wind_profile.heights = vad['altitude']
                            st.session_state.wind_profile.speeds = vad['wind_spd']
                            st.session_state.wind_profile.directions = vad['wind_dir']
                            st.session_state.wind_profile.times = [vad['time']] * len(vad['altitude'])
                            st.session_state.last_data_timestamp = vad['time']
                            data_updated = True
                            st.success(f"New data loaded from {site_id}")
                else:
                    # For auto-refresh, first check if new data exists
                    vad = download_vad(site_id, cache_path="temp_data", check_only=True)
                    if vad and vad['time'] != st.session_state.last_data_timestamp:
                        # Only if new data exists, fetch the full dataset
                        with st.spinner(f'New data available, updating from {site_id}...'):
                            vad = download_vad(site_id, cache_path="temp_data")
                            if vad:
                                st.session_state.wind_profile.heights = vad['altitude']
                                st.session_state.wind_profile.speeds = vad['wind_spd']
                                st.session_state.wind_profile.directions = vad['wind_dir']
                                st.session_state.wind_profile.times = [vad['time']] * len(vad['altitude'])
                                st.session_state.last_data_timestamp = vad['time']
                                data_updated = True
                                st.success(f"New data loaded from {site_id}")

                st.session_state.last_update_time = current_time

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
            pass
        with col2:
            height_colors = st.checkbox("Color code by height", value=True)

        # Create hodograph plot only if data was updated or it doesn't exist yet
        if 'hodograph_plot' not in st.session_state or data_updated:
            plotter = HodographPlotter()
            # Get site information
            site = get_site_by_id(site_id)
            # Get the time from the profile (first time in the list)
            valid_time = st.session_state.wind_profile.times[0] if st.session_state.wind_profile.times else None

            plotter.setup_plot(
                site_id=site_id,
                site_name=site.name,
                valid_time=valid_time
            )
            plotter.plot_profile(st.session_state.wind_profile, height_colors=height_colors)

            # Convert plot to bytes and store in session state
            buf = io.BytesIO()
            plotter.get_plot()[0].savefig(buf, format='png', bbox_inches='tight')
            st.session_state.hodograph_plot = buf.getvalue()
            plt.close()  # Close the plot to free memory

        # Display the stored plot
        st.image(st.session_state.hodograph_plot)

        # Clear data button
        if st.button("Clear Data"):
            st.session_state.wind_profile.clear_data()
            st.session_state.last_update_time = None
            st.session_state.last_data_timestamp = None
            if 'hodograph_plot' in st.session_state:
                del st.session_state.hodograph_plot
            st.rerun()

    else:
        st.info("Select a radar site and click 'Fetch Latest Data' to generate a hodograph.")

    # Trigger auto-refresh if enabled
    if auto_refresh and site_id:
        time.sleep(0.1)  # Small delay to prevent excessive CPU usage
        st.rerun()  # Use st.rerun() instead of deprecated st.experimental_rerun()

if __name__ == "__main__":
    main()