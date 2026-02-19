# Objective of this script: [Insert a brief description of your script's purpose]
# MODULES:
import subprocess
import numpy as np
# Import additional modules if necessary (e.g., pandas, matplotlib)

# VARIABLES:


def calculate_recirculation_bubble_length(x, u):
    """
    Calculate the length of the recirculation bubble (Lrb)
    based on the velocity profile along the x-axis.

    Args:
        x (numpy.array): Array of x-coordinates.
        u (numpy.array): Array of velocity values corresponding to x.

    Returns:
        float: Length of the recirculation bubble (Lrb), or None if not found.
    """
    # Ensure the arrays are of the same length
    if len(x) != len(u):
        raise ValueError("x and u arrays must have the same length.")

    # Find the first point where u transitions from negative to positive
    for i in range(len(u) - 1):
        if u[i] <= 0 and u[i + 1] > 0:
            # Linearly interpolate to find the exact x-coordinate where u = 0
            Lrb = x[i] + (x[i + 1] - x[i]) * (0 - u[i]) / (u[i + 1] - u[i])
            return Lrb
 
    # If no recirculation bubble is found
    return None

# DATA IMPORT:

# 1. Specify the input file path and name
lastTime = subprocess.run("foamListTimes | tail -n 1 | tr -d '\n'", shell=True, capture_output=True, text=True).stdout
input_file = "./postProcessing/sampleDict_line/%s/profile_y_0_U.xy"%(lastTime) 

# 2. Load data from the file
[x, u] = np.loadtxt(input_file, delimiter=' ', usecols=[0, 1], unpack=True)

# DATA PROCESSING:

# 4. Perform computations using NumPy functions
# Calculate Lrb/D
D = 2
Lrb = (calculate_recirculation_bubble_length(x, u) - 1)/D

if Lrb is not None:
    print(f"{Lrb:.4e}")  # Output in scientific notation
else:
    print(" ")
