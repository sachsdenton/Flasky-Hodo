"""
Handles fetching VAD data from NEXRAD sites.
"""
import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Optional, List, Dict, Any
from vad_reader import download_vad, find_file_times
from wsr88d import build_has_name

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
            file_list = find_file_times(site_id)[:count]
        except Exception as e:
            print(f"Error fetching VAD file list for {site_id}: {e}")
            return []

        def _download_one(fn_ft):
            fn, ft = fn_ft
            try:
                # Try cached file first using the expected naming convention
                try:
                    iname = build_has_name(site_id, ft)
                    cached_path = os.path.join(self.temp_dir, iname)
                    if os.path.exists(cached_path) and os.path.getsize(cached_path) > 0:
                        return {
                            'file_id': ft.strftime('%Y%m%d%H%M'),
                            'valid_time': ft,
                            'cached_path': cached_path,
                        }
                except Exception:
                    pass

                vad = download_vad(site_id, time=ft, cache_path=self.temp_dir)
                actual_time = vad['time']
                iname = build_has_name(site_id, actual_time)
                cached_path = os.path.join(self.temp_dir, iname)
                if not os.path.exists(cached_path):
                    return None
                return {
                    'file_id': actual_time.strftime('%Y%m%d%H%M'),
                    'valid_time': actual_time,
                    'cached_path': cached_path,
                }
            except Exception as e:
                print(f"Skipping VAD frame for {site_id} at {ft}: {e}")
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
