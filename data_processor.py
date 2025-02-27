import numpy as np
from typing import List, Dict, Optional
from datetime import datetime
from vad_reader import VADFile, download_vad

class WindProfile:
    def __init__(self):
        self.heights = np.array([], dtype=float)
        self.speeds = np.array([], dtype=float)
        self.directions = np.array([], dtype=float)
        self.times: List[datetime] = []
        self.vad_file: Optional[VADFile] = None
        # Add these attributes for use elsewhere in the codebase
        self.site_id = None
        self.site_name = None

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

            # Store data as numpy arrays directly
            self.heights = np.array([float(h) for h in heights], dtype=float)
            self.speeds = np.array([float(s) for s in speeds], dtype=float)
            self.directions = np.array([float(d) for d in directions], dtype=float)
            self.times = [time] * len(heights)

            return True

        except Exception as e:
            print(f"Error reading NEXRAD file: {e}")
            return False

    def clear_data(self) -> None:
        """Clear all stored wind data."""
        self.heights = np.array([], dtype=float)
        self.speeds = np.array([], dtype=float)
        self.directions = np.array([], dtype=float)
        self.times = []
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
        if len(self.heights) == 0:
            return {"speed": 0.0, "direction": 0.0}

        # Find data points within the layer (already numpy arrays)
        mask = np.logical_and(self.heights >= bottom, self.heights <= top)

        if not np.any(mask):
            return {"speed": 0.0, "direction": 0.0}

        # Calculate mean wind components directly from arrays
        mean_speed = np.mean(self.speeds[mask])
        mean_dir = np.mean(self.directions[mask])

        return {"speed": mean_speed, "direction": mean_dir}

    def validate(self) -> bool:
        """Validate the stored wind profile data."""
        if len(self.heights) == 0:
            return False

        # Basic validation checks
        if not (len(self.heights) == len(self.speeds) == len(self.directions)):
            return False

        # Check value ranges (directly using numpy arrays)
        if not np.all((self.speeds >= 0) & (self.speeds <= 200)):  # Max reasonable wind speed
            return False
        if not np.all((self.directions >= 0) & (self.directions <= 360)):
            return False
        if not np.all(self.heights >= 0):
            return False

        return True