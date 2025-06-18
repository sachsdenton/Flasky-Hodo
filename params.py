
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
    Calculate Storm Relative Helicity (SRH) using the discrete layer approach.
    Following the exact meteorological algorithm provided.
    """
    try:
        # Extract wind data
        wind_dir = np.array(data['wind_dir'])
        wind_spd = np.array(data['wind_spd'])  # in knots
        altitudes = np.array(data['altitude'])  # Check if in km or m
        
        # Check minimum data requirements
        if len(wind_dir) < 2 or len(wind_spd) < 2:
            return np.nan
        
        # Convert altitudes to meters if they appear to be in kilometers
        # Based on debug output showing max altitude of 7.36, this is likely in km
        if np.max(altitudes) < 50:  # If max altitude is less than 50, assume it's in km
            altitudes = altitudes * 1000  # Convert km to meters
            
        # Convert wind to u,v components (meteorological convention)
        # Convert from knots to m/s: 1 knot = 0.514444 m/s
        u = -wind_spd * 0.514444 * np.sin(np.radians(wind_dir))  # u component (east-west) in m/s
        v = -wind_spd * 0.514444 * np.cos(np.radians(wind_dir))  # v component (north-south) in m/s
        
        # Get storm motion u,v components (convert from knots to m/s)
        storm_dir, storm_spd = storm_motion
        us = -storm_spd * 0.514444 * np.sin(np.radians(storm_dir))  # Storm u component
        vs = -storm_spd * 0.514444 * np.cos(np.radians(storm_dir))  # Storm v component
        
        # Sort data by altitude (ascending) - Step 1
        sort_indices = np.argsort(altitudes)
        altitudes_sorted = altitudes[sort_indices]
        u_sorted = u[sort_indices]
        v_sorted = v[sort_indices]
        
        # Select height range of interest - Step 2
        valid_mask = (altitudes_sorted >= 0) & (altitudes_sorted <= hght)
        if np.sum(valid_mask) < 2:
            return np.nan
            
        # Extract layer data
        z = altitudes_sorted[valid_mask]
        u_layer = u_sorted[valid_mask]
        v_layer = v_sorted[valid_mask]
        
        # Calculate SRH using discrete layer approach - Steps 3-8
        srh_total = 0.0
        
        # Add debug information
        print(f"Debug SRH: Processing {len(z)} altitude levels")
        print(f"Debug SRH: Height range: {z[0]:.0f}m to {z[-1]:.0f}m")
        print(f"Debug SRH: Storm motion: u={us:.2f}, v={vs:.2f} m/s")
        
        for i in range(len(z) - 1):
            # Step 4: Calculate layer shear vector
            delta_u = u_layer[i+1] - u_layer[i]
            delta_v = v_layer[i+1] - v_layer[i]
            
            # Step 5: Compute mean wind vector in layer
            u_mean = (u_layer[i] + u_layer[i+1]) / 2.0
            v_mean = (v_layer[i] + v_layer[i+1]) / 2.0
            
            # Step 6: Compute storm-relative wind vector
            ur = u_mean - us
            vr = v_mean - vs
            
            # Step 7: Compute SRH contribution from layer (vector cross product)
            srh_layer = ur * delta_v - vr * delta_u
            
            # Debug first few layers
            if i < 3:
                print(f"Layer {i}: z={z[i]:.0f}-{z[i+1]:.0f}m, "
                      f"wind=({u_mean:.2f},{v_mean:.2f}), "
                      f"storm_rel=({ur:.2f},{vr:.2f}), "
                      f"shear=({delta_u:.3f},{delta_v:.3f}), "
                      f"srh_layer={srh_layer:.2f}")
            
            # Step 8: Add to cumulative total
            srh_total += srh_layer
            
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


