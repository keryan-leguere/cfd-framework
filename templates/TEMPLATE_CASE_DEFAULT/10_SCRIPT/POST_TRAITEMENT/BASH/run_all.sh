#!/bin/bash

# BEFORE LAUNCHING THE SCRIP, ADD:
# In the the systeme/controlDict:
        # includeFunc residuals

foamCleanCase
mkdir -p "LOG"

echo "execution of blockMesh..."
blockMesh  > ./LOG/log.blockMesh

echo "execution of checkMesh..."
checkMesh  > ./LOG/log.checkMesh

echo "execution of decomposePar..."
decomposePar > ./LOG/log.decomposePar

echo "exectution of renumberMesh..."
mpirun -np 4 renumberMesh -parallel -overwrite -noFunctionObjects > ./LOG/log.renumberMesh 

echo "execution of the solver..."
mpirun -np 4 simpleFoam -parallel > ./LOG/log.simpleFoam

echo "execution of recontructPar..."
reconstructPar > ./LOG/log.reconstructPar

gnuplot ./SCRIPTS/GNUPLOT/plotResidualsFigure.gp

echo "Simulation completed"
