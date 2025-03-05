"""
Utilities for fetching and processing NWS weather warnings data.
"""
import requests
import pandas as pd
import json
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
                    
                    warning_data = {
                        "id": prop.get("id", ""),
                        "event": event,
                        "headline": prop.get("headline", ""),
                        "description": prop.get("description", ""),
                        "severity": prop.get("severity", ""),
                        "certainty": prop.get("certainty", ""),
                        "urgency": prop.get("urgency", ""),
                        "sender": prop.get("senderName", ""),
                        "sent": prop.get("sent", ""),
                        "effective": prop.get("effective", ""),
                        "expires": prop.get("expires", ""),
                        "geometry": geometry
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

def get_warning_popup_content(warning: Dict[str, Any]) -> str:
    """Generate HTML content for warning popup."""
    expires = format_warning_time(warning.get("expires", ""))
    effective = format_warning_time(warning.get("effective", ""))
    
    # Pre-process description to replace newlines with <br> tags
    description = warning.get('description', 'No description available.')
    description_html = description.replace('\n', '<br>')
    
    return f"""
    <div style="max-width: 300px;">
        <h4 style="color: {get_warning_color(warning['event'])};">{warning['event']}</h4>
        <p><b>Issued by:</b> {warning.get('sender', 'NWS')}</p>
        <p><b>Effective:</b> {effective}</p>
        <p><b>Expires:</b> {expires}</p>
        <p><b>Severity:</b> {warning.get('severity', 'Unknown')}</p>
        <p><b>Certainty:</b> {warning.get('certainty', 'Unknown')}</p>
        <details>
            <summary>Description</summary>
            <p>{description_html}</p>
        </details>
    </div>
    """