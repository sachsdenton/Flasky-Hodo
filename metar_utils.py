import re
import requests
from typing import Tuple, Optional, Dict, Any
from datetime import datetime
import time

# Simple caching mechanism for Flask
_cache = {}
_cache_ttl = {}

def cache_data(ttl=300):
    def decorator(func):
        def wrapper(*args, **kwargs):
            cache_key = f"{func.__name__}_{str(args)}_{str(sorted(kwargs.items()))}"
            current_time = time.time()
            
            if cache_key in _cache and current_time - _cache_ttl.get(cache_key, 0) < ttl:
                return _cache[cache_key]
            
            result = func(*args, **kwargs)
            _cache[cache_key] = result
            _cache_ttl[cache_key] = current_time
            return result
        return wrapper
    return decorator

@cache_data(ttl=300)  # Cache for 5 minutes
def get_metar(station_id: str) -> Tuple[Optional[float], Optional[float], Optional[datetime], Optional[str]]:
    """
    Fetch METAR data for a given station and extract wind information.
    Results are cached for 5 minutes to reduce API calls.

    Args:
        station_id (str): 4-letter ICAO station identifier

    Returns:
        tuple: (wind_direction, wind_speed, observation_time, error_message)
            wind_direction (float): Wind direction in degrees
            wind_speed (float): Wind speed in knots
            observation_time (datetime): Timestamp of the METAR observation
            error_message (str): Error message if any; None if successful
    """
    try:
        # Validate station ID format
        if not re.match(r'^[A-Z0-9]{4}$', station_id):
            return None, None, None, "Invalid station ID format"

        # Aviation Weather Center API endpoint
        url = f"https://aviationweather.gov/cgi-bin/data/metar.php?ids={station_id}&format=json&hours=2"
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        data = response.json()

        if not data or len(data) == 0:
            return None, None, None, f"No METAR data available for {station_id}"

        # Get the most recent METAR
        metar = data[0]

        # Try different possible key names for wind direction and speed
        wind_dir = None
        wind_speed = None

        # Check for wind direction; handle the 'VRB' case (variable winds)
        for key in ['wdir', 'wind_dir', 'direction', 'drct']:
            if key in metar:
                if isinstance(metar[key], str) and metar[key].upper() == 'VRB':
                    wind_dir = 0  # Use 0 degrees for variable winds
                else:
                    try:
                        wind_dir = float(metar[key])
                    except (ValueError, TypeError):
                        continue

        # Check for wind speed
        for key in ['wspd', 'wind_speed', 'speed', 'sknt']:
            if key in metar:
                try:
                    wind_speed = float(metar[key])
                    break
                except (ValueError, TypeError):
                    continue

        # Extract observation time
        observation_time = None
        for key in ['obsTime', 'observation_time', 'time', 'date_time']:
            if key in metar:
                try:
                    # Try parsing as timestamp (integer)
                    if isinstance(metar[key], (int, float)):
                        observation_time = datetime.fromtimestamp(metar[key])
                        break
                    # Try parsing as ISO format string
                    elif isinstance(metar[key], str):
                        observation_time = datetime.fromisoformat(metar[key].replace('Z', '+00:00'))
                        break
                except (ValueError, TypeError):
                    continue
        
        # Default to current time if observation time is not found
        if observation_time is None:
            observation_time = datetime.utcnow()

        if wind_dir is not None and wind_speed is not None:
            # Validate wind values
            if 0 <= wind_dir <= 360 and wind_speed >= 0:
                return wind_dir, wind_speed, observation_time, None
            else:
                return None, None, None, "Invalid wind values in METAR"
        else:
            missing = []
            if wind_dir is None:
                missing.append("direction")
            if wind_speed is None:
                missing.append("speed")
            return None, None, None, f"Wind data incomplete in METAR (missing: {', '.join(missing)})"

    except requests.exceptions.RequestException as e:
        return None, None, None, f"Failed to fetch METAR data: {str(e)}"
    except (ValueError, KeyError, IndexError) as e:
        return None, None, None, f"Error parsing METAR data: {str(e)}"
    except Exception as e:
        return None, None, None, f"Unexpected error: {str(e)}"
