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

    # Auto-refresh controls
    auto_refresh = st.sidebar.checkbox("Enable Auto-refresh", value=True)
    if auto_refresh:
        refresh_interval = st.sidebar.number_input(
            "Refresh Interval (seconds)",
            min_value=10,
            max_value=300,
            value=120,
            step=5
        )

        # Calculate and display countdown
        if st.session_state.last_update_time:
            time_since_last = (datetime.now() - st.session_state.last_update_time).total_seconds()
            time_until_next = max(0, refresh_interval - time_since_last)
            progress = 1 - (time_until_next / refresh_interval)

            # Display countdown progress bar
            st.sidebar.progress(float(progress), f"Next update in {int(time_until_next)}s")

        # Show last update time if available
        if st.session_state.last_update_time:
            st.sidebar.text(f"Last update: {st.session_state.last_update_time.strftime('%H:%M:%S')}")

    # Radar site selection with empty default
    sites = get_sorted_sites()
    site_options = ["Select a site..."] + [f"{site.id} - {site.name}" for site in sites]
    selected_site = st.sidebar.selectbox(
        "Select Radar Site",
        site_options,
        format_func=lambda x: x
    )

    # Extract site ID from selection, only if a real site is selected
    site_id = None
    if selected_site and selected_site != "Select a site...":
        site_id = selected_site.split(" - ")[0]

    # Auto-refresh logic
    current_time = datetime.now()
    should_refresh = (
        auto_refresh and 
        site_id and  # Only refresh if a site is selected
        (st.session_state.last_update_time is None or 
         (current_time - st.session_state.last_update_time).total_seconds() >= refresh_interval)
    ) if auto_refresh else False

    # Fetch data button or auto-refresh
    fetch_clicked = st.sidebar.button("Fetch Latest Data")

    if fetch_clicked or should_refresh:
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
                        st.session_state.last_update_time = current_time
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
            pass
        with col2:
            height_colors = st.checkbox("Color code by height", value=True)

        # Clear any existing matplotlib figures
        plt.close('all')

        # Create hodograph plot
        plotter = HodographPlotter()
        # Get site information
        site = get_site_by_id(site_id) if site_id else None
        # Get the time from the profile (first time in the list)
        valid_time = st.session_state.wind_profile.times[0] if st.session_state.wind_profile.times else None

        plotter.setup_plot(
            site_id=site_id,
            site_name=site.name if site else None,
            valid_time=valid_time
        )
        plotter.plot_profile(st.session_state.wind_profile, height_colors=height_colors)

        # Convert plot to Streamlit
        buf = io.BytesIO()
        fig, ax = plotter.get_plot()
        fig.savefig(buf, format='png', bbox_inches='tight')
        buf.seek(0)
        st.image(buf)
        plt.close(fig)  # Close the figure after saving

        # Clear data button
        if st.button("Clear Data"):
            st.session_state.wind_profile.clear_data()
            st.session_state.last_update_time = None
            st.rerun()

    else:
        st.info("Select a radar site and click 'Fetch Latest Data' to generate a hodograph.")

    # Trigger auto-refresh if enabled
    if auto_refresh and site_id:
        time.sleep(0.1)  # Small delay to prevent excessive CPU usage
        st.rerun()  # Use st.rerun() instead of deprecated st.experimental_rerun()

if __name__ == "__main__":
    main()