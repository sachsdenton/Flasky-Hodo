from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import json
import os
import io
import base64
import threading
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime
from typing import Optional, Dict, Any, Tuple

# Import existing modules
from hodograph_plotter import HodographPlotter
from data_processor import WindProfile
from radar_sites import get_sorted_sites, get_site_by_id
from utils import calculate_wind_components, calculate_esterheld_angle, calculate_skoff_angle, find_kink_point, interpolate_wind_at_height
from metar_utils import get_metar
from params import compute_bunkers, compute_srh, compute_shear_mag
from map_component import load_metar_sites, calculate_distance
from nexrad_fetcher import NEXRADFetcher
from warning_utils import fetch_active_warnings

app = Flask(__name__)
CORS(app)

try:
    app.json.allow_nan = False
except AttributeError:
    pass

# Global variables for caching
wind_profile = WindProfile()
nexrad_fetcher = NEXRADFetcher()

# In-memory cache for per-frame payloads.
# Key: (mode, site_id, file_id, storm_dir, storm_spd, metar_dir, metar_spd, metar_station, show_half_km)
_frame_payload_cache: Dict[Tuple, Any] = {}
_frame_payload_cache_lock = threading.Lock()
_FRAME_CACHE_MAX = 256


def _frame_cache_get(key):
    with _frame_payload_cache_lock:
        return _frame_payload_cache.get(key)


def _frame_cache_set(key, value):
    with _frame_payload_cache_lock:
        if len(_frame_payload_cache) >= _FRAME_CACHE_MAX:
            # Drop a random entry to keep cache bounded
            _frame_payload_cache.pop(next(iter(_frame_payload_cache)))
        _frame_payload_cache[key] = value


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


# ---------------------------------------------------------------------------
# Shared per-frame computation helpers
# ---------------------------------------------------------------------------

def _sanitize_for_json(value):
    """Recursively replace NaN / Infinity values with None so the result is
    valid JSON (Flask's default jsonify emits the literal ``NaN`` which
    browsers reject)."""
    import math
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(value, dict):
        return {k: _sanitize_for_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize_for_json(v) for v in value]
    return value


def _build_wind_profile_payload(wp, site_id, storm_direction, storm_speed,
                                 metar_direction, metar_speed, metar_station):
    """Build the JSON payload returned by the wind-profile endpoints.

    Identical in shape to the original /api/wind-profile-data response.
    """
    if len(wp.heights) == 0:
        return {'error': 'No wind profile data loaded'}

    site = get_site_by_id(site_id) if site_id else None

    u_components = []
    v_components = []
    for speed, direction in zip(wp.speeds, wp.directions):
        u, v = calculate_wind_components(speed, direction)
        u_components.append(float(u))
        v_components.append(float(v))

    valid_time = None
    if hasattr(wp, 'times') and len(wp.times) > 0:
        vt = wp.times[0]
        if hasattr(vt, 'strftime'):
            valid_time = vt.strftime('%Y-%m-%d %H:%M UTC')

    parameters = {}
    storm_motion_tuple = None
    if storm_direction is not None and storm_speed is not None:
        storm_motion_tuple = (storm_direction, storm_speed)
        storm_u, storm_v = calculate_wind_components(storm_speed, storm_direction)

        param_data = {
            'wind_dir': np.array(wp.directions),
            'wind_spd': np.array(wp.speeds),
            'altitude': np.array(wp.heights)
        }

        if metar_direction is not None and metar_speed is not None:
            param_data['wind_dir'] = np.insert(param_data['wind_dir'], 0, metar_direction)
            param_data['wind_spd'] = np.insert(param_data['wind_spd'], 0, metar_speed)
            param_data['altitude'] = np.insert(param_data['altitude'], 0, 0.0)

        try:
            srh_0_500 = compute_srh(param_data, storm_motion_tuple, 0.5)
            srh_0_1 = compute_srh(param_data, storm_motion_tuple, 1)
            srh_0_3 = compute_srh(param_data, storm_motion_tuple, 3)
            shear_1km = compute_shear_mag(param_data, 1)
            shear_3km = compute_shear_mag(param_data, 3)

            parameters['srh_0_500'] = round(float(srh_0_500), 1) if not np.isnan(srh_0_500) else None
            parameters['srh_0_1'] = round(float(srh_0_1), 1) if not np.isnan(srh_0_1) else None
            parameters['srh_0_3'] = round(float(srh_0_3), 1) if not np.isnan(srh_0_3) else None
            parameters['shear_1km'] = round(float(shear_1km), 1) if not np.isnan(shear_1km) else None
            parameters['shear_3km'] = round(float(shear_3km), 1) if not np.isnan(shear_3km) else None

            try:
                bunkers_result = compute_bunkers(param_data)
                if bunkers_result and len(bunkers_result) >= 3:
                    parameters['bunkers_rm'] = {'direction': float(bunkers_result[0][0]), 'speed': float(bunkers_result[0][1])}
                    parameters['bunkers_lm'] = {'direction': float(bunkers_result[1][0]), 'speed': float(bunkers_result[1][1])}
                    parameters['mean_wind'] = {'direction': float(bunkers_result[2][0]), 'speed': float(bunkers_result[2][1])}
            except Exception:
                pass

            try:
                if parameters.get('bunkers_rm') and parameters.get('mean_wind'):
                    rm_dir = parameters['bunkers_rm']['direction']
                    rm_spd = parameters['bunkers_rm']['speed']
                    mw_dir = parameters['mean_wind']['direction']
                    mw_spd = parameters['mean_wind']['speed']
                    rm_u, rm_v = calculate_wind_components(rm_spd, rm_dir)
                    mw_u, mw_v = calculate_wind_components(mw_spd, mw_dir)
                    dtm_u = 2 * rm_u - mw_u
                    dtm_v = 2 * rm_v - mw_v
                    dtm_spd = float(np.sqrt(dtm_u**2 + dtm_v**2))
                    dtm_dir_rad = np.arctan2(-dtm_u, -dtm_v)
                    dtm_dir = float(np.degrees(dtm_dir_rad)) % 360
                    parameters['deviant_tornado'] = {'direction': round(dtm_dir, 0), 'speed': round(dtm_spd, 0)}
            except Exception:
                pass

            if metar_direction is not None and metar_speed is not None and len(param_data['wind_spd']) > 1:
                try:
                    surface_u, surface_v = calculate_wind_components(float(param_data['wind_spd'][0]), float(param_data['wind_dir'][0]))

                    vad_u_arr = np.array([calculate_wind_components(float(s), float(d))[0] for s, d in zip(param_data['wind_spd'][1:], param_data['wind_dir'][1:])])
                    vad_v_arr = np.array([calculate_wind_components(float(s), float(d))[1] for s, d in zip(param_data['wind_spd'][1:], param_data['wind_dir'][1:])])
                    vad_h_arr = np.array([float(h) for h in param_data['altitude'][1:]])

                    vad_half_km = interpolate_wind_at_height(vad_h_arr, vad_u_arr, vad_v_arr, 0.5)
                    if vad_half_km:
                        ea = calculate_esterheld_angle(surface_u, surface_v, storm_u, storm_v, vad_half_km[0], vad_half_km[1])
                        if ea is not None:
                            parameters['esterheld_angle'] = round(ea, 1)
                        parameters['vad_half_km_point'] = {'u': vad_half_km[0], 'v': vad_half_km[1]}

                    kink = find_kink_point(surface_u, surface_v, vad_u_arr, vad_v_arr, threshold_deg=5.0)
                    if kink:
                        sa = calculate_skoff_angle(surface_u, surface_v, storm_u, storm_v, kink[0], kink[1])
                        if sa is not None:
                            parameters['skoff_angle'] = round(sa, 1)
                        parameters['kink_point'] = {'u': kink[0], 'v': kink[1]}
                except Exception:
                    pass
        except Exception as e:
            print(f"Error computing parameters: {e}")

    return _sanitize_for_json({
        'u_components': u_components,
        'v_components': v_components,
        'heights': [float(h) for h in wp.heights],
        'speeds': [float(s) for s in wp.speeds],
        'directions': [float(d) for d in wp.directions],
        'max_speed': float(np.max(wp.speeds)) if len(wp.speeds) > 0 else 50,
        'site_id': site_id,
        'site_name': site.name if site else '',
        'valid_time': valid_time,
        'parameters': parameters
    })


def _build_hodograph_image_payload(wp, site_id, plot_type, show_half_km,
                                    storm_direction, storm_speed,
                                    metar_direction, metar_speed, metar_station,
                                    show_speed_rings=True, show_height_markers=True,
                                    show_srh=True, show_shear_vector=True,
                                    show_critical_angle=True,
                                    show_storm_motion_marker=True,
                                    show_surface_wind_marker=True,
                                    show_param_text=True, zoom_level=1.0,
                                    fetch_metar_obs_time=True):
    """Render a matplotlib hodograph image for the given wind profile.

    Returns a dict containing ``image`` (base64 PNG), ``parameters``, and
    ``valid_time`` (string).
    """
    if len(wp.heights) == 0:
        return {'error': 'No wind profile data loaded'}

    plotter = HodographPlotter()

    site = get_site_by_id(site_id) if site_id else None
    site_name = site.name if site else None

    # Use the actual VAD valid time when available so titles are correct
    # for historical frames.
    valid_dt = None
    if hasattr(wp, 'times') and len(wp.times) > 0:
        candidate = wp.times[0]
        if hasattr(candidate, 'strftime'):
            valid_dt = candidate
    if valid_dt is None:
        valid_dt = datetime.now()

    plotter.setup_plot(site_id=site_id, site_name=site_name, valid_time=valid_dt)

    plotter.plot_profile(wp, height_colors=True, show_half_km=show_half_km,
                         show_height_markers=show_height_markers, show_speed_rings=show_speed_rings,
                         zoom_level=zoom_level)

    storm_motion_data = None
    storm_motion_tuple = None
    metar_data = None

    if storm_direction is not None and storm_speed is not None:
        storm_motion_data = {'direction': storm_direction, 'speed': storm_speed}
        storm_motion_tuple = (storm_direction, storm_speed)

    if metar_direction is not None and metar_speed is not None:
        metar_data = {'direction': metar_direction, 'speed': metar_speed}

    fig, ax = plotter.get_plot()

    if storm_motion_data and show_storm_motion_marker:
        storm_u, storm_v = calculate_wind_components(storm_motion_data['speed'], storm_motion_data['direction'])
        ax.plot(storm_u, storm_v, 'rs', markersize=12, label='Storm Motion', zorder=10)

    if metar_data and show_surface_wind_marker:
        metar_u, metar_v = calculate_wind_components(metar_data['speed'], metar_data['direction'])
        ax.plot(metar_u, metar_v, 'ko', markersize=10, label='Surface Wind', zorder=10)

    esterheld_angle_value = None
    skoff_angle_value = None
    if storm_motion_data and metar_data and len(wp.speeds) > 0:
        surface_u, surface_v = calculate_wind_components(metar_data['speed'], metar_data['direction'])
        storm_u, storm_v = calculate_wind_components(storm_motion_data['speed'], storm_motion_data['direction'])

        try:
            u_comp = [surface_u]
            v_comp = [surface_v]
            heights = [0.0]

            for i, (speed, direction) in enumerate(zip(wp.speeds, wp.directions)):
                u, v = calculate_wind_components(speed, direction)
                u_comp.append(u)
                v_comp.append(v)
                heights.append(wp.heights[i])

            u_comp = np.array(u_comp)
            v_comp = np.array(v_comp)
            heights = np.array(heights)

            if show_srh:
                for limit, color, alpha, label, zorder in [
                    (0.5, 'orange', 0.25, 'SRH 0-0.5km', 2),
                    (1.0, 'lightgreen', 0.3, 'SRH 0-1km', 1),
                    (3.0, 'lightblue', 0.2, 'SRH 0-3km', 0),
                ]:
                    poly_u = []
                    poly_v = []
                    for i, height in enumerate(heights):
                        if height <= limit:
                            poly_u.append(u_comp[i])
                            poly_v.append(v_comp[i])
                    if len(poly_u) > 2:
                        poly_u.append(storm_u)
                        poly_v.append(storm_v)
                        poly_u.append(poly_u[0])
                        poly_v.append(poly_v[0])
                        ax.fill(poly_u, poly_v, color=color, alpha=alpha, label=label, zorder=zorder)
        except Exception as e:
            print(f"Error adding SRH shading: {e}")

        if len(wp.speeds) > 0:
            radar_u, radar_v = calculate_wind_components(wp.speeds[0], wp.directions[0])
            ref_u, ref_v = radar_u - surface_u, radar_v - surface_v

            shear_points_u = [surface_u]
            shear_points_v = [surface_v]

            for i, (speed, direction) in enumerate(zip(wp.speeds, wp.directions)):
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

            if show_shear_vector and len(shear_points_u) > 1:
                ax.plot(shear_points_u, shear_points_v, 'g-', linewidth=4, alpha=0.7, label='Shear Vector', zorder=8)

            vad_u = np.array([calculate_wind_components(s, d)[0] for s, d in zip(wp.speeds, wp.directions)])
            vad_v = np.array([calculate_wind_components(s, d)[1] for s, d in zip(wp.speeds, wp.directions)])
            vad_heights_km = np.array(wp.heights)

            vad_half_km = interpolate_wind_at_height(vad_heights_km, vad_u, vad_v, 0.5)
            if vad_half_km:
                esterheld_angle_value = calculate_esterheld_angle(
                    surface_u, surface_v, storm_u, storm_v, vad_half_km[0], vad_half_km[1])

            kink = find_kink_point(surface_u, surface_v, vad_u, vad_v, threshold_deg=5.0)
            if kink:
                skoff_angle_value = calculate_skoff_angle(
                    surface_u, surface_v, storm_u, storm_v, kink[0], kink[1])

            if show_critical_angle:
                ax.plot([surface_u, storm_u], [surface_v, storm_v], 'r--', linewidth=2, alpha=0.8, label='Surface-Storm', zorder=9)

                if vad_half_km and esterheld_angle_value is not None:
                    ax.plot([surface_u, vad_half_km[0]], [surface_v, vad_half_km[1]], 'b--', linewidth=2, alpha=0.8, label='Esterheld (0.5km)', zorder=9)

                if kink and skoff_angle_value is not None:
                    ax.plot([surface_u, kink[0]], [surface_v, kink[1]], 'm--', linewidth=2, alpha=0.8, label='Skoff (kink)', zorder=9)

    # Parameter text overlay
    if storm_motion_data:
        param_data = {
            'wind_dir': np.array(wp.directions),
            'wind_spd': np.array(wp.speeds),
            'altitude': np.array(wp.heights)
        }

        if metar_data:
            param_data['wind_dir'] = np.insert(param_data['wind_dir'], 0, metar_data['direction'])
            param_data['wind_spd'] = np.insert(param_data['wind_spd'], 0, metar_data['speed'])
            param_data['altitude'] = np.insert(param_data['altitude'], 0, 0.0)

        try:
            srh_0_1 = compute_srh(param_data, storm_motion_tuple, 1)
            srh_0_3 = compute_srh(param_data, storm_motion_tuple, 3)
            shear_1km = compute_shear_mag(param_data, 1)
            shear_3km = compute_shear_mag(param_data, 3)

            param_text = []

            if not np.isnan(shear_1km):
                param_text.append(f'0-1km Shear: {shear_1km:.0f} kt')
            if not np.isnan(shear_3km):
                param_text.append(f'0-3km Shear: {shear_3km:.0f} kt')

            if storm_motion_data:
                param_text.append(f'Storm Motion: {storm_motion_data["direction"]:.0f}°/{storm_motion_data["speed"]:.0f}kt')

            try:
                bunkers_result = compute_bunkers(param_data)
                if bunkers_result and len(bunkers_result) >= 2:
                    bunkers_rm = bunkers_result[0]
                    param_text.append(f'Bunkers RM: {bunkers_rm[0]:.0f}°/{bunkers_rm[1]:.0f}kt')
            except Exception:
                pass

            if esterheld_angle_value is not None:
                param_text.append(f'Esterheld Angle: {esterheld_angle_value:.1f}°')
            if skoff_angle_value is not None:
                param_text.append(f'Skoff Angle: {skoff_angle_value:.1f}°')

            shear_magnitude_display = None
            shear_depth_display = None
            if metar_data and len(param_data['wind_spd']) > 1:
                try:
                    surface_u, surface_v = calculate_wind_components(float(param_data['wind_spd'][0]), float(param_data['wind_dir'][0]))
                    radar_u, radar_v = calculate_wind_components(float(param_data['wind_spd'][1]), float(param_data['wind_dir'][1]))
                    ref_u, ref_v = radar_u - surface_u, radar_v - surface_v

                    aligned_heights = []
                    aligned_indices = []
                    for i in range(1, len(param_data['wind_spd'])):
                        point_u, point_v = calculate_wind_components(float(param_data['wind_spd'][i]), float(param_data['wind_dir'][i]))
                        vector_u, vector_v = point_u - surface_u, point_v - surface_v

                        dot_product = ref_u * vector_u + ref_v * vector_v
                        mag_ref = np.sqrt(ref_u**2 + ref_v**2)
                        mag_vec = np.sqrt(vector_u**2 + vector_v**2)

                        if mag_ref > 0 and mag_vec > 0:
                            cos_angle = np.clip(dot_product / (mag_ref * mag_vec), -1.0, 1.0)
                            angle = np.rad2deg(np.arccos(cos_angle))
                            if angle <= 5.0:
                                aligned_heights.append(param_data['altitude'][i])
                                aligned_indices.append(i)

                    if aligned_heights and len(aligned_indices) > 0:
                        raw_depth = max(aligned_heights)
                        if raw_depth < 50:
                            shear_depth_display = max(raw_depth, len(aligned_indices) * 200)
                        else:
                            shear_depth_display = raw_depth
                        final_index = aligned_indices[-1]
                        final_u, final_v = calculate_wind_components(float(param_data['wind_spd'][final_index]), float(param_data['wind_dir'][final_index]))
                        shear_magnitude_display = np.sqrt((final_u - surface_u)**2 + (final_v - surface_v)**2)
                except Exception as e:
                    print(f"Error calculating shear parameters: {e}")

            if shear_magnitude_display is not None:
                param_text.append(f'Shear Magnitude: {shear_magnitude_display:.1f} kt')
            if shear_depth_display is not None:
                param_text.append(f'Shear Depth: {shear_depth_display:.0f} m')

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

    # Title block
    title_lines = []
    if site:
        title_lines.append(f'{site.id} - {site.name.upper()}')

    if hasattr(wp, 'times') and len(wp.times) > 0:
        vad_time = wp.times[0]
        if hasattr(vad_time, 'strftime'):
            title_lines.append(f'Valid: {vad_time.strftime("%Y-%m-%d %H:%M")}UTC')
        else:
            title_lines.append('Valid: VAD Data Available')
    else:
        title_lines.append(f'Valid: {datetime.now().strftime("%Y-%m-%d %H:%M")}UTC')

    title_lines.append('')

    if metar_data:
        metar_station_id = metar_station or 'METAR'
        obs_str = None
        if fetch_metar_obs_time and metar_station:
            try:
                import requests
                metar_url = f"https://aviationweather.gov/api/data/metar?ids={metar_station_id}&format=json"
                response = requests.get(metar_url, timeout=5)
                if response.status_code == 200:
                    metar_json = response.json()
                    if metar_json:
                        obs_time = metar_json[0].get('reportTime', '')
                        if obs_time:
                            try:
                                obs_dt = datetime.fromisoformat(obs_time.replace('Z', '+00:00'))
                                obs_str = obs_dt.strftime('%H%M')
                            except Exception:
                                pass
            except Exception:
                pass
        if obs_str:
            title_lines.append(f'Surface Wind {metar_data["direction"]:.0f}/{metar_data["speed"]:.0f} ({metar_station_id} {obs_str}UTC)')
        else:
            title_lines.append(f'Surface Wind {metar_data["direction"]:.0f}/{metar_data["speed"]:.0f} ({metar_station_id})')

    title_text = '\n'.join(title_lines)
    ax.set_title(title_text, fontsize=12, fontweight='bold', pad=20, loc='center')

    ax.legend(loc='upper right', fontsize=9)

    img_buffer = io.BytesIO()
    plt.savefig(img_buffer, format='png', dpi=150, bbox_inches='tight')
    img_buffer.seek(0)
    img_base64 = base64.b64encode(img_buffer.getvalue()).decode()
    plt.close()

    # Build the same parameters dict for the Standard mode response
    parameters = {}
    if storm_motion_data:
        try:
            data = {
                'wind_dir': np.array(wp.directions),
                'wind_spd': np.array(wp.speeds),
                'altitude': np.array(wp.heights)
            }

            if metar_data:
                data['wind_dir'] = np.insert(data['wind_dir'], 0, metar_data['direction'])
                data['wind_spd'] = np.insert(data['wind_spd'], 0, metar_data['speed'])
                data['altitude'] = np.insert(data['altitude'], 0, 0.0)

            srh_0_5 = compute_srh(data, storm_motion_tuple, 0.5)
            srh_0_1 = compute_srh(data, storm_motion_tuple, 1)
            srh_0_3 = compute_srh(data, storm_motion_tuple, 3)

            shear_1km = compute_shear_mag(data, 1)
            shear_3km = compute_shear_mag(data, 3)
            shear_6km = compute_shear_mag(data, 6)

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
            except Exception:
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

                    vad_half_km = interpolate_wind_at_height(vad_heights, vad_u, vad_v, 0.5)
                    if vad_half_km:
                        vad_1km_u_val, vad_1km_v_val = vad_half_km
                        esterheld_angle = calculate_esterheld_angle(
                            surface_u, surface_v, storm_u, storm_v, vad_half_km[0], vad_half_km[1])

                    kink = find_kink_point(surface_u, surface_v, vad_u, vad_v, threshold_deg=5.0)
                    if kink:
                        kink_u_val, kink_v_val = kink
                        skoff_angle = calculate_skoff_angle(
                            surface_u, surface_v, storm_u, storm_v, kink[0], kink[1])
                except Exception:
                    pass

            shear_depth = None
            shear_magnitude = None
            if metar_data and len(data['wind_spd']) > 1:
                try:
                    surface_u, surface_v = calculate_wind_components(data['wind_spd'][0], data['wind_dir'][0])
                    radar_u, radar_v = calculate_wind_components(data['wind_spd'][1], data['wind_dir'][1])
                    ref_u, ref_v = radar_u - surface_u, radar_v - surface_v

                    aligned_heights = []
                    for i in range(1, len(data['wind_spd'])):
                        point_u, point_v = calculate_wind_components(data['wind_spd'][i], data['wind_dir'][i])
                        vector_u, vector_v = point_u - surface_u, point_v - surface_v

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
                        final_u, final_v = calculate_wind_components(data['wind_spd'][len(aligned_heights)], data['wind_dir'][len(aligned_heights)])
                        shear_magnitude = np.sqrt((final_u - surface_u)**2 + (final_v - surface_v)**2)
                except Exception:
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

    valid_time_str = None
    if hasattr(wp, 'times') and len(wp.times) > 0:
        vt = wp.times[0]
        if hasattr(vt, 'strftime'):
            valid_time_str = vt.strftime('%Y-%m-%d %H:%M UTC')

    return _sanitize_for_json({
        'image': img_base64,
        'parameters': parameters,
        'valid_time': valid_time_str,
        'success': True
    })


def _load_wind_profile_from_path(file_path: str) -> Optional[WindProfile]:
    wp = WindProfile()
    if not wp.load_from_nexrad(file_path):
        return None
    return wp


def _common_request_motion_inputs():
    """Pull the storm motion + METAR fields from the current request."""
    storm_direction = request.args.get('storm_direction', type=float)
    storm_speed = request.args.get('storm_speed', type=float)
    metar_direction = request.args.get('metar_direction', type=float)
    metar_speed = request.args.get('metar_speed', type=float)
    metar_station = request.args.get('metar_station', '')
    return storm_direction, storm_speed, metar_direction, metar_speed, metar_station


# ---------------------------------------------------------------------------
# Existing routes — now backed by the shared helpers
# ---------------------------------------------------------------------------

@app.route('/api/wind-profile-data')
def get_wind_profile_data():
    """Return raw wind profile data for interactive client-side rendering"""
    global wind_profile

    try:
        if len(wind_profile.heights) == 0:
            return jsonify({'error': 'No wind profile data loaded'}), 400

        site_id = request.args.get('site_id', '')
        storm_direction, storm_speed, metar_direction, metar_speed, metar_station = _common_request_motion_inputs()

        payload = _build_wind_profile_payload(
            wind_profile, site_id, storm_direction, storm_speed,
            metar_direction, metar_speed, metar_station
        )
        if 'error' in payload:
            return jsonify(payload), 400
        return jsonify(payload)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/hodograph')
def generate_hodograph():
    """Generate hodograph plot"""
    global wind_profile

    try:
        plot_type = request.args.get('type', 'Standard')
        show_half_km = request.args.get('show_half_km', 'true').lower() == 'true'
        site_id = request.args.get('site_id', '')

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

        storm_direction, storm_speed, metar_direction, metar_speed, metar_station = _common_request_motion_inputs()

        payload = _build_hodograph_image_payload(
            wind_profile, site_id, plot_type, show_half_km,
            storm_direction, storm_speed, metar_direction, metar_speed, metar_station,
            show_speed_rings=show_speed_rings, show_height_markers=show_height_markers,
            show_srh=show_srh, show_shear_vector=show_shear_vector,
            show_critical_angle=show_critical_angle,
            show_storm_motion_marker=show_storm_motion_marker,
            show_surface_wind_marker=show_surface_wind_marker,
            show_param_text=show_param_text, zoom_level=zoom_level
        )
        if 'error' in payload:
            return jsonify(payload), 400
        return jsonify(payload)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ---------------------------------------------------------------------------
# History / per-frame endpoints (used by the loop scrubber)
# ---------------------------------------------------------------------------

@app.route('/api/vad-history/<site_id>')
def get_vad_history(site_id):
    """Return ordered metadata for the most recent N VAD scans at the site."""
    try:
        try:
            count = int(request.args.get('count', 7))
        except ValueError:
            count = 7
        count = max(1, min(count, 20))

        frames = nexrad_fetcher.fetch_recent(site_id.upper(), count=count)
        return jsonify({
            'site_id': site_id.upper(),
            'frames': [
                {
                    'file_id': f['file_id'],
                    'valid_time': f['valid_time'].strftime('%Y-%m-%d %H:%M UTC')
                        if hasattr(f['valid_time'], 'strftime') else str(f['valid_time'])
                }
                for f in frames
            ]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/wind-profile-frame/<site_id>/<file_id>')
def get_wind_profile_frame(site_id, file_id):
    """Per-frame wind profile JSON for a historical scan."""
    try:
        site_id = site_id.upper()
        storm_direction, storm_speed, metar_direction, metar_speed, metar_station = _common_request_motion_inputs()

        cache_key = (
            'wind_profile', site_id, file_id,
            storm_direction, storm_speed,
            metar_direction, metar_speed, metar_station,
            None
        )
        cached = _frame_cache_get(cache_key)
        if cached is not None:
            return jsonify(cached)

        file_path = nexrad_fetcher.get_frame_path(site_id, file_id)
        if not file_path or not os.path.exists(file_path):
            return jsonify({'error': 'Frame not available'}), 404

        wp = _load_wind_profile_from_path(file_path)
        if wp is None:
            return jsonify({'error': 'Failed to load frame'}), 500

        payload = _build_wind_profile_payload(
            wp, site_id, storm_direction, storm_speed,
            metar_direction, metar_speed, metar_station
        )
        if 'error' in payload:
            return jsonify(payload), 400

        payload['file_id'] = file_id
        _frame_cache_set(cache_key, payload)
        return jsonify(payload)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/hodograph-frame/<site_id>/<file_id>')
def get_hodograph_frame(site_id, file_id):
    """Per-frame hodograph image (Standard mode) for a historical scan."""
    try:
        site_id = site_id.upper()
        show_half_km = request.args.get('show_half_km', 'true').lower() == 'true'
        storm_direction, storm_speed, metar_direction, metar_speed, metar_station = _common_request_motion_inputs()

        cache_key = (
            'hodograph', site_id, file_id,
            storm_direction, storm_speed,
            metar_direction, metar_speed, metar_station,
            show_half_km
        )
        cached = _frame_cache_get(cache_key)
        if cached is not None:
            return jsonify(cached)

        file_path = nexrad_fetcher.get_frame_path(site_id, file_id)
        if not file_path or not os.path.exists(file_path):
            return jsonify({'error': 'Frame not available'}), 404

        wp = _load_wind_profile_from_path(file_path)
        if wp is None:
            return jsonify({'error': 'Failed to load frame'}), 500

        payload = _build_hodograph_image_payload(
            wp, site_id, 'Standard', show_half_km,
            storm_direction, storm_speed, metar_direction, metar_speed, metar_station,
            fetch_metar_obs_time=False
        )
        if 'error' in payload:
            return jsonify(payload), 400

        payload['file_id'] = file_id
        _frame_cache_set(cache_key, payload)
        return jsonify(payload)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/reset')
def reset_data():
    """Reset all data"""
    global wind_profile
    wind_profile = WindProfile()
    with _frame_payload_cache_lock:
        _frame_payload_cache.clear()
    return jsonify({'success': True})

if __name__ == '__main__':
    # Create temp directory
    os.makedirs("temp_data", exist_ok=True)
    
    # Run the app
    app.run(host='0.0.0.0', port=5000, debug=True)
