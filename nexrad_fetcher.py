"""
Handles fetching NEXRAD Level-II data from NWS servers.
"""
import os
import shutil
from datetime import datetime, timedelta
from typing import Optional, List
from urllib.request import urlopen, URLError

class NEXRADFetcher:
    def __init__(self):
        self.base_url = "ftp://tgftp.nws.noaa.gov/SL.us008001/DF.of/DC.radar/DS.48vwp/SI."
        self.temp_dir = "temp_data"

    def _ensure_temp_dir(self):
        """Ensure temporary directory exists."""
        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir)

    def _find_file_times(self, site_id: str) -> List[tuple]:
        """Find available file times for a radar site."""
        import re
        url = f"{self.base_url}{site_id.lower()}/"

        try:
            file_text = urlopen(url).read().decode('utf-8')
            file_list = re.findall(r"([\w]{3} [\d]{1,2} [\d]{2}:[\d]{2}) (sn.[\d]{4})", file_text)

            if not file_list:
                return []

            file_times, file_names = zip(*file_list)
            file_names = list(file_names)

            # Convert times to datetime objects
            year = datetime.utcnow().year
            file_dts = []
            for ft in file_times:
                ft_dt = datetime.strptime(f"{year} {ft}", "%Y %b %d %H:%M")
                if ft_dt > datetime.utcnow():
                    ft_dt = datetime.strptime(f"{year - 1} {ft}", "%Y %b %d %H:%M")
                file_dts.append(ft_dt)

            # Sort files by time
            file_list = list(zip(file_names, file_dts))
            file_list.sort(key=lambda fl: fl[1])

            return file_list

        except URLError:
            print(f"Could not access radar site '{site_id.upper()}'")
            return []

    def fetch_latest(self, site_id: str) -> Optional[str]:
        """
        Fetch the latest VAD file for a given radar site.

        Args:
            site_id: Radar site identifier (e.g., 'KTLX')

        Returns:
            Path to downloaded file or None if failed
        """
        self._ensure_temp_dir()

        try:
            # Get list of available files
            file_list = self._find_file_times(site_id)
            if not file_list:
                return None

            # Get latest file
            latest_file, latest_time = file_list[-1]
            url = f"{self.base_url}{site_id.lower()}/{latest_file}"

            # Download file
            output_path = os.path.join(self.temp_dir, f"{site_id.lower()}_{latest_file}")
            with urlopen(url) as response, open(output_path, 'wb') as out_file:
                shutil.copyfileobj(response, out_file)

            return output_path

        except Exception as e:
            print(f"Error fetching data: {e}")
            return None

    def cleanup(self):
        """Clean up temporary files."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)