import streamlit as st
import numpy as np
from data_processor import WindProfile
from hodograph_plotter import HodographPlotter
import io
import matplotlib.pyplot as plt
from datetime import datetime

def main():
    st.title("Hodograph Analysis Tool")
    st.sidebar.header("Data Input")

    # Initialize session state
    if 'wind_profile' not in st.session_state:
        st.session_state.wind_profile = WindProfile()

    # Data input method selection
    input_method = st.sidebar.radio(
        "Choose input method",
        ["Manual Entry", "NEXRAD Data Upload"]
    )

    if input_method == "Manual Entry":
        with st.sidebar.form("wind_data_form"):
            st.write("Enter Wind Observation")
            height = st.number_input("Height (meters)", min_value=0.0, step=100.0)
            speed = st.number_input("Wind Speed (knots)", min_value=0.0, max_value=200.0, step=1.0)
            direction = st.number_input("Wind Direction (degrees)", min_value=0.0, max_value=360.0, step=1.0)

            submitted = st.form_submit_button("Add Observation")
            if submitted:
                st.session_state.wind_profile.add_observation(height, speed, direction)
                st.success("Observation added!")

    else:  # NEXRAD Data Upload
        uploaded_file = st.sidebar.file_uploader("Upload NEXRAD Level-II file", type=["gz"])
        if uploaded_file is not None:
            # Save uploaded file temporarily
            with open("temp_nexrad.gz", "wb") as f:
                f.write(uploaded_file.getvalue())

            if st.session_state.wind_profile.load_from_nexrad("temp_nexrad.gz"):
                st.success("Successfully loaded NEXRAD data!")
            else:
                st.error("Error loading NEXRAD data. Please ensure it's a valid Level-II file.")

    # Display current data
    if len(st.session_state.wind_profile.heights) > 0:
        st.subheader("Current Observations")
        data = {
            "Height (m)": st.session_state.wind_profile.heights,
            "Speed (kts)": st.session_state.wind_profile.speeds,
            "Direction (°)": st.session_state.wind_profile.directions,
            "Time": st.session_state.wind_profile.times
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

        # Create and display plot
        plotter = HodographPlotter()
        plotter.setup_plot(max_speed=max_speed)
        plotter.plot_profile(st.session_state.wind_profile, height_colors=height_colors)

        # Convert plot to Streamlit
        buf = io.BytesIO()
        plotter.get_plot()[0].savefig(buf, format='png', bbox_inches='tight')
        st.image(buf)

        # Clear data button
        if st.button("Clear All Data"):
            st.session_state.wind_profile.clear_data()
            st.experimental_rerun()

    else:
        st.info("Add wind observations or upload NEXRAD data to generate the hodograph.")

if __name__ == "__main__":
    main()