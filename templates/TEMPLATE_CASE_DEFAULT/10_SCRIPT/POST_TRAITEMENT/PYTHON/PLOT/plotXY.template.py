# ---- Python Script: Professional Plot Template with Styles and Shading ----
"""
This script provides a template for plotting y versus x with high-quality settings suitable
for scientific publications. It demonstrates how to use different line styles, symbols, and
fill areas in a plot.
"""

# ---- Importing Required Libraries (DO NOT MODIFY) ----
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import colormaps







###########################################################################
#           ---- CONFIGURATION SECTION (MODIFY AS NEEDED) ----            #
###########################################################################

# Adjust these settings as needed to achieve the desired plot appearance.

# Plot style and text rendering
plt.style.use('default')  # Use a clean style.
plt.rc('text', usetex=True)          # Use LaTeX for text rendering if available.
plt.rc('font', family='serif')       # Use serif font for a more professional look.

# Figure settings
FIG_SIZE = (6, 4)        # Width and height in inches.
DPI = 300               # Resolution for saving the plot.
LINE_WIDTH = 2          # Line width for plots.
MARKER_SIZE = 3         # Size of the markers.
FONT_SIZE = 14          # Base font size for labels and titles.

# Colormap for plotting
CMAP = colormaps['plasma']  # Choose a colormap for distinguishing different lines.

# Axis limits (set to None to let matplotlib choose automatically)
X_LIMIT = (None, None)  # Example: (0, 10)
Y_LIMIT = (None, None)  # Example: (-1.5, 1.5)

# Labels and title
X_LABEL = r"$x$ (units)"       # X-axis label.
Y_LABEL = r"$y$ (units)"       # Y-axis label.
PLOT_TITLE = "Sine Wave with Shaded Ground"  # Title of the plot (set to None if no title is needed).

# Legend settings
SHOW_LEGEND = True             # Set to False to hide legend.
LEGEND_LOC = 'upper right'     # Location of the legend ('best' places it automatically).

# Grid settings
SHOW_GRID = False               # Set to False to hide grid.
GRID_STYLE = '--'              # Style of the grid lines (e.g., '--' for dashed lines).

# Output file settings
OUTPUT_FILENAME = './POST_PROCESSING/FIGURES/output.png'  # Output filename for the saved plot.
SAVE_FORMAT = 'png'                  # Format for saving ('png', 'pdf', etc.).

# ---- END OF CONFIGURATION SECTION ----

# ---- PRINT CONFIGURATION ----
print("\n" + "-"*60)
print(f"   Professional Plotting Script")
print("-"*60)
print(f"Plot Title        : {PLOT_TITLE}")
print(f"X-axis Label      : {X_LABEL}")
print(f"Y-axis Label      : {Y_LABEL}")
print(f"Figure Size       : {FIG_SIZE[0]} inches x {FIG_SIZE[1]} inches")
print(f"Output Filename   : {OUTPUT_FILENAME}")
print(f"Resolution (DPI)  : {DPI}")
print(f"Line Width        : {LINE_WIDTH}")
print(f"Marker Size       : {MARKER_SIZE}")
print(f"Legend            : {'Shown' if SHOW_LEGEND else 'Hidden'}, Location: {LEGEND_LOC}")
print(f"Grid              : {'Enabled' if SHOW_GRID else 'Disabled'}, Style: {GRID_STYLE}")
print(f"X-axis Limits     : {X_LIMIT}")
print(f"Y-axis Limits     : {Y_LIMIT}")
print(f"Colormap          : {CMAP.name}")
print("-"*60)
print("   Starting data processing and plotting...")
print("-"*60 + "\n")





# ---- DATA LOADING AND PROCESSING (MODIFY AS NEEDED) ----
# This is where you load and process data for your specific plot.
# Replace this section with your actual data loading logic.

# Example data generation for demonstration.
# Replace this with np.loadtxt() or another method if reading from a file.
x = np.linspace(0, 10, 100)        # Example x data.
y1 = np.sin(x)                      # Example y data (sine wave).
y2 = np.cos(x)                      # Example y data (cosine wave).

# ---- END OF DATA LOADING SECTION ----



# ---- PLOTTING SECTION (DO NOT MODIFY UNLESS NECESSARY) ----
# This section configures the plot appearance based on the settings above.

# Create the figure and axis object.
fig, ax = plt.subplots(1, 1, figsize=FIG_SIZE)

# Plotting the first line with a solid line and circle markers
ax.plot(x, y1, linestyle='-', marker='o', color=CMAP(0.0), label=r"$\sin(x)$",
        linewidth=LINE_WIDTH, markersize=MARKER_SIZE, alpha=0.8, zorder=3)

# Plotting the second line with a dashed line and triangle markers
ax.plot(x, y2, linestyle='--', marker='^', color=CMAP(0.6), label=r"$\cos(x)$",
        linewidth=LINE_WIDTH, markersize=MARKER_SIZE, alpha=0.8, zorder=2)

# Example of shading the area below y = 0 to represent the ground
ax.fill_between(x, -1.5, -1.2, color='gray', alpha=1, zorder=1)




















############################### DO NO TOUCH ANYTHING THERE ###################################################

# Configure labels and title.
ax.set_xlabel(X_LABEL, fontsize=FONT_SIZE)
ax.set_ylabel(Y_LABEL, fontsize=FONT_SIZE)
if PLOT_TITLE:
    ax.set_title(PLOT_TITLE, fontsize=FONT_SIZE + 2)

# Set axis limits if specified.
if X_LIMIT != (None, None):
    ax.set_xlim(X_LIMIT)
if Y_LIMIT != (None, None):
    ax.set_ylim(Y_LIMIT)

# Show legend if enabled.
if SHOW_LEGEND:
    ax.legend(loc=LEGEND_LOC, fontsize=FONT_SIZE - 2,frameon=True, facecolor='white', edgecolor='black')
    #ax.legend(loc=LEGEND_LOC, bbox_to_anchor=(1, 0.5), fontsize=FONT_SIZE - 2)

# Show grid if enabled.
if SHOW_GRID:
    ax.grid(True, linestyle=GRID_STYLE)

# Adjust layout for better appearance.
plt.tight_layout()

# Save the figure with the specified settings.
plt.savefig(OUTPUT_FILENAME, format=SAVE_FORMAT, dpi=DPI)
print(f"Plot saved as '{OUTPUT_FILENAME}'")

#plt.show()

print("\n---- End of Script ----")
