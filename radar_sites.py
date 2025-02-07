"""
Contains NEXRAD radar site information and utilities for site selection.
"""
from dataclasses import dataclass
from typing import Dict, List
from wsr88d import _radar_info

@dataclass
class RadarSite:
    id: str
    name: str
    region: int

# Standard names for radar sites
_SITE_NAMES = {
    # WSR-88Ds
    'KABR': 'Aberdeen',
    'KBIS': 'Bismarck',
    'KFTG': 'Denver/Boulder',
    'KDMX': 'Des Moines',
    'KDTX': 'Detroit',
    'KDDC': 'Dodge City',
    'KDLH': 'Duluth',
    'KCYS': 'Cheyenne',
    'KLOT': 'Chicago',
    'KICT': 'Wichita',
    'KTLX': 'Oklahoma City',
    'KINX': 'Tulsa',
    'KVNX': 'Vance AFB',
    'KFDR': 'Frederick',
    'KAMA': 'Amarillo',
    'KLBB': 'Lubbock',
    'KFFC': 'Atlanta',
    'KBMX': 'Birmingham',
    'KBOX': 'Boston',
    'KBUF': 'Buffalo',
    'KCAE': 'Columbia',
    'KDFW': 'Dallas/Fort Worth',
    'KDTW': 'Detroit',
    'KEPZ': 'El Paso',
    'KGRR': 'Grand Rapids',
    'KGSP': 'Greenville/Spartanburg',
    'KHGX': 'Houston/Galveston',
    'KIND': 'Indianapolis',
    'KJAX': 'Jacksonville',
    'KMCI': 'Kansas City',
    'KMFL': 'Miami',
    'KMKX': 'Milwaukee',
    'KMPX': 'Minneapolis',
    'KOKX': 'New York City',
    'KPAH': 'Paducah',
    'KPBZ': 'Pittsburgh',
    'KPOE': 'Fort Polk',
    'KRAX': 'Raleigh/Durham',
    'KRLX': 'Charleston',
    'KSHV': 'Shreveport',
    'KSJT': 'San Angelo',
    'KTBW': 'Tampa Bay'
}

# Create radar sites mapping from wsr88d._radar_info
RADAR_SITES: Dict[str, RadarSite] = {
    site_id: RadarSite(
        id=site_id,
        name=_SITE_NAMES.get(site_id, site_id),  # Use name from mapping or ID if not found
        region=info['region']
    )
    for site_id, info in _radar_info.items()
    if not site_id.startswith('T')  # Exclude TDWR sites for now
}

def get_sorted_sites() -> List[RadarSite]:
    """Returns a sorted list of radar sites by ID."""
    return sorted(RADAR_SITES.values(), key=lambda x: x.id)

def get_site_by_id(site_id: str) -> RadarSite:
    """Get radar site information by ID."""
    if site_id not in RADAR_SITES:
        raise ValueError(f"Invalid radar site ID: {site_id}")
    return RADAR_SITES[site_id]