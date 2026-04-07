import pandas as pd
import numpy as np

def interpolate_dataframe(data_dict, key_low, key_high, key_new, weight_new):
    """
    Create an interpolated dataframe between two existing dataframes in a dictionary.
    
    Parameters:
    -----------
    data_dict : dict
        Dictionary containing dataframes
    key_low : str
        Key of the lower bound dataframe (e.g., 'dict0')
    key_high : str
        Key of the upper bound dataframe (e.g., 'dict2000')
    key_new : str
        Key for the new interpolated dataframe (e.g., 'dict1250')
    weight_new : float
        Interpolation weight (0.0 = all from key_low, 1.0 = all from key_high)
        For dict1250 between dict0 and dict2000, use 1250/2000 = 0.625
    
    Returns:
    --------
    pd.DataFrame
        The interpolated dataframe (also stored in data_dict[key_new])
    
    Example:
    --------
    >>> interpolate_dataframe(my_dict, 'dict0', 'dict2000', 'dict1250', 1250/2000)
    """
    
    # Get the two dataframes
    df_low = data_dict[key_low]
    df_high = data_dict[key_high]
    
    # Verify they have the same shape and coordinates
    assert df_low.shape == df_high.shape, "Dataframes must have the same shape"
    assert all(df_low['X'] == df_high['X']), "X coordinates must match"
    assert all(df_low['Y'] == df_high['Y']), "Y coordinates must match"
    assert all(df_low['Z'] == df_high['Z']), "Z coordinates must match"
    
    # Create new dataframe starting with coordinates from df_low
    df_new = pd.DataFrame()
    df_new['X'] = df_low['X'].copy()
    df_new['Y'] = df_low['Y'].copy()
    df_new['Z'] = df_low['Z'].copy()
    
    # Identify QOI columns (all columns except X, Y, Z)
    coord_cols = ['X', 'Y', 'Z']
    qoi_cols = [col for col in df_low.columns if col not in coord_cols]
    
    # Linear interpolation for each QOI
    for col in qoi_cols:
        df_new[col] = (1 - weight_new) * df_low[col] + weight_new * df_high[col]
    
    # Store in dictionary
    data_dict[key_new] = df_new
    
    return df_new


# Usage example:
if __name__ == "__main__":
    # Example usage with your specific case
    # Assuming you have a dictionary called 'my_data'
    
    # my_data = {
    #     'dict0': df_at_0,
    #     'dict2000': df_at_2000
    # }
    
    # Create dict1250 by interpolating (1250 is 62.5% of the way from 0 to 2000)
    # interpolate_dataframe(my_data, 'dict0', 'dict2000', 'dict1250', 1250/2000)
    
    # Now my_data['dict1250'] contains the interpolated dataframe
    pass