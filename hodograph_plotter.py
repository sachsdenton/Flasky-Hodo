import matplotlib.pyplot as plt
import numpy as np
from typing import Tuple, Optional
from utils import calculate_wind_components
from datetime import datetime

class HodographPlotter:
    def __init__(self):
        self.fig = None
        self.ax = None
        self.max_speed = None  # Will be set dynamically based on data

    def calculate_max_speed(self, speeds: list) -> int:
        """Calculate the maximum speed rounded up to nearest 10."""
        if not hasattr(speeds, '__len__') or len(speeds) == 0:
            return 100  # Default if no data
        max_speed = float(np.max(speeds))  # Convert to float to handle numpy types
        return int(np.ceil(max_speed / 10.0)) * 10

    def setup_plot(self, site_id: Optional[str] = None, site_name: Optional[str] = None, valid_time: Optional[datetime] = None) -> None:
        """
        Initialize the hodograph plot with dynamic maximum range.

        Args:
            site_id: Four letter radar site identifier
            site_name: Location of the radar site (city, state)
            valid_time: Valid time of the data
        """
        # Close any existing figures
        plt.close('all')

        # Create a figure with more vertical space for title and labels
        self.fig, self.ax = plt.subplots(figsize=(8, 9))

        # Add title with site information and time if provided
        title_parts = []
        if site_id and site_name:
            title_parts.append(f"{site_id} - {site_name}")
        if valid_time:
            time_str = valid_time.strftime('%Y-%m-%d %H:%M UTC')
            title_parts.append(f"Valid: {time_str}")
        
        # Add METAR information if available in session state (to be done in main.py)
        # This placeholder will be used to add a title line for METAR data later
            
        if title_parts:
            # Set the title higher up with more space between title and plot
            self.fig.suptitle('\n'.join(title_parts), y=0.98)

        # Set up the plot
        self.ax.set_aspect('equal')
        self.ax.grid(True)

        # Draw speed rings (will be set when plotting data)
        if self.max_speed:
            speed_rings = list(range(10, self.max_speed + 1, 10))
            for speed in speed_rings:
                circle = plt.Circle((0, 0), speed, fill=False, color='gray', linestyle='--', alpha=0.5)
                self.ax.add_artist(circle)

            # Set limits and labels
            self.ax.set_xlim(-self.max_speed, self.max_speed)
            self.ax.set_ylim(-self.max_speed, self.max_speed)
            self.ax.set_xlabel('U-component (knots)')
            self.ax.set_ylabel('V-component (knots)')

            # Add cardinal directions in meteorological convention
            self.ax.text(0, -self.max_speed - 2, 'N', ha='center')
            self.ax.text(-self.max_speed - 2, 0, 'E', va='center')
            self.ax.text(0, self.max_speed + 2, 'S', ha='center')
            self.ax.text(self.max_speed + 2, 0, 'W', va='center')

    def plot_profile(self, profile, height_colors: bool = True) -> None:
        """
        Plot wind profile on the hodograph.

        Args:
            profile: WindProfile object containing the data
            height_colors: Whether to color code by height
        """
        if not profile.validate():
            raise ValueError("Invalid wind profile data")

        # Set max_speed based on data
        self.max_speed = self.calculate_max_speed(profile.speeds)

        # Recreate the plot with the new max_speed and preserve header info
        self.setup_plot(
            site_id=getattr(profile, 'site_id', None),
            site_name=getattr(profile, 'site_name', None),
            valid_time=profile.times[0] if profile.times else None
        )

        # Calculate u and v components
        u_comp = []
        v_comp = []
        for speed, direction in zip(profile.speeds, profile.directions):
            u, v = calculate_wind_components(speed, direction)
            u_comp.append(u)
            v_comp.append(v)

        u_comp = np.array(u_comp)
        v_comp = np.array(v_comp)
        heights = np.array(profile.heights)

        if height_colors:
            # Create color gradient based on height
            colors = plt.cm.viridis(heights / np.max(heights))

            # Plot segments with color gradient
            for i in range(len(u_comp) - 1):
                self.ax.plot(u_comp[i:i+2], v_comp[i:i+2], 
                           color=colors[i], linewidth=2)
        else:
            self.ax.plot(u_comp, v_comp, 'b-', linewidth=2)

        # First, scatter all points with smaller markers for reference
        self.ax.scatter(u_comp, v_comp, c='red', s=20, zorder=5, alpha=0.5)
        
        # Find all target heights we want to label (0.5, 1, 1.5, 2, 2.5, etc.)
        # Start at 0.5km and go up to the maximum height rounded up to next 0.5km
        max_height_m = np.max(heights) * 1000 if len(heights) > 0 else 0
        
        # Generate all the target heights in 0.5km increments
        target_heights_km = np.arange(0.5, max_height_m/1000 + 0.5, 0.5)
        
        # Generate heights at 1km increments first to prioritize them
        km_targets = []
        half_km_targets = []
        
        for target_km in target_heights_km:
            if abs(target_km - round(target_km)) < 0.01:  # Full kilometer
                km_targets.append(target_km)
            else:  # Half kilometer
                half_km_targets.append(target_km)
        
        # Process full km targets first
        for target_km in km_targets:
            target_m = target_km * 1000  # Convert to meters
            
            # Find the index of the closest height
            height_diffs = np.abs(heights * 1000 - target_m)
            if len(height_diffs) == 0:
                continue
                
            closest_idx = np.argmin(height_diffs)
            
            # Use points that are within 500m (more lenient to ensure we get kilometer labels)
            max_diff = 500  # 500m max difference for full kilometers
            
            if height_diffs[closest_idx] <= max_diff:
                closest_u = u_comp[closest_idx]
                closest_v = v_comp[closest_idx]
                
                # Whole kilometer
                height_label = f'{int(target_km)}'
                circle_color = 'blue'
                circle_size = 300  # Larger circles for km points
                
                # Add the circle with the height label
                self.ax.scatter([closest_u], [closest_v], s=circle_size, c=circle_color, zorder=6, 
                               edgecolor='black', linewidth=1)
                
                # Add the text on top of the circle
                self.ax.text(closest_u, closest_v, height_label, color='white', 
                            ha='center', va='center', fontweight='bold', fontsize=9, zorder=7)
        
        # Then process half km targets
        for target_km in half_km_targets:
            target_m = target_km * 1000  # Convert to meters
            
            # Find the index of the closest height
            height_diffs = np.abs(heights * 1000 - target_m)
            if len(height_diffs) == 0:
                continue
                
            closest_idx = np.argmin(height_diffs)
            
            # Use points that are within 250m (more lenient than before)
            max_diff = 250  # 250m max difference for half kilometers
            
            if height_diffs[closest_idx] <= max_diff:
                closest_u = u_comp[closest_idx]
                closest_v = v_comp[closest_idx]
                
                # Special case for 0.5km, show as .5
                if abs(target_km - 0.5) < 0.01:
                    height_label = '.5'
                else:
                    # All other half-kilometers show as whole numbers
                    height_label = f'{int(target_km)}'
                
                circle_color = 'gray'
                circle_size = 250  # Slightly smaller for half km
                
                # Add the circle with the height label
                self.ax.scatter([closest_u], [closest_v], s=circle_size, c=circle_color, zorder=6, 
                               edgecolor='black', linewidth=1)
                
                # Add the text on top of the circle
                self.ax.text(closest_u, closest_v, height_label, color='white', 
                            ha='center', va='center', fontweight='bold', fontsize=9, zorder=7)

    def add_layer_mean(self, profile, bottom: float, top: float) -> None:
        """
        Add layer mean wind vector to plot.

        Args:
            profile: WindProfile object
            bottom: Bottom of layer (meters)
            top: Top of layer (meters)
        """
        mean_wind = profile.get_layer_mean(bottom, top)
        u, v = calculate_wind_components(mean_wind["speed"], mean_wind["direction"])

        # Plot mean wind vector
        self.ax.arrow(0, 0, u, v, color='red', width=0.5, 
                     head_width=2, head_length=2, zorder=6)

    def save_plot(self, filename: str) -> None:
        """
        Save the hodograph plot to a file.

        Args:
            filename: Output filename
        """
        self.fig.savefig(filename, bbox_inches='tight', dpi=300)
        plt.close(self.fig)  # Close after saving

    def get_plot(self) -> Tuple[plt.Figure, plt.Axes]:
        """
        Get the current plot figure and axes.

        Returns:
            Tuple of (Figure, Axes)
        """
        return self.fig, self.ax