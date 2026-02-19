def calculate_nu(re, U, L):
    """
    Calculate kinematic viscosity (nu) for a given Reynolds number
    based on the formula: nu = (U * L) / Re.
    """
    return (U * L) / re

if __name__ == "__main__":

    # Write the input file for the parametric study launch script
    print(calculate_nu(40,1,2))
