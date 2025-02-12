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

def calculate_skoff_angle(surface_speed: float, surface_dir: float, 
                            radar_speed: float, radar_dir: float) -> float:
    """
    Calculate the angle between surface winds and radar winds (Esterheld Critical Angle).

    Args:
        surface_speed: Surface wind speed in knots
        surface_dir: Surface wind direction in degrees
        radar_speed: Radar wind speed in knots
        radar_dir: Radar wind direction in degrees

    Returns:
        float: Angle in degrees between the two wind vectors
    """
    # Convert both vectors to u,v components
    u1, v1 = calculate_wind_components(surface_speed, surface_dir)
    u2, v2 = calculate_wind_components(radar_speed, radar_dir)

    # Calculate the angle between vectors using dot product
    dot_product = u1*u2 + v1*v2
    magnitudes = np.sqrt((u1**2 + v1**2) * (u2**2 + v2**2))

    if magnitudes == 0:
        return 0.0

    cos_angle = np.clip(dot_product / magnitudes, -1.0, 1.0)
    angle_rad = np.arccos(cos_angle)
    return np.rad2deg(angle_rad)

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