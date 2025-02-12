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
    elevation: float = 0.0  # Added elevation in feet

# Process the CSV files to get location names
def _load_site_names() -> Dict[str, str]:
    site_names = {}

    # Read WSR-88D sites
    wsr88d_csv = "attached_assets/wsr88d-radar-list_alphabetically by site ID.csv"
    if os.path.exists(wsr88d_csv):
        with open(wsr88d_csv, 'r') as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) >= 3 and row[2].strip().startswith('K'):  # Valid WSR-88D row
                    site_id = row[2].strip()
                    location = row[0].strip().strip('"')
                    site_names[site_id] = location

    # Read TDWR sites
    tdwr_csv = "attached_assets/Copy of tdwr-radar-list_alphabetical by site ID.csv"
    if os.path.exists(tdwr_csv):
        with open(tdwr_csv, 'r') as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) >= 3 and row[2].strip().startswith('T'):  # Valid TDWR row
                    site_id = row[2].strip()
                    location = row[0].strip().strip('"')
                    site_names[site_id] = location

    return site_names

# Load site names from CSV files
_SITE_NAMES = _load_site_names()

# Create radar sites mapping from wsr88d._radar_info and include TDWR sites
RADAR_SITES: Dict[str, RadarSite] = {
    site_id: RadarSite(
        id=site_id,
        name=_SITE_NAMES.get(site_id, site_id),  # Use name from CSV mapping or ID if not found
        region=info['region']
    )
    for site_id, info in _radar_info.items()
}

def get_sorted_sites() -> List[RadarSite]:
    """Returns a sorted list of radar sites by ID."""
    return sorted(RADAR_SITES.values(), key=lambda x: (not x.id.startswith('K'), x.name))  # WSR-88D sites first, then sort by name

def get_site_by_id(site_id: str) -> RadarSite:
    """Get radar site information by ID."""
    if site_id not in RADAR_SITES:
        raise ValueError(f"Invalid radar site ID: {site_id}")
    return RADAR_SITES[site_id]