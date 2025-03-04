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

        # Plot points with larger markers
        self.ax.scatter(u_comp, v_comp, c='red', s=50, zorder=5)
        
        # Add altitude callouts for all kilometer and 500m increments
        for i, (u, v, h) in enumerate(zip(u_comp, v_comp, heights)):
            # Convert height to meters
            height_m = h * 1000
            
            # Format: show every kilometer and half kilometer
            if height_m >= 500:  # Only show labels for 500m and above
                # Determine label text
                if abs(height_m / 1000 - round(height_m / 1000)) < 0.05:
                    # Whole kilometer
                    height_label = f'{int(round(height_m / 1000))}km'
                    connect_style = 'solid'
                    bbox_color = 'blue'
                elif abs(height_m / 500 - round(height_m / 500)) < 0.1 and round(height_m / 500) % 2 != 0:
                    # Half kilometer
                    if height_m < 1000:
                        height_label = f'500m'
                    else:
                        height_label = f'{int(height_m // 1000)}.5km'
                    connect_style = 'dotted'
                    bbox_color = 'gray'
                else:
                    continue
                
                # Calculate offset direction (to avoid overlapping labels)
                angle = (i * 45) % 360  # Distribute labels in different directions
                dx = 20 * np.cos(np.deg2rad(angle))
                dy = 20 * np.sin(np.deg2rad(angle))
                
                # Display the label with connecting line
                self.ax.annotate(
                    height_label, 
                    xy=(u, v),
                    xytext=(dx, dy),  # Position farther from point
                    textcoords='offset points',
                    fontsize=9,
                    bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=bbox_color, alpha=0.8),
                    arrowprops=dict(
                        arrowstyle='-',
                        connectionstyle='arc3,rad=0.0',
                        linestyle=connect_style,
                        color='gray'
                    )
                )

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