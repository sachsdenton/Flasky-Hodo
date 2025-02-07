"""
Handles fetching NEXRAD Level-II data from NWS servers.
"""
import requests
from datetime import datetime, timedelta
from typing import Optional, List
import os
import gzip
import shutil

class NEXRADFetcher:
    def __init__(self):
        self.base_url = "https://nomads.ncep.noaa.gov/pub/data/nccf/radar/nexrad_level2"
        self.temp_dir = "temp_data"
        
    def _ensure_temp_dir(self):
        """Ensure temporary directory exists."""
        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir)

    def _build_url(self, site_id: str, timestamp: datetime) -> str:
        """Build URL for NEXRAD data."""
        year = timestamp.strftime("%Y")
        month = timestamp.strftime("%m")
        day = timestamp.strftime("%d")
        return f"{self.base_url}/{year}/{month}/{day}/{site_id}"

    def fetch_latest(self, site_id: str) -> Optional[str]:
        """
        Fetch the latest NEXRAD Level-II file for a given radar site.
        
        Args:
            site_id: Radar site identifier (e.g., 'KTLX')
            
        Returns:
            Path to downloaded file or None if failed
        """
        self._ensure_temp_dir()
        
        # Try current time first, then go back in 5-minute intervals
        current_time = datetime.utcnow()
        
        for minutes_ago in range(0, 60, 5):
            timestamp = current_time - timedelta(minutes=minutes_ago)
            url = self._build_url(site_id, timestamp)
            
            try:
                response = requests.get(f"{url}/index.html")
                if response.status_code == 200:
                    # Find the latest file
                    files = [line for line in response.text.split('\n') 
                            if line.endswith('.gz') and site_id in line]
                    
                    if files:
                        latest_file = sorted(files)[-1]
                        file_url = f"{url}/{latest_file}"
                        
                        # Download the file
                        output_path = os.path.join(self.temp_dir, latest_file)
                        response = requests.get(file_url, stream=True)
                        
                        if response.status_code == 200:
                            with open(output_path, 'wb') as f:
                                for chunk in response.iter_content(chunk_size=8192):
                                    if chunk:
                                        f.write(chunk)
                            return output_path
                        
            except Exception as e:
                print(f"Error fetching data: {e}")
                continue
                
        return None

    def cleanup(self):
        """Clean up temporary files."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
