"""
Handles fetching VAD data from NEXRAD sites.
"""
import os
import re
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from io import BytesIO
from typing import Optional, List, Dict, Any, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from vad_reader import download_vad, find_file_times, VADFile
from wsr88d import build_has_name

# NWS publishes the same VAD files over HTTPS as the legacy FTP path; HTTPS
# is ~6x faster per request and supports parallel connections cleanly.
_HTTPS_BASE = "https://tgftp.nws.noaa.gov/SL.us008001/DF.of/DC.radar/DS.48vwp"

# Apache mod_autoindex row: <a href="sn.0123">sn.0123</a> ... 30-Apr-2026 01:13
_LISTING_ROW = re.compile(
    r'href="(sn\.\d{4})"[^>]*>[^<]*</a>[^<]*</td>'
    r'\s*<td[^>]*>\s*(\d{1,2}-[A-Za-z]{3}-\d{4}\s+\d{2}:\d{2})'
)

_session: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    """Module-wide pooled session with retries and Keep-Alive."""
    global _session
    if _session is None:
        s = requests.Session()
        retry = Retry(total=2, backoff_factor=0.3,
                      status_forcelist=(500, 502, 503, 504),
                      allowed_methods=frozenset(['GET']))
        adapter = HTTPAdapter(pool_connections=16, pool_maxsize=16,
                              max_retries=retry)
        s.mount('https://', adapter)
        s.mount('http://', adapter)
        _session = s
    return _session


def _list_site_https(site_id: str) -> List[Tuple[str, datetime]]:
    """List a site's available VAD files via HTTPS.

    Returns ``[(filename, valid_time)]`` ordered newest-first, with the same
    off-by-one shift that ``vad_reader.find_file_times`` applies (the newest
    entry is exposed as ``sn.last`` because files are only renamed when the
    next one lands).
    """
    url = f"{_HTTPS_BASE}/SI.{site_id.lower()}/"
    resp = _get_session().get(url, timeout=10)
    resp.raise_for_status()

    rows: List[Tuple[str, datetime]] = []
    for fn, ts in _LISTING_ROW.findall(resp.text):
        try:
            dt = datetime.strptime(ts, "%d-%b-%Y %H:%M")
        except ValueError:
            continue
        rows.append((fn, dt))

    if not rows:
        return []

    rows.sort(key=lambda r: r[1])
    names = [r[0] for r in rows]
    times = [r[1] for r in rows]
    # Shift filenames by one — newest scan is published under sn.last until
    # the next volume is generated.
    names[:-1] = names[1:]
    names[-1] = 'sn.last'
    return list(zip(names, times))[::-1]

# Simple caching for Flask
_fetch_cache = {}
_fetch_cache_ttl = {}
_history_cache: Dict[str, List[Dict[str, Any]]] = {}
_history_cache_ttl: Dict[str, float] = {}

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
                # The download_vad function saves files with the naming convention:
                # WFO_SDUS3X_NVWXXX_YYYYMMDDHHMM
                # We need to find the most recent file that contains this site_id
                
                # First, try to find files that match the site pattern
                matching_files = []
                for filename in os.listdir(self.temp_dir):
                    # Look for files that contain NVW + site_id (without K prefix)
                    site_pattern = f"NVW{site_id[1:].upper()}"
                    if site_pattern in filename and not filename.endswith('.vad'):
                        matching_files.append((filename, os.path.getmtime(os.path.join(self.temp_dir, filename))))
                
                # Sort by modification time (most recent first)
                if matching_files:
                    matching_files.sort(key=lambda x: x[1], reverse=True)
                    newest_file = matching_files[0][0]
                    file_path = os.path.join(self.temp_dir, newest_file)
                    _fetch_cache[cache_key] = file_path
                    _fetch_cache_ttl[cache_key] = current_time
                    return file_path
                
                # Fallback: look for any recent file in temp_data
                all_files = []
                for filename in os.listdir(self.temp_dir):
                    if not filename.startswith('.'):
                        all_files.append((filename, os.path.getmtime(os.path.join(self.temp_dir, filename))))
                
                if all_files:
                    all_files.sort(key=lambda x: x[1], reverse=True)
                    newest_file = all_files[0][0]
                    file_path = os.path.join(self.temp_dir, newest_file)
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

    def fetch_recent(self, site_id: str, count: int = 7) -> List[Dict[str, Any]]:
        """
        Fetch the most recent ``count`` VAD scans for a site.

        Returns an ordered list of metadata dicts (newest first), one per
        successfully downloaded scan. Failures are logged and skipped.

        Each entry has the shape::

            {
                'file_id':     str (timestamp 'YYYYMMDDHHMM'),
                'valid_time':  datetime,
                'cached_path': str,
            }

        The history list is cached in-memory for 5 minutes. Downloads are
        parallelized; each downloaded file is also written to ``temp_data``
        on disk so subsequent requests are instant.
        """
        site_id = site_id.upper()
        cache_key = f"history_{site_id}_{count}"
        current_time = time.time()

        if (cache_key in _history_cache and
                current_time - _history_cache_ttl.get(cache_key, 0) < 300):
            return _history_cache[cache_key]

        self._ensure_temp_dir()

        try:
            file_list = _list_site_https(site_id)[:count]
        except Exception as e:
            print(f"HTTPS listing failed for {site_id}: {e}; falling back to FTP")
            try:
                file_list = find_file_times(site_id)[:count]
            except Exception as e2:
                print(f"Error fetching VAD file list for {site_id}: {e2}")
                return []

        site_url_prefix = f"{_HTTPS_BASE}/SI.{site_id.lower()}"
        session = _get_session()

        def _download_one(fn_ft):
            fn, ft = fn_ft
            try:
                # Cache hit by expected filename (timestamp from listing).
                iname = build_has_name(site_id, ft)
                cached_path = os.path.join(self.temp_dir, iname)
                if os.path.exists(cached_path) and os.path.getsize(cached_path) > 0:
                    return {
                        'file_id': ft.strftime('%Y%m%d%H%M'),
                        'valid_time': ft,
                        'cached_path': cached_path,
                    }

                # Direct HTTPS GET — skips download_vad's redundant re-listing.
                resp = session.get(f"{site_url_prefix}/{fn}", timeout=15)
                resp.raise_for_status()
                bio = BytesIO(resp.content)
                vad = VADFile(bio)
                actual_time = vad['time']
                iname = build_has_name(site_id, actual_time)
                cached_path = os.path.join(self.temp_dir, iname)
                with open(cached_path, 'wb') as f:
                    f.write(resp.content)
                return {
                    'file_id': actual_time.strftime('%Y%m%d%H%M'),
                    'valid_time': actual_time,
                    'cached_path': cached_path,
                }
            except Exception as e:
                print(f"Skipping VAD frame for {site_id} at {ft} ({fn}): {e}")
                return None

        # Use as many workers as files so all downloads start immediately.
        results: List[Dict[str, Any]] = []
        max_workers = max(1, min(len(file_list), 8))
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            for r in ex.map(_download_one, file_list):
                if r is not None:
                    results.append(r)

        # Deduplicate by file_id (the upstream listing can have duplicate
        # times across sn.last and the freshly-renamed file).
        seen = set()
        unique: List[Dict[str, Any]] = []
        for r in results:
            if r['file_id'] in seen:
                continue
            seen.add(r['file_id'])
            unique.append(r)

        unique.sort(key=lambda x: x['valid_time'], reverse=True)

        _history_cache[cache_key] = unique
        _history_cache_ttl[cache_key] = current_time
        return unique

    def get_frame_path(self, site_id: str, file_id: str) -> Optional[str]:
        """Look up a cached frame's on-disk path by site_id + file_id.

        Returns ``None`` when the frame isn't in the in-memory history cache
        for the site. Also performs a temp_dir scan as a fallback in case
        the cache was evicted.
        """
        site_id = site_id.upper()
        prefix = f"history_{site_id}_"
        for cache_key, frames in _history_cache.items():
            if not cache_key.startswith(prefix):
                continue
            for frame in frames:
                if frame['file_id'] == file_id:
                    return frame['cached_path']

        # Fallback: scan temp_data for a file whose timestamp matches.
        if os.path.exists(self.temp_dir):
            for filename in os.listdir(self.temp_dir):
                if filename.endswith(file_id) and f"NVW{site_id[1:].upper()}" in filename:
                    return os.path.join(self.temp_dir, filename)
        return None

    def cleanup(self):
        """Clean up temporary files."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
