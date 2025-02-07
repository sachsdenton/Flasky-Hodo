import numpy as np
from typing import List, Dict, Optional
from datetime import datetime
from vad_reader import VADFile, download_vad

class WindProfile:
    def __init__(self):
        self.heights: List[float] = []
        self.speeds: List[float] = []
        self.directions: List[float] = []
        self.times: List[datetime] = []
        self.vad_file: Optional[VADFile] = None

    def load_from_nexrad(self, file_path: str) -> bool:
        """
        Load wind profile data from a NEXRAD file.

        Args:
            file_path: Path to the NEXRAD file

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            with open(file_path, 'rb') as f:
                self.vad_file = VADFile(f)

            # Clear existing data
            self.clear_data()

            # Extract data from VAD file
            heights = self.vad_file['altitude']
            speeds = self.vad_file['wind_spd']
            directions = self.vad_file['wind_dir']
            time = self.vad_file['time']

            # Store data
            for h, s, d in zip(heights, speeds, directions):
                self.heights.append(float(h))
                self.speeds.append(float(s))
                self.directions.append(float(d))
                self.times.append(time)

            return True

        except Exception as e:
            print(f"Error reading NEXRAD file: {e}")
            return False

    def clear_data(self) -> None:
        """Clear all stored wind data."""
        self.heights.clear()
        self.speeds.clear()
        self.directions.clear()
        self.times.clear()
        self.vad_file = None

    def get_layer_mean(self, bottom: float, top: float) -> Dict[str, float]:
        """
        Calculate mean wind in a layer.

        Args:
            bottom: Bottom of layer (meters)
            top: Top of layer (meters)

        Returns:
            Dictionary containing mean speed and direction
        """
        if not self.heights:
            return {"speed": 0.0, "direction": 0.0}

        # Find data points within the layer
        mask = np.logical_and(np.array(self.heights) >= bottom, 
                            np.array(self.heights) <= top)

        if not any(mask):
            return {"speed": 0.0, "direction": 0.0}

        # Calculate mean wind components
        mean_speed = np.mean(np.array(self.speeds)[mask])
        mean_dir = np.mean(np.array(self.directions)[mask])

        return {"speed": mean_speed, "direction": mean_dir}

    def validate(self) -> bool:
        """Validate the stored wind profile data."""
        if not self.heights:
            return False

        # Basic validation checks
        if not (len(self.heights) == len(self.speeds) == len(self.directions)):
            return False

        # Check value ranges
        if not all(0 <= s <= 200 for s in self.speeds):  # Max reasonable wind speed
            return False
        if not all(0 <= d <= 360 for d in self.directions):
            return False
        if not all(h >= 0 for h in self.heights):
            return False

        return True