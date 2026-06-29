# Ideas to batch plot a study

## Objectives:
The idea behind "batch plotting" is that for a study i get results from mutliplt sources: CFD, analytics, experiment.
Most of the time, i need to apply specific python treatment for each source to get the post-processed data, then i plot each sources against each other on a curve, and this for each flight point.
The objective here is to create some guidelines to structure the data and have a wrapper around the plotting library to batch plot = plot for every flight point my data. The difficulty is that it needs to be generic, so i can reuse it for every case, but also very flexible and i have control on the plot (for ex if i want to add a curve for just one plot, or locally change the color of a curve if i want to and so on...)

## Inputs:
I would like to prepare the generation of the figures with dictionary.
For example, we could define a Y-axis dict (for the QOIs):
y_axis_dict={
    "CN":{
        "col_name":"CN",
        "ylabel":r"C_N",
        "y_save_name:"CN",
        "other_key_for_this_qoi:"red",
    "other_qoi":{
    ...
    }
}

We could also define a X-axis dict (for the variables):
x_axis_dict={
    "MACH":{
        "col_name":"Mach",
        "ylabel":r"M",
        "y_save_name:"MACH",
        "other_key_for_this_qoi:"red",
    "other_variables":{
    ...
    }
}

Finally the parameters, meaning each curve for the plot can be define in a dictionary:
configuration_dict:{
    "KW":
        "name":"KW",
        "label":r"k-\omega",
        "dir:"",
        "CDG:"[0,0,0]",
        "other_key_for_this_qoi:"red"
        "df":Pandas.dataFrames(),
    "SA":
        "name":"SA",
        "label":r"SA",
        "dir:"",
        "CDG:"[0,0,0]",
        "other_key_for_this_qoi:"red"
        "df":Pandas.dataFrames(),
    "EXP":
        "name":"REF"
        "label":r"Ref.",
        "dir:"",
        "CDG:"[0,0,0]",
        "other_key_for_this_qoi:"red"
        "df":Pandas.dataFrames(),
    "other_qoi":{
    ...
    }
}

and finally the flight point dict:
this could be automatically completed by taking the unique list of each parameter of the concat df of all the df in configuration_dict.
flight_point_dict:{
    "Mach":
    "Altitude_m":
    "alpha":
    "beta":
    "DL":
    "DM":
    "DN":
}

## Workflow and tasks:
1. I already have some postprocessing scriopt to transform my data into a df, so it sould be assumed that i already have the configuration_dict.
The first is to create fake data in /scripts/post/plot/tests/E2E_MULTIPLE_PLOTTING. You will the header of typcal post-processsed file. 
Create 3 files, with this header and some dummy data (like 30 lines).

2. You will create a python script to test the bash plot wrapper. It needs to create the configuration_dict by loading the created csv. It needs to create all the dict explained previously. It will also take the base file path to save the pictures.

3. Then you will fully write the batch plot wrapper. It should take as an input the dicts created. It needs to plot using the plotting library of course. The file will be saved as svg. The file will be saved at the file path + each flight parameter/ ex MACH/ALTITUDE_M/ALPHA/BETA. If the list contains only one number like DL=DM=DN=0, then you don't create a directory.

4. Verify the script works fine with the wrapper. Write simple, well explained and professionnal code.



