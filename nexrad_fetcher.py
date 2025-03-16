"""
Handles fetching VAD data from NEXRAD sites.
"""
import os
import shutil
import streamlit as st
from datetime import datetime
from typing import Optional
from vad_reader import download_vad

class NEXRADFetcher:
    def __init__(self):
        self.temp_dir = "temp_data"

    def _ensure_temp_dir(self):
        """Ensure temporary directory exists."""
        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir)

    @st.cache_data(ttl=300)  # Cache for 5 minutes
    def fetch_latest(self, site_id: str) -> Optional[str]:
        """
        Fetch the latest VAD file for a given radar site.
        Results are cached for 5 minutes to reduce API calls.

        Args:
            site_id: Radar site identifier (e.g., 'KTLX')

        Returns:
            Path to downloaded file or None if failed
        """
        self._ensure_temp_dir()
        output_path = os.path.join(self.temp_dir, f"{site_id.lower()}_latest.vad")

        try:
            # Use the original VAD plotter's download function with caching
            vad = download_vad(site_id, cache_path=self.temp_dir)
            return output_path if vad else None

        except Exception as e:
            print(f"Error fetching VAD data: {e}")
            return None

    def cleanup(self):
        """Clean up temporary files."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)