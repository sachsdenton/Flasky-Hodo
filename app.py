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
from utils import calculate_wind_components
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
        
        # Debug: Print all received parameters
        print(f"Debug: Hodograph parameters received:")
        print(f"  site_id: {site_id}")
        print(f"  storm_direction: {storm_direction}")
        print(f"  storm_speed: {storm_speed}")
        print(f"  metar_direction: {metar_direction}")
        print(f"  metar_speed: {metar_speed}")
        print(f"  show_half_km: {show_half_km}")
        
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
        plotter.plot_profile(wind_profile, height_colors=True, show_half_km=show_half_km)
        
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
        if storm_motion_data:
            storm_u, storm_v = calculate_wind_components(storm_motion_data['speed'], storm_motion_data['direction'])
            ax.plot(storm_u, storm_v, 'rs', markersize=12, label='Storm Motion', zorder=10)
            
        if metar_data:
            metar_u, metar_v = calculate_wind_components(metar_data['speed'], metar_data['direction'])
            ax.plot(metar_u, metar_v, 'ko', markersize=10, label='Surface Wind', zorder=10)
            
        # Add SRH shading and critical angle analysis
        critical_angle_value = None
        if storm_motion_data and metar_data and len(wind_profile.speeds) > 0:
            # Get surface and storm motion components
            surface_u, surface_v = calculate_wind_components(metar_data['speed'], metar_data['direction'])
            storm_u, storm_v = calculate_wind_components(storm_motion_data['speed'], storm_motion_data['direction'])
            
            # Add SRH shading for 0-1km and 0-3km
            try:
                # Prepare wind profile data with surface wind
                u_comp = [surface_u]
                v_comp = [surface_v]
                heights = [0.0]
                
                for i, (speed, direction) in enumerate(zip(wind_profile.speeds, wind_profile.directions)):
                    u, v = calculate_wind_components(speed, direction)
                    u_comp.append(u)
                    v_comp.append(v)
                    heights.append(wind_profile.heights[i])
                
                # Convert to numpy arrays
                u_comp = np.array(u_comp)
                v_comp = np.array(v_comp)
                heights = np.array(heights)
                
                # Create SRH polygon for 0-1km (light green)
                srh_1km_u = []
                srh_1km_v = []
                for i, height in enumerate(heights):
                    if height <= 1000:  # 1km = 1000m
                        srh_1km_u.append(u_comp[i])
                        srh_1km_v.append(v_comp[i])
                
                if len(srh_1km_u) > 2:
                    # Close the polygon by connecting back to storm motion
                    srh_1km_u.append(storm_u)
                    srh_1km_v.append(storm_v)
                    srh_1km_u.append(srh_1km_u[0])  # Close to start
                    srh_1km_v.append(srh_1km_v[0])
                    
                    ax.fill(srh_1km_u, srh_1km_v, color='lightgreen', alpha=0.3, label='SRH 0-1km', zorder=1)
                
                # Create SRH polygon for 0-3km (light blue)
                srh_3km_u = []
                srh_3km_v = []
                for i, height in enumerate(heights):
                    if height <= 3000:  # 3km = 3000m
                        srh_3km_u.append(u_comp[i])
                        srh_3km_v.append(v_comp[i])
                
                if len(srh_3km_u) > 2:
                    # Close the polygon by connecting back to storm motion
                    srh_3km_u.append(storm_u)
                    srh_3km_v.append(storm_v)
                    srh_3km_u.append(srh_3km_u[0])  # Close to start
                    srh_3km_v.append(srh_3km_v[0])
                    
                    ax.fill(srh_3km_u, srh_3km_v, color='lightblue', alpha=0.2, label='SRH 0-3km', zorder=0)
                    
            except Exception as e:
                print(f"Error adding SRH shading: {e}")
            
            # Find points within shear vector (±10 degree window from surface-to-lowest radar point)
            if len(wind_profile.speeds) > 0:
                # Get lowest radar point
                radar_u, radar_v = calculate_wind_components(wind_profile.speeds[0], wind_profile.directions[0])
                
                # Calculate reference vector (surface to lowest radar point)
                ref_u, ref_v = radar_u - surface_u, radar_v - surface_v
                
                # Find all points within ±10 degrees of reference vector
                shear_points_u = [surface_u]
                shear_points_v = [surface_v]
                
                for i, (speed, direction) in enumerate(zip(wind_profile.speeds, wind_profile.directions)):
                    point_u, point_v = calculate_wind_components(speed, direction)
                    vector_u, vector_v = point_u - surface_u, point_v - surface_v
                    
                    # Calculate angle between reference vector and current vector
                    if np.sqrt(ref_u**2 + ref_v**2) > 0 and np.sqrt(vector_u**2 + vector_v**2) > 0:
                        dot_product = ref_u * vector_u + ref_v * vector_v
                        mag_ref = np.sqrt(ref_u**2 + ref_v**2)
                        mag_vec = np.sqrt(vector_u**2 + vector_v**2)
                        cos_angle = np.clip(dot_product / (mag_ref * mag_vec), -1.0, 1.0)
                        angle = np.rad2deg(np.arccos(cos_angle))
                        
                        if angle <= 10.0:  # Within ±10 degrees
                            shear_points_u.append(point_u)
                            shear_points_v.append(point_v)
                        else:
                            break  # Stop at first point outside the window
                
                # Draw shear vector line (thick line through aligned points)
                if len(shear_points_u) > 1:
                    ax.plot(shear_points_u, shear_points_v, 'g-', linewidth=4, alpha=0.7, label='Shear Vector', zorder=8)
                
                # Draw critical angle lines
                # Line from surface to storm motion
                ax.plot([surface_u, storm_u], [surface_v, storm_v], 'r--', linewidth=2, alpha=0.8, label='Surface-Storm', zorder=9)
                
                # Line from surface to end of shear vector
                if len(shear_points_u) > 1:
                    end_u, end_v = shear_points_u[-1], shear_points_v[-1]
                    ax.plot([surface_u, end_u], [surface_v, end_v], 'b--', linewidth=2, alpha=0.8, label='Surface-Shear', zorder=9)
                    
                    # Calculate critical angle for parameter display
                    v1_u, v1_v = storm_u - surface_u, storm_v - surface_v
                    v2_u, v2_v = end_u - surface_u, end_v - surface_v
                    
                    if np.sqrt(v1_u**2 + v1_v**2) > 0 and np.sqrt(v2_u**2 + v2_v**2) > 0:
                        dot_product = v1_u * v2_u + v1_v * v2_v
                        mag1 = np.sqrt(v1_u**2 + v1_v**2)
                        mag2 = np.sqrt(v2_u**2 + v2_v**2)
                        cos_angle = np.clip(dot_product / (mag1 * mag2), -1.0, 1.0)
                        critical_angle_value = np.rad2deg(np.arccos(cos_angle))
                    
                    # SRH values are displayed only in the upper left parameter box
        
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
                
                # Debug the data structure before SRH calculation
                print(f"Debug: param_data structure:")
                print(f"  wind_dir length: {len(param_data['wind_dir'])}")
                print(f"  wind_spd length: {len(param_data['wind_spd'])}")
                print(f"  altitude length: {len(param_data['altitude'])}")
                print(f"  first few wind_dir: {param_data['wind_dir'][:3] if len(param_data['wind_dir']) > 0 else 'empty'}")
                print(f"  first few wind_spd: {param_data['wind_spd'][:3] if len(param_data['wind_spd']) > 0 else 'empty'}")
                print(f"  first few altitude: {param_data['altitude'][:3] if len(param_data['altitude']) > 0 else 'empty'}")
                print(f"  max altitude: {np.max(param_data['altitude']) if len(param_data['altitude']) > 0 else 'empty'}")
                print(f"  altitudes up to 1000m: {np.sum(param_data['altitude'] <= 1000)}")
                print(f"  altitudes up to 3000m: {np.sum(param_data['altitude'] <= 3000)}")
                print(f"  storm_motion_tuple: {storm_motion_tuple}")
                
                # Only calculate SRH if we have storm motion
                if storm_motion_tuple:
                    srh_0_1 = compute_srh(param_data, storm_motion_tuple, 1000)
                    srh_0_3 = compute_srh(param_data, storm_motion_tuple, 3000)
                else:
                    srh_0_1 = np.nan
                    srh_0_3 = np.nan
                shear_1km = compute_shear_mag(param_data, 1000)
                shear_3km = compute_shear_mag(param_data, 3000)
                
                print(f"Debug: Calculated SRH values - srh_0_1: {srh_0_1}, srh_0_3: {srh_0_3}")
                
                # Create parameter text with requested order
                param_text = []
                
                # Wind shear values first
                if not np.isnan(shear_1km):
                    param_text.append(f'0-1km Shear: {shear_1km:.0f} kts')
                if not np.isnan(shear_3km):
                    param_text.append(f'0-3km Shear: {shear_3km:.0f} kts')
                
                # Storm motion (input storm motion)
                if storm_motion_data:
                    param_text.append(f'Storm Motion: {storm_motion_data["direction"]:.0f}°/{storm_motion_data["speed"]:.0f}kts')
                
                # Add Bunkers storm motion
                try:
                    from params import compute_bunkers
                    bunkers_result = compute_bunkers(param_data)
                    if bunkers_result and len(bunkers_result) >= 2:
                        bunkers_rm = bunkers_result[0]
                        param_text.append(f'Bunkers RM: {bunkers_rm[0]:.0f}°/{bunkers_rm[1]:.0f}kts')
                except:
                    pass
                
                # Add critical angle below Bunkers data
                if critical_angle_value is not None:
                    param_text.append(f'Critical Angle: {critical_angle_value:.1f}°')
                
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
                    param_text.append(f'Shear Magnitude: {shear_magnitude_display:.0f} kts')
                if shear_depth_display is not None:
                    param_text.append(f'Shear Depth: {shear_depth_display:.0f} m')
                
                # Always add SRH values after shear parameters (regardless of shear depth availability)
                print(f"Debug: SRH values - srh_0_1: {srh_0_1}, srh_0_3: {srh_0_3}")
                if not np.isnan(srh_0_1):
                    param_text.append(f'SRH 0-1km: {srh_0_1:.0f} m²/s²')
                    print(f"Debug: Added SRH 0-1km to param_text")
                if not np.isnan(srh_0_3):
                    param_text.append(f'SRH 0-3km: {srh_0_3:.0f} m²/s²')
                    print(f"Debug: Added SRH 0-3km to param_text")
                
                # Display parameters text box in upper left corner
                if param_text:
                    param_str = '\n'.join(param_text)
                    ax.text(0.02, 0.98, param_str, transform=ax.transAxes, fontsize=10,
                           verticalalignment='top', bbox=dict(boxstyle="round,pad=0.5", 
                           facecolor="lightblue", alpha=0.8), zorder=12)
                
                # SRH values are now only displayed in the upper left parameter box
            except Exception as e:
                print(f"Error adding parameters to plot: {e}")
                import traceback
                traceback.print_exc()
        
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
                        
                        # Validate values are not NaN
                        if (not np.isnan(bunkers_rm[0]) and not np.isnan(bunkers_rm[1]) and 
                            not np.isnan(bunkers_lm[0]) and not np.isnan(bunkers_lm[1])):
                            bunkers_info = {
                                'right': {'direction': round(float(bunkers_rm[0]), 1), 'speed': round(float(bunkers_rm[1]), 1)},
                                'left': {'direction': round(float(bunkers_lm[0]), 1), 'speed': round(float(bunkers_lm[1]), 1)}
                            }
                        else:
                            bunkers_info = None
                    else:
                        bunkers_info = None
                except:
                    bunkers_info = None
                
                # Calculate critical angle if we have surface wind
                critical_angle = None
                if metar_data and len(data['wind_spd']) > 1:
                    try:
                        surface_u, surface_v = calculate_wind_components(float(data['wind_spd'][0]), float(data['wind_dir'][0]))
                        storm_u, storm_v = calculate_wind_components(storm_motion_data['speed'], storm_motion_data['direction'])
                        radar_u, radar_v = calculate_wind_components(float(data['wind_spd'][1]), float(data['wind_dir'][1]))
                        
                        # Calculate angle between surface-to-storm and surface-to-radar vectors
                        v1_u, v1_v = storm_u - surface_u, storm_v - surface_v
                        v2_u, v2_v = radar_u - surface_u, radar_v - surface_v
                        
                        dot_product = v1_u * v2_u + v1_v * v2_v
                        mag1 = np.sqrt(v1_u**2 + v1_v**2)
                        mag2 = np.sqrt(v2_u**2 + v2_v**2)
                        
                        if mag1 > 0 and mag2 > 0:
                            cos_angle = np.clip(dot_product / (mag1 * mag2), -1.0, 1.0)
                            critical_angle = np.rad2deg(np.arccos(cos_angle))
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
                
                # Helper function to safely round numeric values
                def safe_round(value, decimals=1):
                    if value is None or np.isnan(value) or np.isinf(value):
                        return None
                    return round(float(value), decimals)
                
                parameters = {
                    'srh_0_5': safe_round(srh_0_5, 1),
                    'srh_0_1': safe_round(srh_0_1, 1),
                    'srh_0_3': safe_round(srh_0_3, 1),
                    'shear_1km': safe_round(shear_1km, 1),
                    'shear_3km': safe_round(shear_3km, 1),
                    'shear_6km': safe_round(shear_6km, 1),
                    'bunkers': bunkers_info,
                    'critical_angle': safe_round(critical_angle, 1),
                    'shear_depth': safe_round(shear_depth, 0),
                    'shear_magnitude': safe_round(shear_magnitude, 1)
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