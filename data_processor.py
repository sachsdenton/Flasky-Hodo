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
            # Clear existing data first
            self.clear_data()
            
            # Load VAD file and extract data immediately while file is open
            with open(file_path, 'rb') as f:
                vad_file = VADFile(f)
                
                # Extract data immediately (already numpy arrays)
                self.heights = vad_file['altitude'].astype(float)
                self.speeds = vad_file['wind_spd'].astype(float)
                self.directions = vad_file['wind_dir'].astype(float)
                
                # Get time from VAD file (single datetime object)
                time = vad_file['time']
                self.times = [time] * len(self.heights)
                
                # Store the VAD file object for later use
                self.vad_file = vad_file

            return True

        except Exception as e:
            print(f"Error reading NEXRAD file: {e}")
            import traceback
            traceback.print_exc()
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