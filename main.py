import streamlit as st
import numpy as np
from datetime import datetime
import matplotlib.pyplot as plt
import plotly.graph_objects as go
from hodograph_plotter import HodographPlotter
from data_processor import WindProfile
from radar_sites import get_sorted_sites, get_site_by_id
from utils import calculate_wind_components
import io
import time
import os

def create_plotly_hodograph(wind_profile, site_id=None, site_name=None, valid_time=None):
    # Define max_speed at the start since it's used throughout the function
    max_speed = 100  # Fixed maximum speed at 100 knots

    # Calculate u and v components
    u_comp = []
    v_comp = []
    for speed, direction in zip(wind_profile.speeds, wind_profile.directions):
        u, v = calculate_wind_components(speed, direction)
        # Negate the components to flip the data to the correct side
        u_comp.append(-u)
        v_comp.append(-v)

    # Create hover text
    hover_text = [
        f'Height: {h*1000:.0f}m / {h*1000*3.28084:.0f}ft<br>'
        f'Speed: {s:.0f}kts<br>'
        f'Direction: {d:.0f}°'
        for h, s, d in zip(wind_profile.heights, wind_profile.speeds, wind_profile.directions)
    ]

    # Create the figure
    fig = go.Figure()

    # Add speed rings
    for speed in range(10, 101, 10):
        circle_points = np.linspace(0, 2*np.pi, 100)
        x = speed * np.cos(circle_points)
        y = speed * np.sin(circle_points)
        fig.add_trace(go.Scatter(
            x=x, y=y,
            mode='lines',
            line=dict(color='rgba(200,200,200,0.5)', width=1),
            showlegend=False,
            hoverinfo='skip'
        ))

    # Add zero lines (axes)
    fig.add_shape(
        type="line",
        x0=-max_speed, x1=max_speed, y0=0, y1=0,
        line=dict(color="black", width=2.5),
        layer='below'
    )
    fig.add_shape(
        type="line",
        x0=0, x1=0, y0=-max_speed, y1=max_speed,
        line=dict(color="black", width=2.5),
        layer='below'
    )

    # Add the wind profile line and points
    fig.add_trace(go.Scatter(
        x=u_comp,
        y=v_comp,
        mode='lines+markers',
        line=dict(color='blue', width=2),
        marker=dict(
            color=wind_profile.heights,
            colorscale='Viridis',
            size=8,
            showscale=True,
            colorbar=dict(title='Height (km)')
        ),
        text=hover_text,
        hoverinfo='text',
        name='Wind Profile'
    ))

    # Configure the layout
    fig.update_layout(
        title=f"{site_id} - {site_name}<br>Valid: {valid_time.strftime('%Y-%m-%d %H:%M UTC')}" if all([site_id, site_name, valid_time]) else None,
        xaxis=dict(
            title='U-component (knots)',
            range=[max_speed, -max_speed],  # Inverted x-axis (East on left)
            zeroline=True,
            gridcolor='lightgray',
            scaleanchor='y',  # Lock aspect ratio
            scaleratio=1,     # Equal scaling
            constrain='domain'  # Maintain aspect ratio when resizing
        ),
        yaxis=dict(
            title='V-component (knots)',
            range=[-max_speed, max_speed],  # Standard y-axis (South on top)
            zeroline=True,
            gridcolor='lightgray',
            scaleanchor='x',
            scaleratio=1,
            constrain='domain'
        ),
        showlegend=False,
        hovermode='closest',
        width=600,   # Fixed width
        height=600,  # Fixed height (equal to width for square plot)
        autosize=False  # Disable autosize to maintain square shape
    )

    # Add cardinal directions in meteorological convention
    annotations = [
        dict(x=0, y=-max_speed-2, text="N", showarrow=False),  # North at bottom
        dict(x=-max_speed-2, y=0, text="E", showarrow=False),  # East on left
        dict(x=0, y=max_speed+2, text="S", showarrow=False),   # South at top
        dict(x=max_speed+2, y=0, text="W", showarrow=False)    # West on right
    ]
    fig.update_layout(annotations=annotations)

    return fig

def main():
    # Create temp_data directory if it doesn't exist
    os.makedirs("temp_data", exist_ok=True)

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

    # Display current data and plot
    if len(st.session_state.wind_profile.heights) > 0:
        st.subheader("Wind Profile Visualization")

        # Plot controls
        col1, col2, col3 = st.columns(3)
        with col1:
            plot_type = st.radio("Plot Type", ["Matplotlib", "Plotly"], key="plot_type")
        with col2:
            height_colors = st.checkbox("Color code by height", value=True)
        with col3:
            pass

        # Clear any existing matplotlib figures
        plt.close('all')

        if plot_type == "Matplotlib":
            # Create hodograph plot (existing matplotlib code)
            plotter = HodographPlotter()
            site = get_site_by_id(site_id) if site_id else None
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
            plt.close(fig)
        else:
            # Create and display Plotly hodograph
            site = get_site_by_id(site_id) if site_id else None
            valid_time = st.session_state.wind_profile.times[0] if st.session_state.wind_profile.times else None

            fig = create_plotly_hodograph(
                st.session_state.wind_profile,
                site_id=site_id,
                site_name=site.name if site else None,
                valid_time=valid_time
            )
            st.plotly_chart(fig, use_container_width=True)

        # Display data table below the plot
        st.subheader("Current Observations")

        # Create data table with both meters and feet
        METERS_TO_FEET = 3.28084
        KM_TO_METERS = 1000  # Convert kilometers to meters
        data = {
            "Height (m / ft)": [
                f"{float(h) * KM_TO_METERS:.0f} m / {(float(h) * KM_TO_METERS * METERS_TO_FEET):.0f} ft" 
                for h in st.session_state.wind_profile.heights
            ],
            "Speed (kts)": [f"{float(s):.0f}" for s in st.session_state.wind_profile.speeds],
            "Direction (°)": [f"{float(d):.0f}" for d in st.session_state.wind_profile.directions]
        }
        st.dataframe(data)

    else:
        st.info("Select a radar site and click 'Fetch Latest Data' to generate a hodograph.")

    # Only trigger auto-refresh if data is stale
    if (auto_refresh and site_id and 
        st.session_state.last_update_time and 
        (datetime.now() - st.session_state.last_update_time).total_seconds() >= refresh_interval):
        time.sleep(0.1)  # Small delay to prevent excessive CPU usage
        st.rerun()

if __name__ == "__main__":
    main()