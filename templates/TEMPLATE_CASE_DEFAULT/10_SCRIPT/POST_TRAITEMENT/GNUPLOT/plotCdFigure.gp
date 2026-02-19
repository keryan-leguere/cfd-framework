set terminal postscript eps enhanced color font 'Helvetica,10'

# Adjusting the key (legend)
set key left box lw 2 font 'Helvetica,14'
set key spacing 1.5

# Adding space around the plot (margins)
set lmargin 15   # Left margin
set rmargin 10   # Right margin
set tmargin 6    # Top margin (for the title)
set bmargin 5    # Bottom margin (for the x-axis label)

# Axis numbers (xtics and ytics) made bigger
set xtics font 'Courier,14'
#set xtics 0,0.25,2.5 font 'Courier,14'
set ytics font 'Courier,14'

# Setting up grid
set grid

# Enabling dashed lines
set termoption dashed

set title "OpenFOAM Cd" font 'Times-Roman, 22'
set xlabel "Iterations" font 'Courier,24'
set ylabel "Cd" font 'Courier,24' offset -3,0
set key right top box

set output "postProcessing/forceCoeffsIncompressible/0/forceCoeffs.eps"

plot "./postProcessing/forceCoeffsIncompressible/0/forceCoeffs.dat" using 1:3 title "Cd" with lines lw 2

