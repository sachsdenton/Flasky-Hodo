import streamlit as st
import numpy as np
from datetime import datetime
import matplotlib.pyplot as plt
import plotly.graph_objects as go
import pandas as pd
import folium
from streamlit_folium import st_folium
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
from map_component import load_metar_sites, calculate_distance, create_map
from geopy.distance import distance
from mrms_handler import MRMSHandler

def calculate_vector_angle(u1: float, v1: float, u2: float, v2: float) -> float:
    """Calculate the angle between two vectors."""
    # Function uses the same calculation as utils.calculate_skoff_angle but with components
    dot_product = u1 * u2 + v1 * v2
    mag1 = np.sqrt(u1**2 + v1**2)
    mag2 = np.sqrt(u2**2 + v2**2)

    if mag1 == 0 or mag2 == 0:
        return 0.0

    cos_angle = np.clip(dot_product / (mag1 * mag2), -1.0, 1.0)
    angle_rad = np.arccos(cos_angle)
    return np.rad2deg(angle_rad)


def calculate_shear_depth(surface_u: float, surface_v: float, profile: WindProfile) -> Tuple[float, list, float]:
    """Calculate shear depth based on points within 5 degrees of the surface-to-lowest vector,
    stopping at the first point that deviates from this alignment. Also calculates shear magnitude."""
    # Get the lowest radar point
    radar_u, radar_v = calculate_wind_components(profile.speeds[0], profile.directions[0])

    # Calculate reference vector (from surface to lowest radar point)
    ref_u = radar_u - surface_u
    ref_v = radar_v - surface_v

    # Find points within 5 degrees of reference vector, stopping at first deviation
    aligned_heights = []
    aligned_u = []
    aligned_v = []
    for i in range(len(profile.speeds)):
        point_u, point_v = calculate_wind_components(profile.speeds[i], profile.directions[i])
        vector_u = point_u - surface_u
        vector_v = point_v - surface_v

        angle = calculate_vector_angle(ref_u, ref_v, vector_u, vector_v)
        if angle <= 5.0:  # Within 5 degrees
            aligned_heights.append(profile.heights[i])
            aligned_u.append(point_u)
            aligned_v.append(point_v)
        else:
            # Stop at first deviation outside the 5-degree bandwidth
            break

    # Calculate shear magnitude (vector difference between surface and highest aligned point)
    shear_magnitude = 0.0
    if aligned_u and aligned_v:
        final_u = aligned_u[-1]
        final_v = aligned_v[-1]
        shear_magnitude = np.sqrt((final_u - surface_u)**2 + (final_v - surface_v)**2)

    # Return the maximum height (shear depth), list of aligned heights, and shear magnitude
    return max(aligned_heights) if aligned_heights else 0.0, aligned_heights, shear_magnitude


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
    # This is a specialized version of the vector angle calculation for three points
    # Calculate vectors
    v1 = [storm_u - surface_u, storm_v - surface_v]  # Surface to Storm vector
    v2 = [radar_u - surface_u, radar_v - surface_v]  # Surface to Radar vector
    
    # Use the existing vector angle function
    return calculate_vector_angle(v1[0], v1[1], v2[0], v2[1])


def create_plotly_hodograph(wind_profile, site_id=None, site_name=None, valid_time=None, plot_type="Standard"):
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
    
    # Add METAR info in the specified format if available
    if st.session_state.metar_data and all(key in st.session_state.metar_data for key in ['station', 'direction', 'speed']):
        metar = st.session_state.metar_data
        metar_time_str = ""
        if 'time' in metar and metar['time']:
            metar_time_str = metar['time'].strftime('%H%M UTC')
        # Add a blank line before METAR info for better spacing
        title.append("")
        title.append(f"Surface Wind: {int(metar['direction'])}/{int(metar['speed'])} ({metar['station']} {metar_time_str})")

    if title:
        fig.update_layout(title={
            'text': '<br>'.join(title),
            'y': 0.98,  # Position title higher to create more space
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
        legend=dict(
            orientation="h",  # Horizontal orientation
            yanchor="bottom",
            y=-0.25,  # Position below the plot
            xanchor="center",
            x=0.5,  # Center horizontally
            bgcolor='rgba(255,255,255,0.8)',  # Semi-transparent background
            bordercolor="LightGrey",
            borderwidth=1
        ),
        hovermode='closest',
        width=600,
        height=600,
        autosize=True,  # Changed to True for better responsiveness
        margin=dict(t=80, b=120, l=50, r=50),  # Add more bottom margin for the legend
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
            showlegend=True,
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
            showlegend=True,
            hovertext=f'Left Mover<br>Speed: {bunkers_left[1]:.0f}kts<br>Direction: {bunkers_left[0]:.0f}°'
        ))

        if plot_type == "Analyst" and st.session_state.metar_data:
            metar = st.session_state.metar_data
            if all(key in metar for key in ['speed', 'direction']):
                surface_u, surface_v = calculate_wind_components(metar['speed'], metar['direction'])

                # Get the lowest radar point
                radar_speed = wind_profile.speeds[0]
                radar_dir = wind_profile.directions[0]
                radar_u, radar_v = calculate_wind_components(radar_speed, radar_dir)
                
                # Calculate shear depth and magnitude 
                shear_depth, aligned_heights, shear_magnitude = calculate_shear_depth(
                    surface_u, surface_v, wind_profile
                )

                # Calculate critical angles for both movers
                right_critical = calculate_skoff_angle_points(
                    surface_u, surface_v, right_u, right_v, radar_u, radar_v
                )
                left_critical = calculate_skoff_angle_points(
                    surface_u, surface_v, left_u, left_v, radar_u, radar_v
                )

                # Add lines from surface to storm movers
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

                # Add critical angle annotations
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

                # Add shear depth and magnitude annotation
                fig.add_annotation(
                    x=0,
                    y=-max_speed * 0.9,
                    text=f'Shear Depth: {shear_depth * 1000:.0f}m<br>Shear Magnitude: {shear_magnitude:.0f}kts',
                    showarrow=False,
                    font=dict(size=12, color='grey'),
                    bgcolor='white',
                    bordercolor='grey',
                    borderwidth=1
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
                    text=f"METAR {metar['station']}<br>Speed: {metar['speed']}kts<br>Direction: {metar['direction']}°{('<br>Time: ' + metar['time'].strftime('%H%M UTC')) if 'time' in metar and metar['time'] else ''}"
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
            else:
                st.warning("METAR station selected but wind data not yet available. Please fetch METAR data using the sidebar form.")

    except Exception as e:
        print(f"Could not calculate Bunkers movers: {str(e)}")

    return fig, max_speed


def refresh_data(site_id, metar_station=None):
    """Refresh both VWP and METAR data."""
    success = True
    error_message = None

    try:
        # Fetch VWP data asynchronously if available
        if site_id:
            from vad_reader import download_vad
            
            # Create temp directory if it doesn't exist
            os.makedirs("temp_data", exist_ok=True)
            
            # Check if we already have recent data (within 30 minutes)
            cache_file = os.path.join("temp_data", f"{site_id}_latest.vad")
            use_cache = False
            
            if os.path.exists(cache_file):
                file_time = os.path.getmtime(cache_file)
                time_diff = datetime.now().timestamp() - file_time
                # Use cache if less than 30 minutes old
                if time_diff < 1800:  # 30 minutes in seconds
                    use_cache = True
            
            # Download new data if needed
            if not use_cache:
                vad = download_vad(site_id, cache_path="temp_data")
            else:
                # Load from cache
                with open(cache_file, 'rb') as f:
                    from vad_reader import VADFile
                    vad = VADFile(f)
            
            if vad:
                # Store data as numpy arrays directly
                st.session_state.wind_profile.heights = np.array(vad['altitude'], dtype=float)
                st.session_state.wind_profile.speeds = np.array(vad['wind_spd'], dtype=float)
                st.session_state.wind_profile.directions = np.array(vad['wind_dir'], dtype=float)
                st.session_state.wind_profile.times = [vad['time']] * len(vad['altitude'])
                # Store site metadata
                st.session_state.wind_profile.site_id = site_id
                site = get_site_by_id(site_id)
                if site:
                    st.session_state.wind_profile.site_name = site.name
            else:
                success = False
                error_message = "Could not fetch radar data"

        # Fetch METAR data only if a station is provided
        if metar_station and success:
            wind_dir, wind_speed, obs_time, error = get_metar(metar_station)
            if error:
                # Don't fail the entire refresh for METAR errors
                st.warning(f"METAR Error: {error}")
            else:
                st.session_state.metar_data = {
                    'station': metar_station,
                    'direction': wind_dir,
                    'speed': wind_speed,
                    'time': obs_time
                }

        if success:
            st.session_state.last_update_time = datetime.now()

    except Exception as e:
        success = False
        error_message = f"Error refreshing data: {str(e)}"

    return success, error_message


def create_radar_map():
    """Create a folium map with radar site markers."""
    sites = get_sorted_sites()

    # Calculate center of US (approximately)
    center_lat, center_lon = 39.8283, -98.5795

    # Create the map with default center and zoom
    m = folium.Map(location=[center_lat, center_lon], zoom_start=4, width='100%')

    # Add markers for each radar site
    for site in sites:
        popup_content = f"""
        <div>
            <b>{site.id}</b><br>
            {site.name}
        </div>
        """

        icon = folium.DivIcon(
            html=f'''
                <div style="transform: rotate(45deg); 
                           background-color: red; 
                           width: 12px; 
                           height: 12px;">
                </div>
            ''',
            icon_size=(12, 12)
        )

        marker = folium.Marker(
            location=[site.lat, site.lon],
            popup=folium.Popup(popup_content, max_width=300),
            tooltip=f"{site.id} - {site.name}",
            icon=icon
        )
        marker._name = f"site_{site.id}"
        marker.add_to(m)

    return m


def update_map_view(m, site):
    """Update map center and zoom for selected radar site."""
    # Center on the radar site
    m.location = [site.lat, site.lon]

    # Calculate the bounds for 120nmi coverage
    # 120nmi ≈ 222.24 km
    # Using folium's fit_bounds to zoom appropriately
    from geopy.distance import distance

    # Calculate corner points of a box around the radar site
    corner_distance = distance(nautical=120)

    # Get the corner coordinates
    north = corner_distance.destination((site.lat, site.lon), bearing=0)
    south = corner_distance.destination((site.lat, site.lon), bearing=180)
    east = corner_distance.destination((site.lat, site.lon), bearing=90)
    west = corner_distance.destination((site.lat, site.lon), bearing=270)

    # Set bounds to cover the 120nmi radius
    bounds = [
        [south.latitude, west.longitude],  # Southwest corner
        [north.latitude, east.longitude]   # Northeast corner
    ]
    m.fit_bounds(bounds)

    return m


def add_metar_sites_to_map(m, radar_site):
    """Add METAR sites to the map for a given radar site."""
    try:
        # Load and filter METAR sites
        metar_sites = load_metar_sites()
        if not metar_sites.empty:
            # Calculate distances and filter sites within 120nmi
            metar_sites['distance'] = metar_sites.apply(
                lambda row: calculate_distance(
                    radar_site.lat, radar_site.lon,
                    row['Latitude'], row['Longitude']
                ),
                axis=1
            )
            metar_sites = metar_sites[metar_sites['distance'] <= 120]

            # Add range circle
            folium.Circle(
                location=[radar_site.lat, radar_site.lon],
                radius=222240,  # 120nmi in meters
                color='blue',
                fill=False,
                weight=1,
            ).add_to(m)

            # Add filtered METAR markers
            for _, row in metar_sites.iterrows():
                popup_content = f"""
                <div>
                    <b>{row['ID']}</b><br>
                    {row['Name']}
                </div>
                """

                folium.CircleMarker(
                    location=[row['Latitude'], row['Longitude']],
                    radius=4,
                    color='blue',
                    fill=True,
                    popup=folium.Popup(popup_content, max_width=200),
                    tooltip=f"{row['ID']} - {row['Name']}"
                ).add_to(m)
    except Exception as e:
        st.warning(f"Error loading METAR sites: {str(e)}")


def reset_app():
    """Reset all session state variables to their initial values."""
    # Clear session state variables
    st.session_state.wind_profile = WindProfile()
    st.session_state.metar_data = None
    st.session_state.storm_motion = None
    st.session_state.plot_type = "Standard"
    st.session_state.selected_site = None
    st.session_state.last_metar_click = None
    st.session_state.show_mrms = True
    
    # Clear URL parameters
    st.query_params.clear()
    
    # Display success message
    st.success("Application has been reset!")


def main():
    os.makedirs("temp_data", exist_ok=True)

    st.title("Hodograph Analysis Tool")
    
    # Add reset button
    if st.button("Reset Application", help="Reset the application to its initial state"):
        reset_app()
        st.rerun()

    # Initialize session state variables
    if 'wind_profile' not in st.session_state:
        st.session_state.wind_profile = WindProfile()
    if 'metar_data' not in st.session_state:
        st.session_state.metar_data = None
    if 'storm_motion' not in st.session_state:
        st.session_state.storm_motion = None
    if 'plot_type' not in st.session_state:
        st.session_state.plot_type = "Standard"
    if 'selected_site' not in st.session_state:
        st.session_state.selected_site = None
    if 'last_metar_click' not in st.session_state:
        st.session_state.last_metar_click = None
    if 'show_mrms' not in st.session_state:
        st.session_state.show_mrms = True

    st.subheader("Select Radar Site")

    # Add MRMS toggle in the sidebar
    st.sidebar.header("Map Settings")
    show_mrms = st.sidebar.checkbox("Show MRMS Radar", value=st.session_state.show_mrms)
    if show_mrms != st.session_state.show_mrms:
        st.session_state.show_mrms = show_mrms
        st.experimental_rerun()

    # Create map with MRMS support
    radar_map = create_map(show_mrms=st.session_state.show_mrms)

    # If a site is selected, add METAR sites around it and update view
    if st.session_state.selected_site:
        try:
            site = get_site_by_id(st.session_state.selected_site)
            radar_map = update_map_view(radar_map, site)
            add_metar_sites_to_map(radar_map, site)
        except ValueError as e:
            st.error(f"Error with radar site: {str(e)}")

    # Generate a unique key for the map based on the selected site
    map_key = f"radar_map_{st.session_state.selected_site}" if st.session_state.selected_site else "radar_map"
    map_data = st_folium(radar_map, height=600, width="100%", key=map_key)

    # Handle map clicks
    if map_data and "last_object_clicked_tooltip" in map_data:
        tooltip = map_data["last_object_clicked_tooltip"]
        if tooltip:
            # Extract site ID from tooltip (format: "XXXX - Site Name")
            site_id = tooltip.split(" - ")[0].strip()
            try:
                # Check if it's a radar site
                site = get_site_by_id(site_id)
                if site_id != st.session_state.selected_site:
                    st.session_state.selected_site = site_id
                    st.query_params["site"] = site_id
                    st.rerun()
            except ValueError:
                # Check if it's a METAR site and hasn't been clicked recently
                metar_sites = load_metar_sites()
                current_time = time.time()
                if (not metar_sites.empty and site_id in metar_sites['ID'].values and 
                    (st.session_state.last_metar_click is None or 
                     current_time - st.session_state.last_metar_click > 2)):
                    st.session_state.metar_data = {'station': site_id}
                    st.session_state.last_metar_click = current_time
                    st.query_params["metar"] = site_id

                    # Refresh data for both radar and METAR when a METAR site is selected
                    if st.session_state.selected_site:  # Only if we have a radar site selected
                        with st.spinner('Refreshing data...'):
                            success, error_message = refresh_data(
                                st.session_state.selected_site,
                                site_id  # Pass the METAR station ID
                            )
                            if not success:
                                st.error(error_message)

    # Site selection sidebar
    st.sidebar.header("Site Selection")

    # Add text input for manual site selection
    manual_site = st.sidebar.text_input(
        "Enter Site ID",
        value=st.session_state.selected_site if st.session_state.selected_site else "",
        key="site_input",
        help="Enter a 4-letter site ID (e.g., KABR for radar, KBOS for METAR)"
    ).strip().upper()

    # Update selected site based on manual input
    if manual_site:
        try:
            site = get_site_by_id(manual_site)
            if manual_site != st.session_state.selected_site:
                st.session_state.selected_site = manual_site
                st.query_params["site"] = manual_site
                st.rerun()
        except ValueError:
            # Check if it's a valid METAR site
            metar_sites = load_metar_sites()
            if not metar_sites.empty and manual_site in metar_sites['ID'].values:
                st.session_state.metar_data = {'station': manual_site}
            else:
                st.sidebar.error(f"Invalid site ID: {manual_site}")

    if st.session_state.selected_site:
        site = get_site_by_id(st.session_state.selected_site)
        if site:
            st.sidebar.write(f"Selected Site: {site.id}")
            st.sidebar.write(f"Name: {site.name}")
            st.sidebar.write(f"Location: {site.lat:.2f}°N, {site.lon:.2f}°W")

            if st.sidebar.button("Plot Hodograph"):
                with st.spinner('Refreshing data...'):
                    success, error_message = refresh_data(site.id, None)
                    if not success:
                        st.sidebar.error(error_message)
                    else:
                        st.sidebar.success("Successfully refreshed data")
        else:
            st.sidebar.info("Click a marker on the map or enter a site ID to select a radar site")

    # Move METAR Data Section up in the sidebar
    st.sidebar.markdown("---")  # Add a visual separator
    st.sidebar.header("METAR Data")

    # Get current radar site information if selected
    radar_site = None
    if st.session_state.selected_site:
        site = get_site_by_id(st.session_state.selected_site)
        if site:
            radar_site = {
                'id': site.id,
                'latitude': site.lat,
                'longitude': site.lon
            }


    # Use selected METAR in the form
    with st.sidebar.form("metar_form"):
        metar_station = st.text_input(
            "METAR Station ID (4-letter ICAO)",
            value=st.session_state.metar_data['station'] if st.session_state.metar_data else "",
            help="Enter a 4-letter ICAO station identifier (e.g., KBOS, KJFK)",
            max_chars=4
        ).strip().upper()

        metar_fetch = st.form_submit_button("Plot METAR")

    if metar_fetch:
        with st.spinner(f'Fetching METAR data from {metar_station}...'):
            wind_dir, wind_speed, obs_time, error = get_metar(metar_station)
            if error:
                st.sidebar.error(f"METAR Error: {error}")
                st.session_state.metar_data = None
            else:
                st.session_state.metar_data = {
                    'station': metar_station,
                    'direction': wind_dir,
                    'speed': wind_speed,
                    'time': obs_time
                }
                st.sidebar.success(f"METAR data loaded: {wind_speed}kts @ {wind_dir}°")

    # Add Storm Motion inputs
    st.sidebar.header("Storm Motion")
    with st.sidebar.form("storm_motion_form"):
        storm_direction = st.number_input(
            "Storm Direction (degrees)",
            min_value=0,
            max_value=360,
            value=st.session_state.storm_motion['direction'] if st.session_state.storm_motion else None,
            help="Enter storm motion direction (0-360 degrees)"
        )
        storm_speed = st.number_input(
            "Storm Speed (knots)",
            min_value=0,
            max_value=100,
            value=st.session_state.storm_motion['speed'] if st.session_state.storm_motion else None,
            help="Enter storm motion speed in knots"
        )

        storm_motion_submit = st.form_submit_button("Plot Storm Motion")

    if storm_motion_submit and storm_direction is not None and storm_speed is not None:
        st.session_state.storm_motion = {
            'direction': storm_direction,
            'speed': storm_speed
        }
        st.sidebar.success(f"Storm motion updated: {storm_speed}kts @ {storm_direction}°")
    elif storm_motion_submit:
        st.sidebar.error("Please enter both direction and speed for storm motion")


    if hasattr(st.session_state.wind_profile.speeds, '__len__') and len(st.session_state.wind_profile.speeds) > 0:
        st.subheader("Wind Profile Visualization")

        col1, col2, col3 = st.columns(3)
        with col1:
            # Initialize plot_type in session state if it doesn't exist
            if 'plot_type' not in st.session_state:
                st.session_state.plot_type = "Standard"
            # Use the radio button value directly
            plot_type = st.radio("Plot Type", ["Standard", "Analyst"], key="plot_type")
        with col2:
            height_colors = st.checkbox("Color code by height", value=True)
        with col3:
            show_metar = st.checkbox("Show METAR data", value=True)

        plt.close('all')

        if plot_type == "Standard":
            plotter = HodographPlotter()
            site = get_site_by_id(st.session_state.selected_site) if st.session_state.selected_site else None
            valid_time = st.session_state.wind_profile.times[0] if st.session_state.wind_profile.times else None

            # Set site info in wind profile
            st.session_state.wind_profile.site_id = st.session_state.selected_site
            st.session_state.wind_profile.site_name = site.name if site else None

            speeds = st.session_state.wind_profile.speeds
            plotter.setup_plot(
                site_id=st.session_state.selected_site,
                site_name=site.name if site else None,
                valid_time=valid_time
            )
            
            # First plot the profile (this will set up the plot with the correct scale)
            plotter.plot_profile(st.session_state.wind_profile, height_colors=height_colors)
            
            # Then add METAR information to the title if available
            if show_metar and st.session_state.metar_data and all(key in st.session_state.metar_data for key in ['station', 'direction', 'speed']):
                metar = st.session_state.metar_data
                metar_time_str = ""
                if 'time' in metar and metar['time']:
                    metar_time_str = metar['time'].strftime('%H%M UTC')
                
                # Get the current title text
                title = plotter.fig.texts[0].get_text() if plotter.fig.texts else ""
                
                # Add METAR information in the specified format with additional newlines for spacing
                metar_title = f"{title}\n\nSurface Wind: {int(metar['direction'])}/{int(metar['speed'])} ({metar['station']} {metar_time_str})"
                
                # Update the title
                plotter.fig.texts[0].set_text(metar_title)

            if show_metar and st.session_state.metar_data:
                metar = st.session_state.metar_data
                # Check if we have both speed and direction before proceeding
                if all(key in metar for key in ['speed', 'direction']):
                    surface_u, surface_v = calculate_wind_components(metar['speed'], metar['direction'])

                    ### Get the lowest radar point
                    radar_speed = st.session_state.wind_profile.speeds[0]
                    radar_dir = st.session_state.wind_profile.directions[0]
                    radar_u, radar_v = calculate_wind_components(radar_speed, radar_dir)

                    # Calculate shear depth and magnitude
                    shear_depth, aligned_heights, shear_magnitude = calculate_shear_depth(
                        surface_u, surface_v, st.session_state.wind_profile
                    )

                    fig, ax = plotter.get_plot()

                    # Plot METAR point with tooltip that includes timestamp
                    metar_label = f"METAR {metar['station']}"
                    if 'time' in metar and metar['time']:
                        # When hovering, the full info will be shown including timestamp
                        metar_label += f" ({metar['time'].strftime('%H%M UTC')})"
                    ax.scatter([surface_u], [surface_v], c='red', marker='*', s=150, 
                              label=metar_label)

                    # Draw surface to radar line
                    ax.plot([surface_u, radar_u], [surface_v, radar_v], 'b--', linewidth=2)

                    # Draw the reference line (light grey dashed)
                    end_u, end_v = extend_line_to_edge(surface_u, surface_v, radar_u, radar_v, plotter.max_speed)
                    ax.plot([surface_u, end_u], [surface_v, end_v], 
                           color='lightgrey', linestyle='--', linewidth=1.5,
                           label='Ideal Shear Vector')

                    # Add shear depth and magnitude annotations
                    max_speed = plotter.max_speed
                    ax.text(0, -max_speed * 0.9,
                           f'Shear Depth: {shear_depth * 1000:.0f}m\nShear Magnitude: {shear_magnitude:.0f}kts',
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

                        # Add the angle annotation
                        ax.text(0, -max_speed * 0.8,
                               f'Critical Angle: {critical_angle:.1f}°',
                               ha='center', va='center',
                               bbox=dict(facecolor='white', edgecolor='blue', alpha=0.8),
                               fontsize=10)
                else:
                    st.warning("METAR station selected but wind data not yet available. Please fetch METAR data using the sidebar form.")

            buf = io.BytesIO()
            fig, ax = plotter.get_plot()
            fig.savefig(buf, format='png', bbox_inches='tight')
            buf.seek(0)
            st.image(buf)
            plt.close(fig)
        else:
            site = get_site_by_id(st.session_state.selected_site) if st.session_state.selected_site else None
            valid_time = st.session_state.wind_profile.times[0] if st.session_state.wind_profile.times else None

            # Get the plotly hodograph - no need to add METAR data here as it's already handled in the create_plotly_hodograph 
            # function for the Analyst view
            fig, max_speed = create_plotly_hodograph(
                st.session_state.wind_profile,
                site_id=st.session_state.selected_site,
                site_name=site.name if site else None,
                valid_time=valid_time,
                plot_type=plot_type
            )

            st.plotly_chart(fig, usecontainer_width=True)

        # Add wind data table with more comprehensive data
        st.subheader("Wind Profile Data")
        
        # Create height, speed, and direction arrays
        heights = np.array(st.session_state.wind_profile.heights)
        speeds = np.array(st.session_state.wind_profile.speeds)
        directions = np.array(st.session_state.wind_profile.directions)
        
        # Calculate U and V components for each level
        u_components = []
        v_components = []
        for s, d in zip(speeds, directions):
            u, v = calculate_wind_components(s, d)
            u_components.append(round(u, 1))
            v_components.append(round(v, 1))
        
        # Calculate shear between adjacent layers
        shear_magnitude = []
        shear_direction = []
        
        for i in range(len(heights)-1):
            u1, v1 = calculate_wind_components(speeds[i], directions[i])
            u2, v2 = calculate_wind_components(speeds[i+1], directions[i+1])
            
            # Vector difference
            du = u2 - u1
            dv = v2 - v1
            
            # Magnitude of shear
            mag = np.sqrt(du**2 + dv**2)
            
            # Direction of shear (convert to meteorological convention)
            dir_rad = np.arctan2(-du, -dv)  # Note the negative signs to convert to meteorological convention
            dir_deg = np.rad2deg(dir_rad)
            if dir_deg < 0:
                dir_deg += 360
                
            shear_magnitude.append(round(mag, 1))
            shear_direction.append(int(dir_deg))
        
        # Add a placeholder for the last row
        shear_magnitude.append(None)
        shear_direction.append(None)
        
        # Create a comprehensive dataframe
        data = {
            'Height (m)': [int(h * 1000) for h in heights],
            'Height (ft)': [int(h * 1000 * 3.28084) for h in heights],
            'Speed (kts)': [int(s) for s in speeds],
            'Direction (°)': [int(d) for d in directions],
            'U-comp (kts)': u_components,
            'V-comp (kts)': v_components,
            'Layer Shear (kts)': shear_magnitude,
            'Shear Dir (°)': shear_direction
        }
        
        df = pd.DataFrame(data)
        st.dataframe(df, hide_index=True)
        
        # Add a summary of critical values
        if st.session_state.metar_data and all(key in st.session_state.metar_data for key in ['speed', 'direction']):
            st.subheader("Critical Values Summary")
            
            metar = st.session_state.metar_data
            surface_u, surface_v = calculate_wind_components(metar['speed'], metar['direction'])
            
            # Get the lowest radar point
            radar_speed = st.session_state.wind_profile.speeds[0]
            radar_dir = st.session_state.wind_profile.directions[0]
            
            # Calculate shear depth and magnitude
            shear_depth, aligned_heights, shear_magnitude = calculate_shear_depth(
                surface_u, surface_v, st.session_state.wind_profile
            )
            
            summary_data = {
                "Parameter": ["Shear Depth", "Shear Magnitude", "Surface Wind", "Lowest Radar Wind"],
                "Value": [
                    f"{shear_depth * 1000:.0f} meters",
                    f"{shear_magnitude:.1f} knots",
                    f"{int(metar['speed'])} knots from {int(metar['direction'])}°",
                    f"{int(radar_speed)} knots from {int(radar_dir)}°"
                ]
            }
            
            # Add Bunkers motion if available
            try:
                data = {
                    'wind_dir': st.session_state.wind_profile.directions,
                    'wind_spd': st.session_state.wind_profile.speeds,
                    'altitude': st.session_state.wind_profile.heights
                }
                bunkers_right, bunkers_left, mean_wind = compute_bunkers(data)
                
                summary_data["Parameter"].extend(["Right Mover", "Left Mover", "Mean Wind"])
                summary_data["Value"].extend([
                    f"{bunkers_right[1]:.1f} knots from {bunkers_right[0]:.1f}°",
                    f"{bunkers_left[1]:.1f} knots from {bunkers_left[0]:.1f}°",
                    f"{mean_wind[1]:.1f} knots from {mean_wind[0]:.1f}°"
                ])
                
                # Add critical angles if storm motion is available
                if st.session_state.storm_motion:
                    storm_u, storm_v = calculate_wind_components(
                        st.session_state.storm_motion['speed'],
                        st.session_state.storm_motion['direction']
                    )
                    
                    critical_angle = calculate_skoff_angle_points(
                        surface_u, surface_v, storm_u, storm_v, radar_u, radar_v
                    )
                    
                    summary_data["Parameter"].append("Critical Angle")
                    summary_data["Value"].append(f"{critical_angle:.1f}°")
            except Exception as e:
                st.warning(f"Could not calculate all derived values: {str(e)}")
                
            summary_df = pd.DataFrame(summary_data)
            st.dataframe(summary_df, hide_index=True)

    else:
        st.info("Select a radar site and click 'Plot Hodograph' to generate a hodograph.")

    # Handle site selection from the map using message passing
    if st.session_state.selected_site is not None:
        site = get_site_by_id(st.session_state.selected_site)
        if site:
            st.success(f"Site selected: {site.id} - {site.name}")

if __name__ == "__main__":
    main()