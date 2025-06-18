
import numpy as np
from utils import calculate_wind_components

# Aliasing calculate_wind_components for backward compatibility
# This avoids duplicate implementations of the same functionality
def vec2comp(wdir, wspd):
    return calculate_wind_components(wspd, wdir)

def comp2vec(u, v):
    vmag = np.hypot(u, v)
    vdir = 90 - np.degrees(np.arctan2(-v, -u))
    vdir = np.where(vdir < 0, vdir + 360, vdir)
    vdir = np.where(vdir >= 360, vdir - 360, vdir)
    return vdir, vmag

def interp(u, v, altitude, hght):
    u_hght = np.interp(hght, altitude, u, left=np.nan, right=np.nan)
    v_hght = np.interp(hght, altitude, v, left=np.nan, right=np.nan)
    return u_hght, v_hght


def _clip_profile(prof, alt, clip_alt, intrp_prof):
    try:
        idx_clip = np.where((alt[:-1] <= clip_alt) & (alt[1:] > clip_alt))[0][0]
    except IndexError:
        return np.nan * np.ones(prof.size)

    prof_clip = prof[:(idx_clip + 1)]
    prof_clip = np.append(prof_clip, intrp_prof)

    return np.array(prof_clip)


def compute_shear_mag(data, hght):
    u, v = vec2comp(data['wind_dir'], data['wind_spd'])
    u = np.array(u)
    v = np.array(v)
    u_hght, v_hght = interp(u, v, data['altitude'], hght)
    return np.hypot(u_hght - u[0], v_hght - v[0])


def compute_srh(data, storm_motion, hght):
    """
    Calculate Storm Relative Helicity (SRH) for a given layer depth.
    Using the standard meteorological definition.
    """
    try:
        # Extract wind data
        wind_dir = np.array(data['wind_dir'])
        wind_spd = np.array(data['wind_spd'])
        altitudes = np.array(data['altitude']) 
        
        # Check minimum data requirements
        if len(wind_dir) < 2 or len(wind_spd) < 2:
            return np.nan
            
        # Convert wind to u,v components (meteorological convention)
        u = -wind_spd * np.sin(np.radians(wind_dir))  # u component (east-west)
        v = -wind_spd * np.cos(np.radians(wind_dir))  # v component (north-south)
        
        # Get storm motion u,v components
        storm_dir, storm_spd = storm_motion
        storm_u = -storm_spd * np.sin(np.radians(storm_dir))
        storm_v = -storm_spd * np.cos(np.radians(storm_dir))
        
        # Calculate storm-relative wind components
        rel_u = u - storm_u
        rel_v = v - storm_v
        
        # Find data within the specified height layer
        valid_mask = (altitudes >= 0) & (altitudes <= hght)
        if np.sum(valid_mask) < 2:
            return np.nan
            
        # Extract layer data
        layer_u = rel_u[valid_mask]
        layer_v = rel_v[valid_mask]
        layer_z = altitudes[valid_mask]
        
        # Calculate SRH using finite difference approximation
        srh_total = 0.0
        
        for i in range(len(layer_z) - 1):
            # Height difference
            dz = layer_z[i+1] - layer_z[i]
            if dz <= 0:
                continue
                
            # Wind differences
            du = layer_u[i+1] - layer_u[i]
            dv = layer_v[i+1] - layer_v[i]
            
            # Average storm-relative wind in layer
            avg_u = (layer_u[i] + layer_u[i+1]) / 2.0
            avg_v = (layer_v[i] + layer_v[i+1]) / 2.0
            
            # SRH increment: (V-C) × (dV/dz) * dz
            # Cross product in 2D: u*dv - v*du
            srh_increment = avg_u * dv - avg_v * du
            srh_total += srh_increment
            
        return srh_total
        
    except Exception as e:
        print(f"Error in SRH calculation: {e}")
        return np.nan


def compute_bunkers(data):
    d = 7.5 * 1.94     # Deviation value emperically derived as 7.5 m/s
    hght = 6
                
    # SFC-6km Mean Wind
    u, v = vec2comp(data['wind_dir'], data['wind_spd'])
    u_hght, v_hght = interp(u, v, data['altitude'], hght)
    u_clip = _clip_profile(u, data['altitude'], hght, u_hght)
    v_clip = _clip_profile(v, data['altitude'], hght, v_hght)

    mnu6 = u_clip.mean()
    mnv6 = v_clip.mean()

    # SFC-6km Shear Vector
    shru = u_hght - u[0]
    shrv = v_hght - v[0]

    # Bunkers Right Motion
    tmp = d / np.hypot(shru, shrv)
    rstu = mnu6 + (tmp * shrv)
    rstv = mnv6 - (tmp * shru)
    lstu = mnu6 - (tmp * shrv)
    lstv = mnv6 + (tmp * shru)

    return comp2vec(rstu, rstv), comp2vec(lstu, lstv), comp2vec(mnu6, mnv6)
    

def compute_crit_angl(data, storm_motion):
    u, v = vec2comp(data['wind_dir'], data['wind_spd'])
    storm_u, storm_v = vec2comp(*storm_motion)

    u_05km, v_05km = interp(u, v, data['altitude'], 0.5)

    base_u = storm_u - u[0]
    base_v = storm_v - v[0]

    ang_u = u_05km - u[0]
    ang_v = v_05km - v[0]

    len_base = np.hypot(base_u, base_v)
    len_ang = np.hypot(ang_u, ang_v)

    base_dot_ang = base_u * ang_u + base_v * ang_v
    return np.degrees(np.arccos(base_dot_ang / (len_base * len_ang)))


def compute_parameters(data, storm_motion):
    params = {}

    try:
        params['bunkers_right'], params['bunkers_left'], params['mean_wind'] = compute_bunkers(data)
    except (IndexError, ValueError):
        params['bunkers_right'] = (np.nan, np.nan)
        params['bunkers_left'] = (np.nan, np.nan)
        params['mean_wind'] = (np.nan, np.nan)

    if storm_motion.lower() in ['blm', 'left-mover']:
        params['storm_motion'] = params['bunkers_left']
    elif storm_motion.lower() in ['brm', 'right-mover']:
        params['storm_motion'] = params['bunkers_right']
    elif storm_motion.lower() in ['mnw', 'mean-wind']:
        params['storm_motion'] = params['mean_wind']
    else:
        params['storm_motion'] = tuple(int(v) for v in storm_motion.split('/'))

    try:
        params['critical'] = compute_crit_angl(data, params['storm_motion'])
    except (IndexError, ValueError):
        params['critical'] = np.nan

    for hght in [1, 3, 6]:
        try:
            params["shear_mag_%dm" % (hght * 1000)] = compute_shear_mag(data, hght)
        except (IndexError, ValueError):
            params["shear_mag_%dm" % (hght * 1000)] = np.nan

    for hght in [0.5, 1, 3]:
        params["srh_%dm" % (int(hght * 1000))] = compute_srh(data, params['storm_motion'], hght)

    return params


