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
        
        if len(wind_profile.heights) == 0:
            return jsonify({'error': 'No wind profile data loaded'}), 400
        
        # Create hodograph plotter
        plotter = HodographPlotter()
        
        # Get site information
        site = get_site_by_id(site_id) if site_id else None
        site_name = site.name if site else None
        
        # Setup plot
        plotter.setup_plot(site_id=site_id, site_name=site_name, valid_time=datetime.now())
        
        # Plot the wind profile
        plotter.plot_profile(wind_profile, height_colors=True, show_half_km=show_half_km)
        
        # Add METAR surface wind if provided
        if metar_direction is not None and metar_speed is not None:
            metar_u, metar_v = calculate_wind_components(metar_speed, metar_direction)
            fig, ax = plotter.get_plot()
            ax.plot(metar_u, metar_v, 'ko', markersize=8, label=f'METAR Surface Wind')
            ax.legend()
        
        # Add storm motion if provided
        storm_motion_data = None
        if storm_direction is not None and storm_speed is not None:
            storm_motion_data = {'direction': storm_direction, 'speed': storm_speed}
            storm_u, storm_v = calculate_wind_components(storm_speed, storm_direction)
            fig, ax = plotter.get_plot()
            ax.plot(storm_u, storm_v, 'rs', markersize=10, label=f'Storm Motion')
            ax.legend()
        
        # Save plot to base64 string
        img_buffer = io.BytesIO()
        fig, ax = plotter.get_plot()
        plt.savefig(img_buffer, format='png', dpi=150, bbox_inches='tight')
        img_buffer.seek(0)
        img_base64 = base64.b64encode(img_buffer.getvalue()).decode()
        plt.close()
        
        # Calculate parameters if we have storm motion
        parameters = {}
        if storm_motion_data:
            try:
                # Prepare data for parameter calculations
                data = {
                    'u': np.array([calculate_wind_components(s, d)[0] for s, d in zip(wind_profile.speeds, wind_profile.directions)]),
                    'v': np.array([calculate_wind_components(s, d)[1] for s, d in zip(wind_profile.speeds, wind_profile.directions)]),
                    'height': wind_profile.heights
                }
                
                # Calculate SRH
                srh_0_5 = compute_srh(data, storm_motion_data, 500)
                srh_0_1 = compute_srh(data, storm_motion_data, 1000)
                srh_0_3 = compute_srh(data, storm_motion_data, 3000)
                
                parameters = {
                    'srh_0_5': round(srh_0_5, 1),
                    'srh_0_1': round(srh_0_1, 1),
                    'srh_0_3': round(srh_0_3, 1)
                }
            except Exception as e:
                print(f"Error calculating parameters: {e}")
        
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