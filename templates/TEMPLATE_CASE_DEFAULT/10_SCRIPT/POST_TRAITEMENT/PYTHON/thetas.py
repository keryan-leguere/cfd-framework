# Objective of this script:
# Calculate the separation angle (hs) where the vorticity becomes null 
# based on the data file containing x, y coordinates and vorticity values.

# MODULES:
import numpy as np
import subprocess
# Import additional modules if necessary (e.g., pandas, matplotlib)

# VARIABLES:
def calculate_separation_angle(x, y, vorticity):
    """
    Calculate the separation angle (hs) based on vorticity data.
    
    Args:
        x (numpy.array): Array of x-coordinates.
        y (numpy.array): Array of y-coordinates.
        vorticity (numpy.array): Array of vorticity values corresponding to (x, y).
    
    Returns:
        float: Separation angle (hs) in degrees, or None if not found.
    """
    # Ensure the arrays are of the same length
    if len(x) != len(y) or len(x) != len(vorticity):
        raise ValueError("x, y, and vorticity arrays must have the same length.")
    
    # Convert (x, y) to angular position (theta) in radians
    theta = np.arctan2(y, x)
    
    # Ensure theta is in the range [0, 2*pi]
    theta = np.mod(theta, 2 * np.pi)
    
    # Sort theta and corresponding vorticity for smooth processing
    sorted_indices = np.argsort(theta)
    theta = theta[sorted_indices]
    vorticity = vorticity[sorted_indices]
    
    # Find the first point where vorticity transitions from positive to negative
    for i in range(len(vorticity) - 1):
        if vorticity[i] > 0 and vorticity[i + 1] <= 0:
            # Linearly interpolate to find the exact theta where vorticity = 0
            hs_rad = theta[i] + (theta[i + 1] - theta[i]) * (0 - vorticity[i]) / (vorticity[i + 1] - vorticity[i])
            hs_deg = np.degrees(hs_rad)  # Convert to degrees
            return hs_deg
    
    # If no separation angle is found
    return None


# DATA IMPORT:

# 1. Specify the input file path and name
lastTime = subprocess.run("foamListTimes | tail -n 1 | tr -d '\n'", shell=True, capture_output=True, text=True).stdout
input_file = f"postProcessing/sampleDict_surface/{lastTime}/vorticity_walls_interpolated.raw"

# 2. Load data from the file
data = np.loadtxt(input_file, delimiter=' ', usecols=[0, 1, 2,5])
filtered_data = data[data[:, 2] > 0]

x = filtered_data[:, 0]  # Column 0
y = filtered_data[:, 1]  # Column 1
vorticity = filtered_data[:, 3]  # Column 5 (index 3 after usecols selection)


# DATA PROCESSING:

# Calculate the separation angle
hs = calculate_separation_angle(x, y, vorticity)

if hs is not None:
    print(f"{hs:.2f}")  # Output in scientific notation
else:
    print(" ")
