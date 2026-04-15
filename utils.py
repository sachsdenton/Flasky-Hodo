import numpy as np
from typing import Tuple, List, Optional

def calculate_wind_components(speed: float, direction: float) -> Tuple[float, float]:
    """
    Calculate u and v components from wind speed and direction.

    Args:
        speed: Wind speed in knots
        direction: Wind direction in degrees

    Returns:
        Tuple of (u, v) components
    """
    direction_rad = np.deg2rad(270 - direction)  # Convert to mathematical angle
    u = speed * np.cos(direction_rad)
    v = speed * np.sin(direction_rad)
    return u, v

def _angle_at_vertex(vertex_u, vertex_v, point_a_u, point_a_v, point_b_u, point_b_v):
    """
    Calculate the angle at vertex between rays to point_a and point_b.
    Returns angle in degrees, or None if degenerate.
    """
    v1_u, v1_v = point_a_u - vertex_u, point_a_v - vertex_v
    v2_u, v2_v = point_b_u - vertex_u, point_b_v - vertex_v
    mag1 = np.sqrt(v1_u**2 + v1_v**2)
    mag2 = np.sqrt(v2_u**2 + v2_v**2)
    if mag1 == 0 or mag2 == 0:
        return None
    dot = v1_u * v2_u + v1_v * v2_v
    cos_angle = np.clip(dot / (mag1 * mag2), -1.0, 1.0)
    return float(np.rad2deg(np.arccos(cos_angle)))


def calculate_esterheld_angle(surface_u, surface_v, storm_u, storm_v, vad_half_km_u, vad_half_km_v):
    """
    Esterheld Critical Angle: angle at the surface wind vertex between
    the storm motion point and the interpolated 0.5 km VAD wind point.
    """
    return _angle_at_vertex(surface_u, surface_v, storm_u, storm_v, vad_half_km_u, vad_half_km_v)


def find_kink_point(surface_u, surface_v, u_components, v_components, threshold_deg=5.0):
    """
    Find the first 'kink' in the hodograph — the first VAD point where the
    vector from the surface deviates more than threshold_deg from the
    reference line (surface → lowest VAD point).

    Returns (kink_u, kink_v) or None if no kink found.
    """
    if len(u_components) < 2:
        return None

    ref_u = u_components[0] - surface_u
    ref_v = v_components[0] - surface_v
    mag_ref = np.sqrt(ref_u**2 + ref_v**2)
    if mag_ref == 0:
        return None

    for i in range(1, len(u_components)):
        vec_u = u_components[i] - surface_u
        vec_v = v_components[i] - surface_v
        mag_vec = np.sqrt(vec_u**2 + vec_v**2)
        if mag_vec == 0:
            continue
        cos_a = np.clip((ref_u * vec_u + ref_v * vec_v) / (mag_ref * mag_vec), -1.0, 1.0)
        angle = np.rad2deg(np.arccos(cos_a))
        if angle > threshold_deg:
            return (float(u_components[i]), float(v_components[i]))

    return None


def calculate_skoff_angle(surface_u, surface_v, storm_u, storm_v, kink_u, kink_v):
    """
    Skoff Critical Angle: angle at the surface wind vertex between
    the storm motion point and the first kink point on the hodograph.
    """
    return _angle_at_vertex(surface_u, surface_v, storm_u, storm_v, kink_u, kink_v)


def interpolate_wind_at_height(heights, u_components, v_components, target_height):
    """
    Interpolate U/V wind components at a specific height.
    Heights and target must use the same unit (e.g. both km or both m).
    Returns (u, v) or None if target is outside the data range.
    """
    if len(heights) == 0 or target_height < min(heights) or target_height > max(heights):
        return None
    u_interp = float(np.interp(target_height, heights, u_components))
    v_interp = float(np.interp(target_height, heights, v_components))
    return (u_interp, v_interp)

def validate_wind_data(speeds: List[float], directions: List[float], heights: List[float]) -> bool:
    """
    Validate wind data inputs.

    Args:
        speeds: List of wind speeds
        directions: List of wind directions
        heights: List of heights

    Returns:
        bool: True if data is valid
    """
    if not (len(speeds) == len(directions) == len(heights)):
        return False

    # Check value ranges
    if not all(0 <= s <= 200 for s in speeds):  # Max reasonable wind speed
        return False
    if not all(0 <= d <= 360 for d in directions):
        return False
    if not all(h >= 0 for h in heights):
        return False

    return True

def interpolate_height(heights: List[float], values: List[float], target_height: float) -> Optional[float]:
    """
    Interpolate a value at a specific height.

    Args:
        heights: List of heights
        values: List of values corresponding to heights
        target_height: Height to interpolate at

    Returns:
        Interpolated value or None if outside range
    """
    if target_height < min(heights) or target_height > max(heights):
        return None

    return np.interp(target_height, heights, values)