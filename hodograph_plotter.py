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
        if not speeds:
            return 100  # Default if no data
        max_speed = max(speeds)
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

        self.fig, self.ax = plt.subplots(figsize=(8, 8))

        # Add title with site information and time if provided
        if site_id and site_name and valid_time:
            time_str = valid_time.strftime('%Y-%m-%d %H:%M UTC')
            title = f"{site_id} - {site_name}\nValid: {time_str}"
            self.fig.suptitle(title, y=0.95)

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

        # Recreate the plot with the new max_speed
        self.setup_plot()

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

        # Plot points
        self.ax.scatter(u_comp, v_comp, c='red', s=30, zorder=5)

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