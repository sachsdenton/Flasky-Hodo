"""
Handles fetching VAD data from NEXRAD sites.
"""
import os
import shutil
import time
from datetime import datetime
from typing import Optional
from vad_reader import download_vad

# Simple caching for Flask
_fetch_cache = {}
_fetch_cache_ttl = {}

class NEXRADFetcher:
    def __init__(self):
        self.temp_dir = "temp_data"

    def _ensure_temp_dir(self):
        """Ensure temporary directory exists."""
        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir)

    def fetch_latest(self, site_id: str) -> Optional[str]:
        """
        Fetch the latest VAD file for a given radar site.
        Results are cached for 5 minutes to reduce API calls.

        Args:
            site_id: Radar site identifier (e.g., 'KTLX')

        Returns:
            Path to downloaded file or None if failed
        """
        # Check cache first
        cache_key = f"fetch_{site_id.upper()}"
        current_time = time.time()
        
        if (cache_key in _fetch_cache and 
            current_time - _fetch_cache_ttl.get(cache_key, 0) < 300):
            return _fetch_cache[cache_key]
        
        self._ensure_temp_dir()

        try:
            # Use the original VAD plotter's download function with caching
            vad = download_vad(site_id, cache_path=self.temp_dir)
            
            if vad:
                # The download_vad function already saves the file with the proper name
                # We need to find the actual file that was created
                for filename in os.listdir(self.temp_dir):
                    if filename.startswith(site_id.upper()) and filename.endswith('.vad'):
                        file_path = os.path.join(self.temp_dir, filename)
                        _fetch_cache[cache_key] = file_path
                        _fetch_cache_ttl[cache_key] = current_time
                        return file_path
                
                # If no file found with expected pattern, look for any .vad file
                for filename in os.listdir(self.temp_dir):
                    if filename.endswith('.vad'):
                        file_path = os.path.join(self.temp_dir, filename)
                        _fetch_cache[cache_key] = file_path
                        _fetch_cache_ttl[cache_key] = current_time
                        return file_path
            
            _fetch_cache[cache_key] = None
            _fetch_cache_ttl[cache_key] = current_time
            return None

        except Exception as e:
            print(f"Error fetching VAD data for {site_id}: {e}")
            _fetch_cache[cache_key] = None
            _fetch_cache_ttl[cache_key] = current_time
            return None

    def cleanup(self):
        """Clean up temporary files."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)