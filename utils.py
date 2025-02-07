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
