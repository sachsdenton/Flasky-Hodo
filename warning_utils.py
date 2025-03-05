"""
Utilities for fetching and processing NWS weather warnings data.
"""
import requests
import pandas as pd
import json
import re
from datetime import datetime
import streamlit as st
from typing import List, Dict, Any, Tuple, Optional

# NWS API endpoints
NWS_API_BASE = "https://api.weather.gov"
NWS_USER_AGENT = "(Hodograph Analysis Tool, contact@example.com)"

# Cache warnings data to avoid frequent API calls
@st.cache_data(ttl=300)  # Cache for 5 minutes
def fetch_active_warnings() -> List[Dict[str, Any]]:
    """
    Fetch active severe thunderstorm and tornado warnings from NWS API.
    
    Returns:
        List of dictionaries containing warning data
    """
    headers = {
        "User-Agent": NWS_USER_AGENT,
        "Accept": "application/geo+json"
    }
    
    try:
        # Fetch active alerts
        response = requests.get(
            f"{NWS_API_BASE}/alerts/active", 
            headers=headers,
            params={"event": "Tornado Warning,Severe Thunderstorm Warning"}
        )
        response.raise_for_status()
        
        data = response.json()
        
        # Extract only the warnings we're interested in
        warnings = []
        if "features" in data:
            for feature in data["features"]:
                prop = feature["properties"]
                
                # Check for warning types we want
                event = prop.get("event", "")
                if event in ["Tornado Warning", "Severe Thunderstorm Warning"]:
                    geometry = feature.get("geometry", {})
                    
                    # Get description and extract storm motion information
                    description = prop.get("description", "")
                    storm_motion = extract_storm_motion(description)
                    
                    warning_data = {
                        "id": prop.get("id", ""),
                        "event": event,
                        "headline": prop.get("headline", ""),
                        "description": description,
                        "severity": prop.get("severity", ""),
                        "certainty": prop.get("certainty", ""),
                        "urgency": prop.get("urgency", ""),
                        "sender": prop.get("senderName", ""),
                        "sent": prop.get("sent", ""),
                        "effective": prop.get("effective", ""),
                        "expires": prop.get("expires", ""),
                        "geometry": geometry,
                        "storm_motion": storm_motion
                    }
                    warnings.append(warning_data)
        
        return warnings
        
    except Exception as e:
        st.error(f"Error fetching warnings: {str(e)}")
        return []

def format_warning_time(time_str: str) -> str:
    """Format warning time to a more readable format."""
    try:
        dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
        return dt.strftime("%H:%M UTC %m/%d")
    except:
        return time_str

def get_warning_color(event_type: str) -> str:
    """Get the color for a specific warning type."""
    if event_type == "Tornado Warning":
        return "red"
    elif event_type == "Severe Thunderstorm Warning":
        return "orange"
    else:
        return "yellow"
        
def extract_storm_motion(description: str) -> Dict[str, Any]:
    """
    Extract storm motion information from warning description.
    
    Args:
        description: The warning description text
        
    Returns:
        Dictionary with direction and speed if found, otherwise empty
    """
    motion_info = {}
    
    # Common patterns for storm motion in NWS warnings
    # Pattern for "MOVING EAST AT 30 MPH" format
    direction_pattern = r"MOVING\s+([A-Z]+(?:\s+[A-Z]+)?)\s+AT\s+(\d+)\s+MPH"
    # Pattern for "MOVING NORTHEAST AT 35 MPH (55 KMH)" format with optional KMH
    direction_pattern_alt = r"MOVING\s+([A-Z]+(?:\s+[A-Z]+)?)\s+AT\s+(\d+)\s+MPH\s*(?:\(\d+\s+KMH\))?"
    # Pattern for with cardinal degrees "MOVING EAST (90 DEGREES) AT 30 MPH" format
    direction_degrees_pattern = r"MOVING\s+([A-Z]+(?:\s+[A-Z]+)?)\s*\((\d+)\s+DEGREES\)\s+AT\s+(\d+)\s+MPH"
    
    # Try the patterns in order
    match = re.search(direction_degrees_pattern, description, re.IGNORECASE)
    if match:
        motion_info["cardinal_direction"] = match.group(1).title()
        motion_info["direction_degrees"] = int(match.group(2))
        motion_info["speed"] = int(match.group(3))
        return motion_info
        
    match = re.search(direction_pattern, description, re.IGNORECASE) or re.search(direction_pattern_alt, description, re.IGNORECASE)
    if match:
        motion_info["cardinal_direction"] = match.group(1).title()
        motion_info["speed"] = int(match.group(2))
        # Convert cardinal direction to approximate degrees
        cardinal_to_degrees = {
            "NORTH": 0, "NORTHEAST": 45, "EAST": 90, "SOUTHEAST": 135,
            "SOUTH": 180, "SOUTHWEST": 225, "WEST": 270, "NORTHWEST": 315,
            "N": 0, "NE": 45, "E": 90, "SE": 135,
            "S": 180, "SW": 225, "W": 270, "NW": 315
        }
        direction_key = motion_info["cardinal_direction"].upper()
        if direction_key in cardinal_to_degrees:
            motion_info["direction_degrees"] = cardinal_to_degrees[direction_key]
        
    return motion_info

def get_warning_popup_content(warning: Dict[str, Any]) -> str:
    """Generate HTML content for warning popup."""
    expires = format_warning_time(warning.get("expires", ""))
    effective = format_warning_time(warning.get("effective", ""))
    
    # Pre-process description to replace newlines with <br> tags
    description = warning.get('description', 'No description available.')
    description_html = description.replace('\n', '<br>')
    
    # Get storm motion information
    storm_motion_html = ""
    if warning.get("storm_motion") and warning["storm_motion"]:
        motion = warning["storm_motion"]
        storm_motion_html = '<div style="margin-top: 10px; padding: 8px; background-color: #f5f5f5; border-radius: 4px;">'
        
        if "cardinal_direction" in motion and "speed" in motion:
            storm_motion_html += f'<p style="margin: 0;"><b>Storm Motion:</b></p>'
            storm_motion_html += f'<p style="margin: 0;"><b>Direction:</b> {motion["cardinal_direction"]}'
            
            if "direction_degrees" in motion:
                storm_motion_html += f' ({motion["direction_degrees"]}°)'
                
            storm_motion_html += f'</p><p style="margin: 0;"><b>Speed:</b> {motion["speed"]} MPH</p>'
        
        storm_motion_html += '</div>'
    
    return f"""
    <div style="max-width: 300px;">
        <h4 style="color: {get_warning_color(warning['event'])};">{warning['event']}</h4>
        <p><b>Issued by:</b> {warning.get('sender', 'NWS')}</p>
        <p><b>Effective:</b> {effective}</p>
        <p><b>Expires:</b> {expires}</p>
        <p><b>Severity:</b> {warning.get('severity', 'Unknown')}</p>
        <p><b>Certainty:</b> {warning.get('certainty', 'Unknown')}</p>
        {storm_motion_html}
        <details style="margin-top: 10px;">
            <summary>Description</summary>
            <p>{description_html}</p>
        </details>
    </div>
    """