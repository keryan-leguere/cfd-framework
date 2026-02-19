"""
calculate_reynolds.py

This script calculates the Reynolds number for a given flow using parameters from
OpenFOAM files. The Reynolds number (Re) is calculated using the formula:

    Re = U * L / nu

where:
- U is the magnitude of the freestream velocity vector.
- L is the characteristic length, provided as an argument.
- nu is the kinematic viscosity, extracted from OpenFOAM's "constant/transportProperties" file.

The script:
1. Extracts the velocity components (Ux, Uy, Uz) for a specified boundary patch from the `0/U` file.
2. Calculates the magnitude of the velocity vector U = sqrt(Ux^2 + Uy^2 + Uz^2).
3. Extracts the kinematic viscosity (nu) from `constant/transportProperties`.
4. Calculates the Reynolds number using the provided length (L) and extracted U and nu values.

Usage:
    python3 calculate_reynolds.py <L> <patch_name>

Arguments:
- L: Characteristic length used in the Reynolds number calculation (float).
- patch_name: The name of the boundary patch in the `0/U` file where velocity components are defined.

Example:
Suppose we have a characteristic length of 1.0 and want to calculate the Reynolds number using the
velocity specified for the `left` patch in the `0/U` file.

Command:
    python3 calculate_reynolds.py 1.0 left

Assumptions:
- The `0/U` file contains the velocity in the form `uniform (Ux Uy Uz);` within the specified patch.
- The `constant/transportProperties` file defines `nu` as `nu [ 0 2 -1 0 0 0 0 ] <value>;`.

Output:
- The script outputs the Reynolds number in scientific notation.
"""

import re
import sys
import math

def extract_velocity(filename, patch_name):
    try:
        with open(filename, 'r') as file:
            content = file.read()
            # Use regex to find the specified patch and extract U components
            pattern = rf"{patch_name}.*?uniform\s+\(([\d\.\-eE]+)\s+([\d\.\-eE]+)\s+([\d\.\-eE]+)\)"
            match = re.search(pattern, content, re.DOTALL)
            if match:
                Ux, Uy, Uz = map(float, match.groups())
                return math.sqrt(Ux**2 + Uy**2 + Uz**2)
            else:
                print(f"Error: Velocity for patch '{patch_name}' not found in {filename}.")
                sys.exit(1)
    except FileNotFoundError:
        print(f"Error: File {filename} not found.")
        sys.exit(1)

def extract_nu(filename):
    try:
        with open(filename, 'r') as file:
            content = file.read()
            # Use regex to find the nu value
            match = re.search(r'nu\s+([\d\.\-eE]+);', content)
            if match:
                return float(match.group(1))
            else:
                print(f"Error: nu value not found in {filename}.")
                sys.exit(1)
    except FileNotFoundError:
        print(f"Error: File {filename} not found.")
        sys.exit(1)

def calculate_reynolds_number(L, U, nu):
    return U * L / nu

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 calculate_reynolds.py <L> <patch_name>")
        sys.exit(1)
    
    L = float(sys.argv[1])
    patch_name = sys.argv[2]

    U = extract_velocity("./0/U", patch_name)
    nu = extract_nu("./constant/transportProperties")
    reynolds_number = calculate_reynolds_number(L, U, nu)
    print(f"{reynolds_number:.3e}")  # Output in scientific notation
