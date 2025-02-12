import streamlit as st
import numpy as np
from datetime import datetime
import matplotlib.pyplot as plt
import plotly.graph_objects as go
from hodograph_plotter import HodographPlotter
from data_processor import WindProfile
from radar_sites import get_sorted_sites, get_site_by_id
from utils import calculate_wind_components
from metar_utils import get_metar
import io
import time
import os

def create_plotly_hodograph(wind_profile, site_id=None, site_name=None, valid_time=None):
    speeds = wind_profile.speeds
    if not hasattr(speeds, '__len__') or len(speeds) == 0:
        max_speed = 100
    else:
        max_speed = float(np.max(speeds))
        max_speed = int(np.ceil(max_speed / 10.0)) * 10

    u_comp = []
    v_comp = []
    for speed, direction in zip(wind_profile.speeds, wind_profile.directions):
        u, v = calculate_wind_components(speed, direction)
        u_comp.append(u)
        v_comp.append(v)

    hover_text = [
        f'Height: {h*1000:.0f}m / {h*1000*3.28084:.0f}ft<br>'
        f'Speed: {s:.0f}kts<br>'
        f'Direction: {d:.0f}°'
        for h, s, d in zip(wind_profile.heights, wind_profile.speeds, wind_profile.directions)
    ]

    fig = go.Figure()

    for speed in range(10, max_speed + 1, 10):
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

    fig.add_trace(go.Scatter(
        x=u_comp,
        y=v_comp,
        mode='lines+markers',
        line=dict(color='blue', width=2),
        marker=dict(
            color=wind_profile.heights,
            colorscale='Viridis',
            size=8,
            showscale=False
        ),
        text=hover_text,
        hoverinfo='text',
        name='Wind Profile'
    ))

    fig.update_layout(
        xaxis=dict(
            title='U-component (knots)',
            range=[-max_speed, max_speed],
            zeroline=False,
            showgrid=False,
            scaleanchor='y',
            scaleratio=1,
            constrain='domain'
        ),
        yaxis=dict(
            title='V-component (knots)',
            range=[-max_speed, max_speed],
            zeroline=False,
            showgrid=False,
            scaleanchor='x',
            scaleratio=1,
            constrain='domain'
        ),
        showlegend=False,
        hovermode='closest',
        width=600,
        height=600,
        autosize=False,
        plot_bgcolor='white'
    )

    fig.add_shape(
        type="line",
        x0=-max_speed, x1=max_speed,
        y0=0, y1=0,
        line=dict(color="black", width=2),
        layer='below'
    )
    fig.add_shape(
        type="line",
        x0=0, x1=0,
        y0=-max_speed, y1=max_speed,
        line=dict(color="black", width=2),
        layer='below'
    )

    annotations = [
        dict(x=0, y=-max_speed-2, text="N", showarrow=False),
        dict(x=-max_speed-2, y=0, text="E", showarrow=False),
        dict(x=0, y=max_speed+2, text="S", showarrow=False),
        dict(x=max_speed+2, y=0, text="W", showarrow=False)
    ]
    fig.update_layout(annotations=annotations)

    return fig

def main():
    os.makedirs("temp_data", exist_ok=True)

    st.title("Hodograph Analysis Tool")
    st.sidebar.header("Data Source")

    if 'wind_profile' not in st.session_state:
        st.session_state.wind_profile = WindProfile()
    if 'last_update_time' not in st.session_state:
        st.session_state.last_update_time = None
    if 'metar_data' not in st.session_state:
        st.session_state.metar_data = None

    auto_refresh = st.sidebar.checkbox("Enable Auto-refresh", value=True)
    if auto_refresh:
        refresh_interval = st.sidebar.number_input(
            "Refresh Interval (seconds)",
            min_value=10,
            max_value=300,
            value=120,
            step=5
        )

        if st.session_state.last_update_time:
            time_since_last = (datetime.now() - st.session_state.last_update_time).total_seconds()
            time_until_next = max(0, refresh_interval - time_since_last)
            progress = 1 - (time_until_next / refresh_interval)
            st.sidebar.progress(float(progress), f"Next update in {int(time_until_next)}s")

        if st.session_state.last_update_time:
            st.sidebar.text(f"Last update: {st.session_state.last_update_time.strftime('%H:%M:%S')}")

    sites = get_sorted_sites()
    site_options = ["Select a site..."] + [f"{site.id} - {site.name}" for site in sites]
    selected_site = st.sidebar.selectbox(
        "Select Radar Site",
        site_options,
        format_func=lambda x: x
    )

    site_id = None
    if selected_site and selected_site != "Select a site...":
        site_id = selected_site.split(" - ")[0]

    current_time = datetime.now()
    should_refresh = (
        auto_refresh and 
        site_id and  
        (st.session_state.last_update_time is None or 
         (current_time - st.session_state.last_update_time).total_seconds() >= refresh_interval)
    ) if auto_refresh else False

    fetch_clicked = st.sidebar.button("Fetch Latest Data")

    st.sidebar.header("METAR Data")
    metar_station = st.sidebar.text_input(
        "METAR Station ID (4-letter ICAO)",
        help="Enter a 4-letter ICAO station identifier (e.g., KBOS, KJFK)",
        max_chars=4
    ).strip().upper()

    if metar_station:
        metar_fetch = st.sidebar.button("Fetch METAR Data")
        if metar_fetch:
            with st.spinner(f'Fetching METAR data from {metar_station}...'):
                wind_dir, wind_speed, error = get_metar(metar_station)
                if error:
                    st.sidebar.error(f"METAR Error: {error}")
                    st.session_state.metar_data = None
                else:
                    st.session_state.metar_data = {
                        'station': metar_station,
                        'direction': wind_dir,
                        'speed': wind_speed
                    }
                    st.sidebar.success(f"METAR data loaded: {wind_speed}kts @ {wind_dir}°")


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

    if hasattr(st.session_state.wind_profile.speeds, '__len__') and len(st.session_state.wind_profile.speeds) > 0:
        st.subheader("Wind Profile Visualization")

        col1, col2, col3 = st.columns(3)
        with col1:
            plot_type = st.radio("Plot Type", ["Standard", "Analyst"], key="plot_type")
        with col2:
            height_colors = st.checkbox("Color code by height", value=True)
        with col3:
            show_metar = st.checkbox("Show METAR data", value=True)

        plt.close('all')

        if plot_type == "Standard":
            plotter = HodographPlotter()
            site = get_site_by_id(site_id) if site_id else None
            valid_time = st.session_state.wind_profile.times[0] if st.session_state.wind_profile.times else None

            speeds = st.session_state.wind_profile.speeds
            plotter.setup_plot(
                site_id=site_id,
                site_name=site.name if site else None,
                valid_time=valid_time
            )
            plotter.plot_profile(st.session_state.wind_profile, height_colors=height_colors)

            if show_metar and st.session_state.metar_data:
                metar = st.session_state.metar_data
                u, v = calculate_wind_components(metar['speed'], metar['direction'])
                fig, ax = plotter.get_plot()
                ax.scatter([u], [v], c='red', marker='*', s=150, label=f"METAR {metar['station']}")
                ax.legend()

            buf = io.BytesIO()
            fig, ax = plotter.get_plot()
            fig.savefig(buf, format='png', bbox_inches='tight')
            buf.seek(0)
            st.image(buf)
            plt.close(fig)
        else:
            site = get_site_by_id(site_id) if site_id else None
            valid_time = st.session_state.wind_profile.times[0] if st.session_state.wind_profile.times else None

            fig = create_plotly_hodograph(
                st.session_state.wind_profile,
                site_id=site_id,
                site_name=site.name if site else None,
                valid_time=valid_time
            )

            if show_metar and st.session_state.metar_data:
                metar = st.session_state.metar_data
                u, v = calculate_wind_components(metar['speed'], metar['direction'])
                fig.add_trace(go.Scatter(
                    x=[u],
                    y=[v],
                    mode='markers',
                    marker=dict(
                        symbol='star',
                        size=15,
                        color='red',
                    ),
                    name=f"METAR {metar['station']}",
                    hoverinfo='text',
                    text=f"METAR {metar['station']}<br>Speed: {metar['speed']}kts<br>Direction: {metar['direction']}°"
                ))

            st.plotly_chart(fig, use_container_width=True)

        st.subheader("Current Observations")

        METERS_TO_FEET = 3.28084
        KM_TO_METERS = 1000
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

    if (auto_refresh and site_id and 
        st.session_state.last_update_time and 
        (datetime.now() - st.session_state.last_update_time).total_seconds() >= refresh_interval):
        time.sleep(0.1)
        st.rerun()

if __name__ == "__main__":
    main()