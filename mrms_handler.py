"""
Handles fetching and processing of MRMS (Multi-Radar/Multi-Sensor) data.
"""
import requests
from typing import Optional, Dict, Tuple
from datetime import datetime
import numpy as np

class MRMSHandler:
    """Handles MRMS data operations."""
    
    def __init__(self):
        self.mrms_base_url = "https://mrms.ncep.noaa.gov/data"
        self.tile_base_url = "https://mesonet.agron.iastate.edu/cache/tile.py/1.0.0"
        
    def get_tile_url(self, product: str = "nexrad-n0q-900913") -> str:
        """
        Get the tile URL for MRMS data visualization.
        
        Args:
            product: MRMS product identifier
            
        Returns:
            URL template for tile service
        """
        return f"{self.tile_base_url}/{product}/{{z}}/{{x}}/{{y}}.png"
    
    def get_reflectivity_metadata(self) -> Dict:
        """
        Get metadata for latest reflectivity mosaic.
        
        Returns:
            Dictionary containing metadata
        """
        metadata = {
            "attribution": '&copy; <a href="https://mrms.ncep.noaa.gov/">NOAA MRMS</a>',
            "min_zoom": 0,
            "max_zoom": 16,
            "opacity": 0.7,
            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        }
        return metadata
    
    def get_bounds(self) -> Tuple[Tuple[float, float], Tuple[float, float]]:
        """
        Get CONUS bounds for MRMS data.
        
        Returns:
            Tuple of ((min_lat, min_lon), (max_lat, max_lon))
        """
        return ((20.0, -130.0), (55.0, -60.0))  # CONUS coverage
