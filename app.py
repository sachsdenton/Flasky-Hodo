from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import json
import os
import io
import base64
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime
from typing import Optional, Dict, Any

# Import existing modules
from hodograph_plotter import HodographPlotter
from data_processor import WindProfile
from radar_sites import get_sorted_sites, get_site_by_id
from utils import calculate_wind_components, calculate_esterheld_angle, calculate_skoff_angle, find_kink_point, interpolate_wind_at_height
from metar_utils import get_metar
from params import compute_bunkers, compute_srh
from map_component import load_metar_sites, calculate_distance
from nexrad_fetcher import NEXRADFetcher
from warning_utils import fetch_active_warnings

app = Flask(__name__)
CORS(app)

# Global variables for caching
wind_profile = WindProfile()
nexrad_fetcher = NEXRADFetcher()

@app.route('/')
def index():
    """Main page with map and controls"""
    return render_template('index.html')

@app.route('/api/radar-sites')
def get_radar_sites():
    """Get all radar sites as JSON"""
    sites = get_sorted_sites()
    sites_data = []
    for site in sites:
        sites_data.append({
            'id': site.id,
            'name': site.name,
            'lat': site.lat,
            'lon': site.lon,
            'elevation': site.elevation
        })
    return jsonify(sites_data)

@app.route('/api/metar-sites')
def get_metar_sites():
    """Get METAR sites as JSON"""
    try:
        df = load_metar_sites()
        if df.empty:
            return jsonify([])
        
        metar_data = []
        for _, row in df.iterrows():
            metar_data.append({
                'id': row['ID'],
                'name': row['Name'],
                'lat': row['Latitude'],
                'lon': row['Longitude']
            })
        return jsonify(metar_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/warnings')
def get_warnings():
    """Get active weather warnings"""
    try:
        warnings = fetch_active_warnings()
        return jsonify(warnings)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/vad-data/<site_id>')
def get_vad_data(site_id):
    """Fetch VAD data for a radar site"""
    global wind_profile
    
    try:
        # Fetch latest VAD file
        file_path = nexrad_fetcher.fetch_latest(site_id.upper())
        if not file_path:
            return jsonify({'error': 'No VAD data available for this site'}), 404
        
        # Load data into wind profile
        wind_profile = WindProfile()
        success = wind_profile.load_from_nexrad(file_path)
        
        if not success:
            return jsonify({'error': 'Failed to load VAD data'}), 500
        
        # Get site information
        site = get_site_by_id(site_id.upper())
        
        return jsonify({
            'site_id': site_id.upper(),
            'site_name': site.name if site else site_id,
            'data_points': len(wind_profile.heights),
            'max_height': float(np.max(wind_profile.heights)) if len(wind_profile.heights) > 0 else 0,
            'success': True
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/metar/<station_id>')
def get_metar_data(station_id):
    """Get METAR data for a station"""
    try:
        wind_dir, wind_speed, obs_time, error = get_metar(station_id.upper())
        
        if error:
            return jsonify({'error': error}), 400
        
        return jsonify({
            'station': station_id.upper(),
            'direction': wind_dir,
            'speed': wind_speed,
            'time': obs_time.isoformat() if obs_time else None
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/wind-profile-data')
def get_wind_profile_data():
    """Return raw wind profile data for interactive client-side rendering"""
    global wind_profile
    
    try:
        if len(wind_profile.heights) == 0:
            return jsonify({'error': 'No wind profile data loaded'}), 400
        
        site_id = request.args.get('site_id', '')
        site = get_site_by_id(site_id) if site_id else None
        
        u_components = []
        v_components = []
        for speed, direction in zip(wind_profile.speeds, wind_profile.directions):
            u, v = calculate_wind_components(speed, direction)
            u_components.append(float(u))
            v_components.append(float(v))
        
        valid_time = None
        if hasattr(wind_profile, 'times') and len(wind_profile.times) > 0:
            vt = wind_profile.times[0]
            if hasattr(vt, 'strftime'):
                valid_time = vt.strftime('%Y-%m-%d %H:%M UTC')
        
        storm_direction = request.args.get('storm_direction', type=float)
        storm_speed = request.args.get('storm_speed', type=float)
        metar_direction = request.args.get('metar_direction', type=float)
        metar_speed = request.args.get('metar_speed', type=float)
        metar_station = request.args.get('metar_station', '')
        
        parameters = {}
        storm_motion_tuple = None
        if storm_direction is not None and storm_speed is not None:
            storm_motion_tuple = (storm_direction, storm_speed)
            storm_u, storm_v = calculate_wind_components(storm_speed, storm_direction)
            
            param_data = {
                'wind_dir': np.array(wind_profile.directions),
                'wind_spd': np.array(wind_profile.speeds),
                'altitude': np.array(wind_profile.heights)
            }
            
            if metar_direction is not None and metar_speed is not None:
                param_data['wind_dir'] = np.insert(param_data['wind_dir'], 0, metar_direction)
                param_data['wind_spd'] = np.insert(param_data['wind_spd'], 0, metar_speed)
                param_data['altitude'] = np.insert(param_data['altitude'], 0, 0.0)
            
            try:
                from params import compute_srh, compute_shear_mag
                srh_0_1 = compute_srh(param_data, storm_motion_tuple, 1000)
                srh_0_3 = compute_srh(param_data, storm_motion_tuple, 3000)
                shear_1km = compute_shear_mag(param_data, 1000)
                shear_3km = compute_shear_mag(param_data, 3000)
                
                parameters['srh_0_1'] = round(float(srh_0_1), 1) if not np.isnan(srh_0_1) else None
                parameters['srh_0_3'] = round(float(srh_0_3), 1) if not np.isnan(srh_0_3) else None
                parameters['shear_1km'] = round(float(shear_1km), 1) if not np.isnan(shear_1km) else None
                parameters['shear_3km'] = round(float(shear_3km), 1) if not np.isnan(shear_3km) else None
                
                try:
                    bunkers_result = compute_bunkers(param_data)
                    if bunkers_result and len(bunkers_result) >= 2:
                        parameters['bunkers_rm'] = {'direction': float(bunkers_result[0][0]), 'speed': float(bunkers_result[0][1])}
                except:
                    pass
                    
                if metar_direction is not None and metar_speed is not None and len(param_data['wind_spd']) > 1:
                    try:
                        surface_u, surface_v = calculate_wind_components(float(param_data['wind_spd'][0]), float(param_data['wind_dir'][0]))
                        radar_u, radar_v = calculate_wind_components(float(param_data['wind_spd'][1]), float(param_data['wind_dir'][1]))
                        v1_u, v1_v = storm_u - surface_u, storm_v - surface_v
                        v2_u, v2_v = radar_u - surface_u, radar_v - surface_v
                        dot_product = v1_u * v2_u + v1_v * v2_v
                        mag1 = np.sqrt(v1_u**2 + v1_v**2)
                        mag2 = np.sqrt(v2_u**2 + v2_v**2)
                        if mag1 > 0 and mag2 > 0:
                            cos_angle = np.clip(dot_product / (mag1 * mag2), -1.0, 1.0)
                            parameters['critical_angle'] = round(float(np.rad2deg(np.arccos(cos_angle))), 1)
                    except:
                        pass
            except Exception as e:
                print(f"Error computing parameters: {e}")
        
        return jsonify({
            'u_components': u_components,
            'v_components': v_components,
            'heights': [float(h) for h in wind_profile.heights],
            'speeds': [float(s) for s in wind_profile.speeds],
            'directions': [float(d) for d in wind_profile.directions],
            'max_speed': float(np.max(wind_profile.speeds)) if len(wind_profile.speeds) > 0 else 50,
            'site_id': site_id,
            'site_name': site.name if site else '',
            'valid_time': valid_time,
            'parameters': parameters
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/hodograph')
def generate_hodograph():
    """Generate hodograph plot"""
    global wind_profile
    
    try:
        # Get parameters from request
        plot_type = request.args.get('type', 'Standard')
        show_half_km = request.args.get('show_half_km', 'true').lower() == 'true'
        storm_direction = request.args.get('storm_direction', type=float)
        storm_speed = request.args.get('storm_speed', type=float)
        metar_direction = request.args.get('metar_direction', type=float)
        metar_speed = request.args.get('metar_speed', type=float)
        site_id = request.args.get('site_id', '')

        # Analyst mode feature toggles (all default to True for Standard mode)
        is_analyst = plot_type == 'Analyst'
        show_speed_rings = request.args.get('show_speed_rings', 'true').lower() == 'true'
        show_height_markers = request.args.get('show_height_markers', 'true').lower() == 'true'
        show_srh = request.args.get('show_srh', 'true').lower() == 'true'
        show_shear_vector = request.args.get('show_shear_vector', 'true').lower() == 'true'
        show_critical_angle = request.args.get('show_critical_angle', 'true').lower() == 'true'
        show_storm_motion_marker = request.args.get('show_storm_motion_marker', 'true').lower() == 'true'
        show_surface_wind_marker = request.args.get('show_surface_wind_marker', 'true').lower() == 'true'
        show_param_text = request.args.get('show_param_text', 'true').lower() == 'true'
        zoom_level = request.args.get('zoom', 1.0, type=float)
        
        if len(wind_profile.heights) == 0:
            return jsonify({'error': 'No wind profile data loaded'}), 400
        
        # Create hodograph plotter
        plotter = HodographPlotter()
        
        # Get site information
        site = get_site_by_id(site_id) if site_id else None
        site_name = site.name if site else None
        
        # Setup plot with minimal title (we'll add comprehensive title later)
        from datetime import datetime as dt_class
        plotter.setup_plot(site_id=site_id, site_name=site_name, valid_time=dt_class.now())
        
        # Plot the wind profile
        plotter.plot_profile(wind_profile, height_colors=True, show_half_km=show_half_km,
                           show_height_markers=show_height_markers, show_speed_rings=show_speed_rings,
                           zoom_level=zoom_level)
        
        # Remove duplicate METAR plotting - will be handled in main plotting section
        
        # Prepare meteorological data for plotting
        storm_motion_data = None
        storm_motion_tuple = None
        metar_data = None
        
        if storm_direction is not None and storm_speed is not None:
            storm_motion_data = {'direction': storm_direction, 'speed': storm_speed}
            storm_motion_tuple = (storm_direction, storm_speed)
            
        if metar_direction is not None and metar_speed is not None:
            metar_data = {'direction': metar_direction, 'speed': metar_speed}
        
        # Calculate and add meteorological annotations to the plot
        fig, ax = plotter.get_plot()
        
        # Add storm motion and surface wind markers
        if storm_motion_data and show_storm_motion_marker:
            storm_u, storm_v = calculate_wind_components(storm_motion_data['speed'], storm_motion_data['direction'])
            ax.plot(storm_u, storm_v, 'rs', markersize=12, label='Storm Motion', zorder=10)
            
        if metar_data and show_surface_wind_marker:
            metar_u, metar_v = calculate_wind_components(metar_data['speed'], metar_data['direction'])
            ax.plot(metar_u, metar_v, 'ko', markersize=10, label='Surface Wind', zorder=10)
            
        # Add SRH shading and critical angle analysis
        esterheld_angle_value = None
        skoff_angle_value = None
        if storm_motion_data and metar_data and len(wind_profile.speeds) > 0:
            surface_u, surface_v = calculate_wind_components(metar_data['speed'], metar_data['direction'])
            storm_u, storm_v = calculate_wind_components(storm_motion_data['speed'], storm_motion_data['direction'])
            
            try:
                u_comp = [surface_u]
                v_comp = [surface_v]
                heights = [0.0]
                
                for i, (speed, direction) in enumerate(zip(wind_profile.speeds, wind_profile.directions)):
                    u, v = calculate_wind_components(speed, direction)
                    u_comp.append(u)
                    v_comp.append(v)
                    heights.append(wind_profile.heights[i])
                
                u_comp = np.array(u_comp)
                v_comp = np.array(v_comp)
                heights = np.array(heights)
                
                if show_srh:
                    srh_1km_u = []
                    srh_1km_v = []
                    for i, height in enumerate(heights):
                        if height <= 1000:
                            srh_1km_u.append(u_comp[i])
                            srh_1km_v.append(v_comp[i])
                    
                    if len(srh_1km_u) > 2:
                        srh_1km_u.append(storm_u)
                        srh_1km_v.append(storm_v)
                        srh_1km_u.append(srh_1km_u[0])
                        srh_1km_v.append(srh_1km_v[0])
                        ax.fill(srh_1km_u, srh_1km_v, color='lightgreen', alpha=0.3, label='SRH 0-1km', zorder=1)
                    
                    srh_3km_u = []
                    srh_3km_v = []
                    for i, height in enumerate(heights):
                        if height <= 3000:
                            srh_3km_u.append(u_comp[i])
                            srh_3km_v.append(v_comp[i])
                    
                    if len(srh_3km_u) > 2:
                        srh_3km_u.append(storm_u)
                        srh_3km_v.append(storm_v)
                        srh_3km_u.append(srh_3km_u[0])
                        srh_3km_v.append(srh_3km_v[0])
                        ax.fill(srh_3km_u, srh_3km_v, color='lightblue', alpha=0.2, label='SRH 0-3km', zorder=0)
                    
            except Exception as e:
                print(f"Error adding SRH shading: {e}")
            
            if len(wind_profile.speeds) > 0:
                radar_u, radar_v = calculate_wind_components(wind_profile.speeds[0], wind_profile.directions[0])
                ref_u, ref_v = radar_u - surface_u, radar_v - surface_v
                
                shear_points_u = [surface_u]
                shear_points_v = [surface_v]
                
                for i, (speed, direction) in enumerate(zip(wind_profile.speeds, wind_profile.directions)):
                    point_u, point_v = calculate_wind_components(speed, direction)
                    vector_u, vector_v = point_u - surface_u, point_v - surface_v
                    
                    if np.sqrt(ref_u**2 + ref_v**2) > 0 and np.sqrt(vector_u**2 + vector_v**2) > 0:
                        dot_product = ref_u * vector_u + ref_v * vector_v
                        mag_ref = np.sqrt(ref_u**2 + ref_v**2)
                        mag_vec = np.sqrt(vector_u**2 + vector_v**2)
                        cos_angle = np.clip(dot_product / (mag_ref * mag_vec), -1.0, 1.0)
                        angle = np.rad2deg(np.arccos(cos_angle))
                        
                        if angle <= 10.0:
                            shear_points_u.append(point_u)
                            shear_points_v.append(point_v)
                        else:
                            break
                
                if show_shear_vector:
                    if len(shear_points_u) > 1:
                        ax.plot(shear_points_u, shear_points_v, 'g-', linewidth=4, alpha=0.7, label='Shear Vector', zorder=8)
                
                vad_u = np.array([calculate_wind_components(s, d)[0] for s, d in zip(wind_profile.speeds, wind_profile.directions)])
                vad_v = np.array([calculate_wind_components(s, d)[1] for s, d in zip(wind_profile.speeds, wind_profile.directions)])
                vad_heights_m = np.array(wind_profile.heights)

                vad_1km = interpolate_wind_at_height(vad_heights_m, vad_u, vad_v, 1000.0)
                if vad_1km:
                    esterheld_angle_value = calculate_esterheld_angle(
                        surface_u, surface_v, storm_u, storm_v, vad_1km[0], vad_1km[1])

                kink = find_kink_point(surface_u, surface_v, vad_u, vad_v, threshold_deg=5.0)
                if kink:
                    skoff_angle_value = calculate_skoff_angle(
                        surface_u, surface_v, storm_u, storm_v, kink[0], kink[1])

                if show_critical_angle:
                    ax.plot([surface_u, storm_u], [surface_v, storm_v], 'r--', linewidth=2, alpha=0.8, label='Surface-Storm', zorder=9)

                    if vad_1km and esterheld_angle_value is not None:
                        ax.plot([surface_u, vad_1km[0]], [surface_v, vad_1km[1]], 'b--', linewidth=2, alpha=0.8, label='Esterheld (1km)', zorder=9)

                    if kink and skoff_angle_value is not None:
                        ax.plot([surface_u, kink[0]], [surface_v, kink[1]], 'm--', linewidth=2, alpha=0.8, label='Skoff (kink)', zorder=9)
        
        # Add meteorological parameters text directly on the plot
        if storm_motion_data:
            # Calculate parameters for text display
            param_data = {
                'wind_dir': np.array(wind_profile.directions),
                'wind_spd': np.array(wind_profile.speeds),
                'altitude': np.array(wind_profile.heights)
            }
            
            # Add surface wind if available
            if metar_data:
                param_data['wind_dir'] = np.insert(param_data['wind_dir'], 0, metar_data['direction'])
                param_data['wind_spd'] = np.insert(param_data['wind_spd'], 0, metar_data['speed'])
                param_data['altitude'] = np.insert(param_data['altitude'], 0, 0.0)
            
            try:
                # Calculate key parameters
                from params import compute_srh, compute_shear_mag
                srh_0_1 = compute_srh(param_data, storm_motion_tuple, 1000)
                srh_0_3 = compute_srh(param_data, storm_motion_tuple, 3000)
                shear_1km = compute_shear_mag(param_data, 1000)
                shear_3km = compute_shear_mag(param_data, 3000)
                
                # Create parameter text with requested order
                param_text = []
                
                # Wind shear values first
                if not np.isnan(shear_1km):
                    param_text.append(f'0-1km Shear: {shear_1km:.0f} kt')
                if not np.isnan(shear_3km):
                    param_text.append(f'0-3km Shear: {shear_3km:.0f} kt')
                
                # Storm motion (input storm motion)
                if storm_motion_data:
                    param_text.append(f'Storm Motion: {storm_motion_data["direction"]:.0f}°/{storm_motion_data["speed"]:.0f}kt')
                
                # Add Bunkers storm motion
                try:
                    from params import compute_bunkers
                    bunkers_result = compute_bunkers(param_data)
                    if bunkers_result and len(bunkers_result) >= 2:
                        bunkers_rm = bunkers_result[0]
                        param_text.append(f'Bunkers RM: {bunkers_rm[0]:.0f}°/{bunkers_rm[1]:.0f}kt')
                except:
                    pass
                
                if esterheld_angle_value is not None:
                    param_text.append(f'Esterheld Angle: {esterheld_angle_value:.1f}°')
                if skoff_angle_value is not None:
                    param_text.append(f'Skoff Angle: {skoff_angle_value:.1f}°')
                
                # Calculate and add shear magnitude and depth for display
                shear_magnitude_display = None
                shear_depth_display = None
                if metar_data and len(param_data['wind_spd']) > 1:
                    try:
                        surface_u, surface_v = calculate_wind_components(float(param_data['wind_spd'][0]), float(param_data['wind_dir'][0]))
                        
                        # Get the lowest radar point for reference vector
                        radar_u, radar_v = calculate_wind_components(float(param_data['wind_spd'][1]), float(param_data['wind_dir'][1]))
                        ref_u, ref_v = radar_u - surface_u, radar_v - surface_v
                        
                        # Find points within 5 degrees of reference vector and calculate shear depth
                        aligned_heights = []
                        aligned_indices = []
                        
                        # Check all radar points for alignment within ±5 degrees (skip surface wind at index 0)
                        for i in range(1, len(param_data['wind_spd'])):
                            point_u, point_v = calculate_wind_components(float(param_data['wind_spd'][i]), float(param_data['wind_dir'][i]))
                            vector_u, vector_v = point_u - surface_u, point_v - surface_v
                            
                            # Calculate angle between vectors
                            dot_product = ref_u * vector_u + ref_v * vector_v
                            mag_ref = np.sqrt(ref_u**2 + ref_v**2)
                            mag_vec = np.sqrt(vector_u**2 + vector_v**2)
                            
                            if mag_ref > 0 and mag_vec > 0:
                                cos_angle = np.clip(dot_product / (mag_ref * mag_vec), -1.0, 1.0)
                                angle = np.rad2deg(np.arccos(cos_angle))
                                
                                # Include all points within ±5 degrees, don't break on first non-aligned point
                                if angle <= 5.0:
                                    aligned_heights.append(param_data['altitude'][i])
                                    aligned_indices.append(i)
                        
                        if aligned_heights and len(aligned_indices) > 0:
                            # Use the maximum altitude or a minimum meaningful depth
                            raw_depth = max(aligned_heights)
                            
                            print(f"Debug: Found {len(aligned_indices)} aligned levels, raw_depth: {raw_depth:.0f}m")
                            print(f"Debug: Aligned altitudes: {[f'{h:.0f}m' for h in aligned_heights[:5]]}")  # Show first 5
                            
                            # If VAD altitudes are very small (< 50m), estimate depth based on typical radar beam geometry
                            if raw_depth < 50:
                                # Estimate depth based on number of aligned levels and typical VAD level spacing
                                # Typical VAD levels are spaced every ~150-300m in height
                                estimated_depth = len(aligned_indices) * 200  # 200m per level estimate
                                shear_depth_display = max(raw_depth, estimated_depth)
                                print(f"Debug: Using estimated depth: {shear_depth_display:.0f}m")
                            else:
                                shear_depth_display = raw_depth
                                print(f"Debug: Using raw depth: {shear_depth_display:.0f}m")
                            
                            # Calculate shear magnitude using the highest aligned point
                            final_index = aligned_indices[-1]
                            final_u, final_v = calculate_wind_components(float(param_data['wind_spd'][final_index]), float(param_data['wind_dir'][final_index]))
                            shear_magnitude_display = np.sqrt((final_u - surface_u)**2 + (final_v - surface_v)**2)
                            
                            print(f"Debug: Shear magnitude: {shear_magnitude_display:.1f}kt at level {final_index}")
                        else:
                            print("Debug: No aligned heights found")
                    except Exception as e:
                        print(f"Debug: Error calculating shear parameters: {e}")
                        import traceback
                        traceback.print_exc()
                
                # Add shear magnitude and depth under critical angle
                if shear_magnitude_display is not None:
                    param_text.append(f'Shear Magnitude: {shear_magnitude_display:.1f} kt')
                if shear_depth_display is not None:
                    param_text.append(f'Shear Depth: {shear_depth_display:.0f} m')
                
                # Add both SRH values below shear parameters
                if not np.isnan(srh_0_1):
                    param_text.append(f'SRH 0-1km: {srh_0_1:.0f} m²/s²')
                if not np.isnan(srh_0_3):
                    param_text.append(f'SRH 0-3km: {srh_0_3:.0f} m²/s²')
                
                if show_param_text and param_text:
                    param_str = '\n'.join(param_text)
                    ax.text(0.02, 0.98, param_str, transform=ax.transAxes, fontsize=10,
                           verticalalignment='top', bbox=dict(boxstyle="round,pad=0.5", 
                           facecolor="lightblue", alpha=0.8), zorder=12)
            except Exception as e:
                print(f"Error adding parameters to plot: {e}")
        
        # Add comprehensive title to the hodograph
        title_lines = []
        if site:
            title_lines.append(f'{site.id} - {site.name.upper()}')
        
        # Get VAD valid time from wind profile data (simplified)
        if hasattr(wind_profile, 'times') and len(wind_profile.times) > 0:
            vad_time = wind_profile.times[0]  # Use first timestamp
            if hasattr(vad_time, 'strftime'):
                utc_str = vad_time.strftime('%Y-%m-%d %H:%M')
                title_lines.append(f'Valid: {utc_str}UTC')
            else:
                title_lines.append(f'Valid: VAD Data Available')
        else:
            # Use current time as fallback
            from datetime import datetime as dt_class
            current_time = dt_class.now()
            title_lines.append(f'Valid: {current_time.strftime("%Y-%m-%d %H:%M")}UTC')
        
        # Add empty line
        title_lines.append('')
        
        # Add surface wind information with station ID and timestamp
        if metar_data:
            metar_station_id = request.args.get('metar_station', 'METAR')
            
            # Get METAR observation time from the API
            try:
                import requests
                metar_url = f"https://aviationweather.gov/api/data/metar?ids={metar_station_id}&format=json"
                response = requests.get(metar_url, timeout=5)
                if response.status_code == 200:
                    metar_json = response.json()
                    if metar_json and len(metar_json) > 0:
                        obs_time = metar_json[0].get('reportTime', '')
                        if obs_time:
                            # Extract time from ISO format (e.g., "2025-06-08T22:53:00Z")
                            try:
                                from datetime import datetime as dt_class
                                obs_dt = dt_class.fromisoformat(obs_time.replace('Z', '+00:00'))
                                obs_str = obs_dt.strftime('%H%M')
                                title_lines.append(f'Surface Wind {metar_data["direction"]:.0f}/{metar_data["speed"]:.0f} ({metar_station_id} {obs_str}UTC)')
                            except:
                                title_lines.append(f'Surface Wind {metar_data["direction"]:.0f}/{metar_data["speed"]:.0f} ({metar_station_id})')
                        else:
                            title_lines.append(f'Surface Wind {metar_data["direction"]:.0f}/{metar_data["speed"]:.0f} ({metar_station_id})')
                    else:
                        title_lines.append(f'Surface Wind {metar_data["direction"]:.0f}/{metar_data["speed"]:.0f} ({metar_station_id})')
                else:
                    title_lines.append(f'Surface Wind {metar_data["direction"]:.0f}/{metar_data["speed"]:.0f} ({metar_station_id})')
            except:
                title_lines.append(f'Surface Wind {metar_data["direction"]:.0f}/{metar_data["speed"]:.0f} ({metar_station_id})')
        
        # Set the comprehensive title
        title_text = '\n'.join(title_lines)
        ax.set_title(title_text, fontsize=12, fontweight='bold', pad=20, loc='center')
        
        ax.legend(loc='upper right', fontsize=9)
        
        # Save plot to base64 string
        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format='png', dpi=150, bbox_inches='tight')
        img_buffer.seek(0)
        img_base64 = base64.b64encode(img_buffer.getvalue()).decode()
        plt.close()
        
        # Calculate advanced meteorological parameters
        parameters = {}
        if storm_motion_data:
            try:
                # Prepare data for parameter calculations (correct format for params.py functions)
                data = {
                    'wind_dir': np.array(wind_profile.directions),
                    'wind_spd': np.array(wind_profile.speeds),
                    'altitude': np.array(wind_profile.heights)
                }
                
                # Add surface wind if available
                metar_data = None
                if metar_direction is not None and metar_speed is not None:
                    metar_data = {'direction': metar_direction, 'speed': metar_speed}
                    surface_direction = metar_direction
                    surface_speed = metar_speed
                    
                    # Prepend surface wind to data arrays
                    data['wind_dir'] = np.insert(data['wind_dir'], 0, surface_direction)
                    data['wind_spd'] = np.insert(data['wind_spd'], 0, surface_speed)
                    data['altitude'] = np.insert(data['altitude'], 0, 0.0)
                
                # Calculate SRH values
                from params import compute_srh
                srh_0_5 = compute_srh(data, storm_motion_tuple, 500)
                srh_0_1 = compute_srh(data, storm_motion_tuple, 1000)
                srh_0_3 = compute_srh(data, storm_motion_tuple, 3000)
                
                # Calculate shear magnitude
                from params import compute_shear_mag
                shear_1km = compute_shear_mag(data, 1000)
                shear_3km = compute_shear_mag(data, 3000)
                shear_6km = compute_shear_mag(data, 6000)
                
                # Calculate Bunkers storm motion for comparison
                from params import compute_bunkers
                try:
                    bunkers_result = compute_bunkers(data)
                    if bunkers_result and len(bunkers_result) >= 2:
                        bunkers_rm = bunkers_result[0]
                        bunkers_lm = bunkers_result[1]
                        bunkers_info = {
                            'right_mover': {'direction': float(bunkers_rm[0]), 'speed': float(bunkers_rm[1])},
                            'left_mover': {'direction': float(bunkers_lm[0]), 'speed': float(bunkers_lm[1])}
                        }
                    else:
                        bunkers_info = None
                except:
                    bunkers_info = None
                
                esterheld_angle = None
                skoff_angle = None
                kink_u_val, kink_v_val = None, None
                vad_1km_u_val, vad_1km_v_val = None, None
                if metar_data and len(data['wind_spd']) > 1:
                    try:
                        surface_u, surface_v = calculate_wind_components(float(data['wind_spd'][0]), float(data['wind_dir'][0]))
                        storm_u, storm_v = calculate_wind_components(storm_motion_data['speed'], storm_motion_data['direction'])

                        vad_u = np.array([calculate_wind_components(float(s), float(d))[0] for s, d in zip(data['wind_spd'][1:], data['wind_dir'][1:])])
                        vad_v = np.array([calculate_wind_components(float(s), float(d))[1] for s, d in zip(data['wind_spd'][1:], data['wind_dir'][1:])])
                        vad_heights = np.array([float(h) for h in data['altitude'][1:]])

                        vad_1km = interpolate_wind_at_height(vad_heights, vad_u, vad_v, 1000.0)
                        if vad_1km:
                            vad_1km_u_val, vad_1km_v_val = vad_1km
                            esterheld_angle = calculate_esterheld_angle(
                                surface_u, surface_v, storm_u, storm_v, vad_1km[0], vad_1km[1])

                        kink = find_kink_point(surface_u, surface_v, vad_u, vad_v, threshold_deg=5.0)
                        if kink:
                            kink_u_val, kink_v_val = kink
                            skoff_angle = calculate_skoff_angle(
                                surface_u, surface_v, storm_u, storm_v, kink[0], kink[1])
                    except:
                        pass
                
                # Calculate shear depth
                shear_depth = None
                shear_magnitude = None
                if metar_data and len(data['wind_spd']) > 1:
                    try:
                        surface_u, surface_v = calculate_wind_components(data['wind_spd'][0], data['wind_dir'][0])
                        
                        # Get the lowest radar point for reference vector
                        radar_u, radar_v = calculate_wind_components(data['wind_spd'][1], data['wind_dir'][1])
                        ref_u, ref_v = radar_u - surface_u, radar_v - surface_v
                        
                        # Find points within 5 degrees of reference vector
                        aligned_heights = []
                        for i in range(1, len(data['wind_spd'])):
                            point_u, point_v = calculate_wind_components(data['wind_spd'][i], data['wind_dir'][i])
                            vector_u, vector_v = point_u - surface_u, point_v - surface_v
                            
                            # Calculate angle between vectors
                            dot_product = ref_u * vector_u + ref_v * vector_v
                            mag_ref = np.sqrt(ref_u**2 + ref_v**2)
                            mag_vec = np.sqrt(vector_u**2 + vector_v**2)
                            
                            if mag_ref > 0 and mag_vec > 0:
                                cos_angle = np.clip(dot_product / (mag_ref * mag_vec), -1.0, 1.0)
                                angle = np.rad2deg(np.arccos(cos_angle))
                                
                                if angle <= 5.0:
                                    aligned_heights.append(data['altitude'][i])
                                else:
                                    break
                        
                        if aligned_heights:
                            shear_depth = max(aligned_heights)
                            # Calculate shear magnitude to this depth
                            final_u, final_v = calculate_wind_components(data['wind_spd'][len(aligned_heights)], data['wind_dir'][len(aligned_heights)])
                            shear_magnitude = np.sqrt((final_u - surface_u)**2 + (final_v - surface_v)**2)
                    except:
                        pass
                
                parameters = {
                    'srh_0_5': round(srh_0_5, 1) if not np.isnan(srh_0_5) else None,
                    'srh_0_1': round(srh_0_1, 1) if not np.isnan(srh_0_1) else None,
                    'srh_0_3': round(srh_0_3, 1) if not np.isnan(srh_0_3) else None,
                    'shear_1km': round(shear_1km, 1) if not np.isnan(shear_1km) else None,
                    'shear_3km': round(shear_3km, 1) if not np.isnan(shear_3km) else None,
                    'shear_6km': round(shear_6km, 1) if not np.isnan(shear_6km) else None,
                    'bunkers': bunkers_info,
                    'esterheld_angle': round(esterheld_angle, 1) if esterheld_angle is not None else None,
                    'skoff_angle': round(skoff_angle, 1) if skoff_angle is not None else None,
                    'kink_point': {'u': kink_u_val, 'v': kink_v_val} if kink_u_val is not None else None,
                    'vad_1km_point': {'u': vad_1km_u_val, 'v': vad_1km_v_val} if vad_1km_u_val is not None else None,
                    'shear_depth': round(shear_depth, 0) if shear_depth is not None else None,
                    'shear_magnitude': round(shear_magnitude, 1) if shear_magnitude is not None else None
                }
            except Exception as e:
                print(f"Error calculating parameters: {e}")
                import traceback
                traceback.print_exc()
        
        return jsonify({
            'image': img_base64,
            'parameters': parameters,
            'success': True
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/reset')
def reset_data():
    """Reset all data"""
    global wind_profile
    wind_profile = WindProfile()
    return jsonify({'success': True})

if __name__ == '__main__':
    # Create temp directory
    os.makedirs("temp_data", exist_ok=True)
    
    # Run the app
    app.run(host='0.0.0.0', port=5000, debug=True)