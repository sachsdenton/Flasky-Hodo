"""
Contains NEXRAD radar site information and utilities for site selection.
"""
from dataclasses import dataclass
from typing import Dict, List

@dataclass
class RadarSite:
    id: str
    name: str
    state: str
    latitude: float
    longitude: float
    region: int

# NEXRAD site information mapping
_SITE_LOCATIONS = {
    # WSR-88Ds
    'KABR': {'name': 'Aberdeen', 'state': 'SD', 'lat': 45.456, 'lon': -98.413, 'region': 3},
    'KBIS': {'name': 'Bismarck', 'state': 'ND', 'lat': 46.771, 'lon': -100.760, 'region': 3},
    'KFTG': {'name': 'Denver/Boulder', 'state': 'CO', 'lat': 39.786, 'lon': -104.546, 'region': 5},
    'KDMX': {'name': 'Des Moines', 'state': 'IA', 'lat': 41.731, 'lon': -93.723, 'region': 3},
    'KDTX': {'name': 'Detroit', 'state': 'MI', 'lat': 42.700, 'lon': -83.472, 'region': 3},
    'KDDC': {'name': 'Dodge City', 'state': 'KS', 'lat': 37.761, 'lon': -99.969, 'region': 3},
    'KDLH': {'name': 'Duluth', 'state': 'MN', 'lat': 46.837, 'lon': -92.210, 'region': 3},
    'KCYS': {'name': 'Cheyenne', 'state': 'WY', 'lat': 41.152, 'lon': -104.806, 'region': 5},
    'KLOT': {'name': 'Chicago', 'state': 'IL', 'lat': 41.604, 'lon': -88.085, 'region': 3},
    'KICT': {'name': 'Wichita', 'state': 'KS', 'lat': 37.654, 'lon': -97.443, 'region': 3},
    'KTLX': {'name': 'Oklahoma City', 'state': 'OK', 'lat': 35.333, 'lon': -97.278, 'region': 4},
    'KINX': {'name': 'Tulsa', 'state': 'OK', 'lat': 36.175, 'lon': -95.564, 'region': 4},
    'KVNX': {'name': 'Vance AFB', 'state': 'OK', 'lat': 36.741, 'lon': -98.128, 'region': 4},
    'KFDR': {'name': 'Frederick', 'state': 'OK', 'lat': 34.362, 'lon': -98.977, 'region': 4},
    'KAMA': {'name': 'Amarillo', 'state': 'TX', 'lat': 35.233, 'lon': -101.709, 'region': 4},
    'KLBB': {'name': 'Lubbock', 'state': 'TX', 'lat': 33.654, 'lon': -101.814, 'region': 4},
    # Add more sites as needed based on wsr88d.py
}

# Create radar sites mapping
RADAR_SITES: Dict[str, RadarSite] = {
    site_id: RadarSite(
        id=site_id,
        name=info['name'],
        state=info['state'],
        latitude=info['lat'],
        longitude=info['lon'],
        region=info['region']
    )
    for site_id, info in _SITE_LOCATIONS.items()
}

def get_sorted_sites() -> List[RadarSite]:
    """Returns a sorted list of radar sites by ID."""
    return sorted(RADAR_SITES.values(), key=lambda x: x.id)

def get_site_by_id(site_id: str) -> RadarSite:
    """Get radar site information by ID."""
    if site_id not in RADAR_SITES:
        raise ValueError(f"Invalid radar site ID: {site_id}")
    return RADAR_SITES[site_id]