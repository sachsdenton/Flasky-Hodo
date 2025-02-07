import numpy as np
from typing import List, Tuple, Dict
from utils import calculate_wind_components, validate_wind_data

class WindProfile:
    def __init__(self):
        self.heights: List[float] = []
        self.speeds: List[float] = []
        self.directions: List[float] = []
        self.u_components: List[float] = []
        self.v_components: List[float] = []

    def add_observation(self, height: float, speed: float, direction: float) -> None:
        """
        Add a wind observation to the profile.
        
        Args:
            height: Height of observation (meters)
            speed: Wind speed (knots)
            direction: Wind direction (degrees)
        """
        self.heights.append(height)
        self.speeds.append(speed)
        self.directions.append(direction)
        u, v = calculate_wind_components(speed, direction)
        self.u_components.append(u)
        self.v_components.append(v)

    def clear_data(self) -> None:
        """Clear all stored wind data."""
        self.heights.clear()
        self.speeds.clear()
        self.directions.clear()
        self.u_components.clear()
        self.v_components.clear()

    def get_layer_mean(self, bottom: float, top: float) -> Dict[str, float]:
        """
        Calculate mean wind in a layer.
        
        Args:
            bottom: Bottom of layer (meters)
            top: Top of layer (meters)
        
        Returns:
            Dictionary containing mean speed and direction
        """
        mask = np.logical_and(np.array(self.heights) >= bottom, 
                            np.array(self.heights) <= top)
        
        if not any(mask):
            return {"speed": 0.0, "direction": 0.0}
        
        mean_u = np.mean(np.array(self.u_components)[mask])
        mean_v = np.mean(np.array(self.v_components)[mask])
        
        speed = np.sqrt(mean_u**2 + mean_v**2)
        direction = 270 - np.rad2deg(np.arctan2(mean_v, mean_u))
        if direction < 0:
            direction += 360
        
        return {"speed": speed, "direction": direction}

    def validate(self) -> bool:
        """Validate the stored wind profile data."""
        return validate_wind_data(self.speeds, self.directions, self.heights)
