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

# Standard list of NEXRAD sites
RADAR_SITES: Dict[str, RadarSite] = {
    "KTLX": RadarSite("KTLX", "Oklahoma City", "OK", 35.333, -97.278),
    "KINX": RadarSite("KINX", "Tulsa", "OK", 36.175, -95.564),
    "KVNX": RadarSite("KVNX", "Vance AFB", "OK", 36.741, -98.128),
    "KFDR": RadarSite("KFDR", "Frederick", "OK", 34.362, -98.977),
    "KDDC": RadarSite("KDDC", "Dodge City", "KS", 37.761, -99.969),
    "KICT": RadarSite("KICT", "Wichita", "KS", 37.654, -97.443),
    "KAMA": RadarSite("KAMA", "Amarillo", "TX", 35.233, -101.709),
    "KLBB": RadarSite("KLBB", "Lubbock", "TX", 33.654, -101.814),
    # Add more radar sites as needed
}

def get_sorted_sites() -> List[RadarSite]:
    """Returns a sorted list of radar sites by ID."""
    return sorted(RADAR_SITES.values(), key=lambda x: x.id)

def get_site_by_id(site_id: str) -> RadarSite:
    """Get radar site information by ID."""
    return RADAR_SITES.get(site_id)
