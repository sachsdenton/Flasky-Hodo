from __future__ import print_function
import numpy as np
import struct
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

try:
    from urllib.request import urlopen, URLError
except ImportError:
    from urllib2 import urlopen, URLError

try:
    from io import BytesIO
except ImportError:
    from BytesIO import BytesIO

@dataclass
class VADPoint:
    """
    Represents a single VAD observation point.
    """
    height: float  # meters
    speed: float   # knots
    direction: float  # degrees
    time: datetime
    rms_error: float

class VADReader:
    """
    Handles reading and processing of VAD (Velocity Azimuth Display) data.
    """
    fields = ['wind_dir', 'wind_spd', 'rms_error', 'divergence', 'slant_range', 'elev_angle']
    base_url = "ftp://tgftp.nws.noaa.gov/SL.us008001/DF.of/DC.radar/DS.48vwp/"

    def __init__(self):
        self._data = None
        self._time = None
        self.vad_data: List[VADPoint] = []

    def read_nexrad_file(self, file_path: str) -> bool:
        """
        Read a NEXRAD Level-II file and extract VAD data.

        Args:
            file_path: Path to the NEXRAD Level-II file
        """
        try:
            with open(file_path, 'rb') as f:
                self._rpg = BytesIO(f.read())

            self._read_headers()
            has_symbology_block, has_graphic_block, has_tabular_block = self._read_product_description_block()

            if has_tabular_block:
                self._read_tabular_block()
                self._data = self._get_data()
                return True
            return False
        except Exception as e:
            print(f"Error reading NEXRAD file: {e}")
            return False

    def _read_headers(self):
        """Read the WMO and message headers."""
        self._read('s30')  # WMO header

        # Message header
        self._read('h')    # Message code
        self._read('h')    # Date
        self._read('i')    # Time
        self._read('i')    # Length
        self._read('h')    # Source ID
        self._read('h')    # Destination ID
        self._read('h')    # Number of blocks

    def _read_product_description_block(self):
        """Read the product description block."""
        self._read('h')  # Block separator
        self._radar_latitude = self._read('i') / 1000.
        self._radar_longitude = self._read('i') / 1000.
        self._radar_elevation = self._read('h')

        product_code = self._read('h')
        if product_code != 48:
            raise IOError("Not a VWP file")

        # Skip operational mode and other metadata
        self._read('h')  # Operational mode
        self._vcp = self._read('h')
        self._read('h')  # Request sequence number
        self._read('h')  # Volume scan number

        scan_date = self._read('h')
        scan_time = self._read('i')
        self._read('h')  # Product date
        self._read('i')  # Product time

        # Skip product dependent variables
        self._read('h')
        self._read('h')
        self._read('h')
        self._read('h')
        self._read('16h')
        self._read('7h')

        self._read('b')  # Version
        self._read('b')  # Spot blank

        offset_symbology = self._read('i')
        offset_graphic = self._read('i')
        offset_tabular = self._read('i')

        self._time = datetime(1969, 12, 31) + timedelta(days=scan_date, seconds=scan_time)

        return offset_symbology > 0, offset_graphic > 0, offset_tabular > 0

    def _read_tabular_block(self):
        """Read the tabular block containing VAD data."""
        self._read('h')  # Block separator
        block_id = self._read('h')
        if block_id != 3:
            raise IOError("Not a tabular block")

        self._read('i')  # Block size
        self._text_message = []

        # Skip header
        for _ in range(15):
            self._read('h')

        num_pages = self._read('h')

        for _ in range(num_pages):
            num_chars = self._read('h')
            self._text_message.append([])
            while num_chars != -1:
                self._text_message[-1].append(self._read(f"s{num_chars}"))
                num_chars = self._read('h')

    def _read(self, type_string: str):
        """Read binary data according to format string."""
        if type_string[0] != 's':
            size = struct.calcsize(type_string)
            data = struct.unpack(f">{type_string}", self._rpg.read(size))
        else:
            size = int(type_string[1:])
            data = tuple([self._rpg.read(size).strip(b"\0").decode('utf-8')])

        if len(data) == 1:
            return data[0]
        return list(data)

    def _get_data(self) -> Dict[str, np.ndarray]:
        """Process VAD data from text message."""
        vad_list = []
        for page in self._text_message:
            if page[0].strip()[:20] == "VAD Algorithm Output":
                vad_list.extend(page[3:])

        data = {field: [] for field in self.fields}

        for line in vad_list:
            values = line.strip().split()
            data['wind_dir'].append(float(values[4]))
            data['wind_spd'].append(float(values[5]))
            data['rms_error'].append(float(values[6]))
            data['divergence'].append(float(values[7]) if values[7] != 'NA' else np.nan)
            data['slant_range'].append(float(values[8]))
            data['elev_angle'].append(float(values[9]))

        # Convert to numpy arrays
        for key in data:
            data[key] = np.array(data[key])

        # Convert slant range to height
        data['slant_range'] *= 6067.1 / 3281.

        r_e = 4. / 3. * 6371  # Earth radius
        data['altitude'] = np.sqrt(r_e ** 2 + data['slant_range'] ** 2 + 
                                 2 * r_e * data['slant_range'] * 
                                 np.sin(np.radians(data['elev_angle']))) - r_e

        # Sort by altitude
        order = np.argsort(data['altitude'])
        for key in data:
            data[key] = data[key][order]

        return data

    def get_profile(self, time: Optional[datetime] = None) -> List[VADPoint]:
        """Get wind profile data."""
        if self._data is None:
            return []

        points = []
        for i in range(len(self._data['altitude'])):
            point = VADPoint(
                height=float(self._data['altitude'][i]),
                speed=float(self._data['wind_spd'][i]),
                direction=float(self._data['wind_dir'][i]),
                time=self._time,
                rms_error=float(self._data['rms_error'][i])
            )
            points.append(point)

        return points

    def get_height_range(self) -> Tuple[float, float]:
        """Get the height range of available data."""
        if self._data is None:
            return (0.0, 0.0)
        return (min(self._data['altitude']), max(self._data['altitude']))