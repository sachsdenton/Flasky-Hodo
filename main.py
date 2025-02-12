import streamlit as st
import numpy as np
from datetime import datetime
import matplotlib.pyplot as plt
import plotly.graph_objects as go
from hodograph_plotter import HodographPlotter
from data_processor import WindProfile
from radar_sites import get_sorted_sites, get_site_by_id
from utils import calculate_wind_components, calculate_skoff_angle
from metar_utils import get_metar
import io
import time
import os
from typing import Tuple
from params import compute_bunkers

def calculate_vector_angle(u1: float, v1: float, u2: float, v2: float) -> float:
    """Calculate the angle between two vectors."""
    dot_product = u1 * u2 + v1 * v2
    mag1 = np.sqrt(u1**2 + v1**2)
    mag2 = np.sqrt(u2**2 + v2**2)

    if mag1 == 0 or mag2 == 0:
        return 0.0

    cos_angle = np.clip(dot_product / (mag1 * mag2), -1.0, 1.0)
    angle_rad = np.arccos(cos_angle)
    return np.rad2deg(angle_rad)

def calculate_shear_depth(surface_u: float, surface_v: float, profile: WindProfile) -> Tuple[float, list]:
    """Calculate shear depth based on points within 5 degrees of the surface-to-lowest vector."""
    # Get the lowest radar point
    radar_u, radar_v = calculate_wind_components(profile.speeds[0], profile.directions[0])

    # Calculate reference vector (from surface to lowest radar point)
    ref_u = radar_u - surface_u
    ref_v = radar_v - surface_v

    # Find points within 5 degrees of reference vector
    aligned_heights = []
    for i in range(len(profile.speeds)):
        point_u, point_v = calculate_wind_components(profile.speeds[i], profile.directions[i])
        vector_u = point_u - surface_u
        vector_v = point_v - surface_v

        angle = calculate_vector_angle(ref_u, ref_v, vector_u, vector_v)
        if angle <= 5.0:  # Within 5 degrees
            aligned_heights.append(profile.heights[i])

    # Return the maximum height (shear depth) and list of aligned heights
    return max(aligned_heights) if aligned_heights else 0.0, aligned_heights

def extend_line_to_edge(surface_u: float, surface_v: float, radar_u: float, radar_v: float, max_speed: float) -> Tuple[float, float]:
    """Calculate where a line through two points intersects the hodograph edge."""
    # Calculate vector from surface to radar point
    vector_u = radar_u - surface_u
    vector_v = radar_v - surface_v

    # Normalize the vector
    magnitude = np.sqrt(vector_u**2 + vector_v**2)
    if magnitude == 0:
        return radar_u, radar_v

    unit_u = vector_u / magnitude
    unit_v = vector_v / magnitude

    # Scale to reach edge (max_speed)
    scale = max_speed * 1.4  # Scale beyond the max speed rings for visual clarity
    end_u = surface_u + unit_u * scale
    end_v = surface_v + unit_v * scale

    return end_u, end_v

def calculate_skoff_angle_points(surface_u, surface_v, storm_u, storm_v, radar_u, radar_v):
    """Calculate the Skoff Critical Angle between three points."""
    # Calculate vectors
    v1 = [storm_u - surface_u, storm_v - surface_v]  # Surface to Storm vector
    v2 = [radar_u - surface_u, radar_v - surface_v]  # Surface to Radar vector

    # Calculate dot product
    dot_product = v1[0]*v2[0] + v1[1]*v2[1]

    # Calculate magnitudes
    mag1 = np.sqrt(v1[0]**2 + v1[1]**2)
    mag2 = np.sqrt(v2[0]**2 + v2[1]**2)

    if mag1 == 0 or mag2 == 0:
        return 0.0

    # Calculate angle
    cos_angle = np.clip(dot_product / (mag1 * mag2), -1.0, 1.0)
    angle_rad = np.arccos(cos_angle)
    return np.rad2deg(angle_rad)

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

    # Add title with site and time information
    title = []
    if site_id and site_name:
        title.append(f"{site_id} - {site_name}")
    if valid_time:
        title.append(f"Valid: {valid_time.strftime('%Y-%m-%d %H:%M UTC')}")
    if st.session_state.metar_data:
        metar = st.session_state.metar_data
        title.append(f"METAR: {metar['station']}")

    if title:
        fig.update_layout(title={
            'text': '<br>'.join(title),
            'y': 0.95,
            'x': 0.5,
            'xanchor': 'center',
            'yanchor': 'top'
        })

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
        showlegend=True,
        hovermode='closest',
        width=600,
        height=600,
        autosize=False,
        plot_bgcolor='white'
    )

    # Add base axes
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

    # Add cardinal direction annotations
    annotations = [
        dict(x=0, y=-max_speed-2, text="N", showarrow=False),
        dict(x=-max_speed-2, y=0, text="E", showarrow=False),
        dict(x=0, y=max_speed+2, text="S", showarrow=False),
        dict(x=max_speed+2, y=0, text="W", showarrow=False)
    ]
    fig.update_layout(annotations=annotations)

    # Add Bunkers movers if we have enough data
    data = {
        'wind_dir': wind_profile.directions,
        'wind_spd': wind_profile.speeds,
        'altitude': wind_profile.heights
    }

    try:
        bunkers_right, bunkers_left, mean_wind = compute_bunkers(data)

        # Add Bunkers right mover
        right_u, right_v = calculate_wind_components(bunkers_right[1], bunkers_right[0])
        fig.add_trace(go.Scatter(
            x=[right_u],
            y=[right_v],
            mode='markers',
            marker=dict(
                symbol='diamond',
                size=12,
                color='purple',
            ),
            name='RM',
            showlegend=False,
            hovertext=f'Right Mover<br>Speed: {bunkers_right[1]:.0f}kts<br>Direction: {bunkers_right[0]:.0f}°'
        ))

        # Add Bunkers left mover
        left_u, left_v = calculate_wind_components(bunkers_left[1], bunkers_left[0])
        fig.add_trace(go.Scatter(
            x=[left_u],
            y=[left_v],
            mode='markers',
            marker=dict(
                symbol='diamond',
                size=12,
                color='blue',
            ),
            name='LM',
            showlegend=False,
            hovertext=f'Left Mover<br>Speed: {bunkers_left[1]:.0f}kts<br>Direction: {bunkers_left[0]:.0f}°'
        ))

        # For analyst plot, add critical angle lines and annotations
        if plot_type == "Analyst" and show_metar and st.session_state.metar_data:
            metar = st.session_state.metar_data
            surface_u, surface_v = calculate_wind_components(metar['speed'], metar['direction'])

            # Get the lowest radar point
            radar_speed = st.session_state.wind_profile.speeds[0]
            radar_dir = st.session_state.wind_profile.directions[0]
            radar_u, radar_v = calculate_wind_components(radar_speed, radar_dir)

            # Calculate critical angles for both movers
            right_critical = calculate_skoff_angle_points(
                surface_u, surface_v, right_u, right_v, radar_u, radar_v
            )
            left_critical = calculate_skoff_angle_points(
                surface_u, surface_v, left_u, left_v, radar_u, radar_v
            )

            # Add lines to storm motion vectors (only in analyst mode)
            fig.add_trace(go.Scatter(
                x=[surface_u, right_u],
                y=[surface_v, right_v],
                mode='lines',
                line=dict(color='purple', width=2, dash='dash'),
                name='Right Mover Vector',
                showlegend=True
            ))

            fig.add_trace(go.Scatter(
                x=[surface_u, left_u],
                y=[surface_v, left_v],
                mode='lines',
                line=dict(color='blue', width=2, dash='dash'),
                name='Left Mover Vector',
                showlegend=True
            ))

            # Add critical angle annotations at different vertical positions
            fig.add_annotation(
                x=0,
                y=-max_speed * 0.7,
                text=f'Right Mover Critical Angle: {right_critical:.1f}°',
                showarrow=False,
                font=dict(size=12, color='purple'),
                bgcolor='white',
                bordercolor='purple',
                borderwidth=1
            )

            fig.add_annotation(
                x=0,
                y=-max_speed * 0.6,
                text=f'Left Mover Critical Angle: {left_critical:.1f}°',
                showarrow=False,
                font=dict(size=12, color='blue'),
                bgcolor='white',
                bordercolor='blue',
                borderwidth=1
            )

    except Exception as e:
        print(f"Could not calculate Bunkers movers: {str(e)}")

    return fig, max_speed

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
    if 'storm_motion' not in st.session_state:
        st.session_state.storm_motion = None

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

    # Add Storm Motion inputs
    st.sidebar.header("Storm Motion")
    storm_direction = st.sidebar.number_input(
        "Storm Direction (degrees)",
        min_value=0,
        max_value=360,
        value=None,
        help="Enter storm motion direction (0-360 degrees)"
    )
    storm_speed = st.sidebar.number_input(
        "Storm Speed (knots)",
        min_value=0,
        max_value=100,
        value=None,
        help="Enter storm motion speed in knots"
    )

    # Update storm motion in session state
    st.session_state.storm_motion = {
        'direction': storm_direction,
        'speed': storm_speed
    } if storm_direction is not None and storm_speed is not None else None

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

            # Set site info in wind profile
            st.session_state.wind_profile.site_id = site_id
            st.session_state.wind_profile.site_name = site.name if site else None

            speeds = st.session_state.wind_profile.speeds
            plotter.setup_plot(
                site_id=site_id,
                site_name=site.name if site else None,
                valid_time=valid_time
            )
            plotter.plot_profile(st.session_state.wind_profile, height_colors=height_colors)

            if show_metar and st.session_state.metar_data:
                metar = st.session_state.metar_data
                surface_u, surface_v = calculate_wind_components(metar['speed'], metar['direction'])

                # Get the lowest radar point
                radar_speed = st.session_state.wind_profile.speeds[0]
                radar_dir = st.session_state.wind_profile.directions[0]
                radar_u, radar_v = calculate_wind_components(radar_speed, radar_dir)

                # Calculate shear depth
                shear_depth, aligned_heights = calculate_shear_depth(
                    surface_u, surface_v, st.session_state.wind_profile
                )

                fig, ax = plotter.get_plot()

                # Plot METAR point
                ax.scatter([surface_u], [surface_v], c='red', marker='*', s=150, 
                          label=f"METAR {metar['station']}")

                # Draw surface to radar line
                ax.plot([surface_u, radar_u], [surface_v, radar_v], 'b--', linewidth=2)

                # Draw the reference line (light grey dashed)
                end_u, end_v = extend_line_to_edge(surface_u, surface_v, radar_u, radar_v, plotter.max_speed)
                ax.plot([surface_u, end_u], [surface_v, end_v], 
                       color='lightgrey', linestyle='--', linewidth=1.5,
                       label='Ideal Shear Vector')


                # Add shear depth annotation
                max_speed = plotter.max_speed
                ax.text(0, -max_speed * 0.9,
                       f'Shear Depth: {shear_depth * 1000:.0f}m',
                       ha='center', va='center',
                       bbox=dict(facecolor='white', edgecolor='grey', alpha=0.8),
                       fontsize=10,
                       color='grey')

                # Only add storm motion if it's been entered
                if st.session_state.storm_motion:
                    storm_u, storm_v = calculate_wind_components(
                        st.session_state.storm_motion['speed'],
                        st.session_state.storm_motion['direction']
                    )

                    # Plot Storm Motion point
                    ax.scatter([storm_u], [storm_v], c='green', marker='^', s=150,
                              label='Storm Motion')

                    # Draw connecting lines (only surface to storm motion)
                    ax.plot([surface_u, storm_u], [surface_v, storm_v], 'g--', linewidth=2)

                    # Calculate and display Skoff Critical Angle
                    critical_angle = calculate_skoff_angle_points(
                        surface_u, surface_v, storm_u, storm_v, radar_u, radar_v
                    )

                    # Add text annotation for critical angle at the bottom
                    max_speed = plotter.max_speed
                    ax.text(0, -max_speed * 0.8, 
                           f'Skoff Critical Angle: {critical_angle:.1f}°',
                           ha='center', va='center',
                           bbox=dict(facecolor='white', edgecolor='blue', alpha=0.8),
                           fontsize=10,
                           color='blue')

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

            fig, max_speed = create_plotly_hodograph(
                st.session_state.wind_profile,
                site_id=site_id,
                site_name=site.name if site else None,
                valid_time=valid_time
            )

            if show_metar and st.session_state.metar_data:
                metar = st.session_state.metar_data
                surface_u, surface_v = calculate_wind_components(metar['speed'], metar['direction'])

                # Get the lowest radar point
                radar_speed = st.session_state.wind_profile.speeds[0]
                radar_dir = st.session_state.wind_profile.directions[0]
                radar_u, radar_v = calculate_wind_components(radar_speed, radar_dir)

                # Calculate shear depth
                shear_depth, aligned_heights = calculate_shear_depth(
                    surface_u, surface_v, st.session_state.wind_profile
                )

                # Add METAR point and surface-to-radar line
                fig.add_trace(go.Scatter(
                    x=[surface_u, radar_u],
                    y=[surface_v, radar_v],
                    mode='lines',
                    line=dict(color='blue', width=2, dash='dash'),
                    showlegend=False,
                    hoverinfo='skip'
                ))

                fig.add_trace(go.Scatter(
                    x=[surface_u],
                    y=[surface_v],
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

                # Add reference vector line extended to edge
                end_u, end_v = extend_line_to_edge(surface_u, surface_v, radar_u, radar_v, max_speed)
                fig.add_trace(go.Scatter(
                    x=[surface_u, end_u],
                    y=[surface_v, end_v],
                    mode='lines',
                    line=dict(color='lightgrey', width=1.5, dash='dash'),
                    name='Ideal Shear Vector',
                    showlegend=True
                ))

                # Add shear depth annotation
                fig.add_annotation(
                    x=0,
                    y=-max_speed * 0.9,
                    text=f'Shear Depth: {shear_depth * 1000:.0f}m',
                    showarrow=False,
                    font=dict(size=12, color='grey'),
                    bgcolor='white',
                    bordercolor='grey',
                    borderwidth=1
                )


                # Only add storm motion if it's been entered
                if st.session_state.storm_motion:
                    storm_u, storm_v = calculate_wind_components(
                        st.session_state.storm_motion['speed'],
                        st.session_state.storm_motion['direction']
                    )

                    # Add Storm Motion point
                    fig.add_trace(go.Scatter(
                        x=[storm_u],
                        y=[storm_v],
                        mode='markers',
                        marker=dict(
                            symbol='triangle-up',
                            size=15,
                            color='green',
                        ),
                        name="Storm Motion",
                        hoverinfo='text',
                        text=f"Storm Motion<br>Speed: {st.session_state.storm_motion['speed']}kts<br>Direction: {st.session_state.storm_motion['direction']}°"
                    ))

                    # Add connecting lines
                    for coord_pair in [
                        dict(
                            points=([surface_u, storm_u], [surface_v, storm_v]),
                            color='green'
                        )
                    ]:
                        fig.add_trace(go.Scatter(
                            x=coord_pair['points'][0],
                            y=coord_pair['points'][1],
                            mode='lines',
                            line=dict(color=coord_pair['color'], width=2, dash='dash'),
                            showlegend=False,
                            hoverinfo='skip'
                        ))

                    # Calculate and display Skoff Critical Angle
                    critical_angle = calculate_skoff_angle_points(
                        surface_u, surface_v, storm_u, storm_v, radar_u, radar_v
                    )

                    # Add annotation for the angle at the bottom
                    fig.add_annotation(
                        x=0,
                        y=-max_speed * 0.8,
                        text=f'Skoff Critical Angle: {critical_angle:.1f}°',
                        showarrow=False,
                        font=dict(size=12, color='blue'),
                        bgcolor='white',
                        bordercolor='blue',
                        borderwidth=1
                    )

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