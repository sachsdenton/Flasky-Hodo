"""
Contains NEXRAD radar site information and utilities for site selection.
"""
from dataclasses import dataclass
from typing import Dict, List
from wsr88d import _radar_info
import csv
import os

@dataclass
class RadarSite:
    id: str
    name: str
    region: int
    lat: float = 0.0
    lon: float = 0.0
    elevation: float = 0.0  # Added elevation in feet

def _load_site_data() -> Dict[str, Dict]:
    """Load site data from CSV file."""
    site_data = {}
    csv_path = "attached_assets/Weather_Radar_Stations_lat_lon_locations.csv"

    if os.path.exists(csv_path):
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['siteID']:  # Valid site row
                    site_data[row['siteID']] = {
                        'name': row['siteName'].strip() + ', ' + row['State'].strip(),
                        'lat': float(row['Latitude']),
                        'lon': float(row['Longitude']),
                        'elevation': float(row['antennaElevation'].replace(',', '')) if row['antennaElevation'] else 0.0
                    }
    return site_data

# Load site data from CSV files
_SITE_DATA = _load_site_data()

# Create radar sites mapping from wsr88d._radar_info and include coordinates from CSV
RADAR_SITES: Dict[str, RadarSite] = {
    site_id: RadarSite(
        id=site_id,
        name=_SITE_DATA.get(site_id, {}).get('name', site_id),
        region=info['region'],
        lat=_SITE_DATA.get(site_id, {}).get('lat', 0.0),
        lon=_SITE_DATA.get(site_id, {}).get('lon', 0.0),
        elevation=_SITE_DATA.get(site_id, {}).get('elevation', 0.0)
    )
    for site_id, info in _radar_info.items()
    if site_id in _SITE_DATA  # Only include sites we have coordinates for
}

def get_sorted_sites() -> List[RadarSite]:
    """Returns a sorted list of radar sites by ID."""
    return sorted(RADAR_SITES.values(), key=lambda x: (not x.id.startswith('K'), x.name))  # WSR-88D sites first, then sort by name

def get_site_by_id(site_id: str) -> RadarSite:
    """Get radar site information by ID."""
    if site_id not in RADAR_SITES:
        raise ValueError(f"Invalid radar site ID: {site_id}")
    return RADAR_SITES[site_id]