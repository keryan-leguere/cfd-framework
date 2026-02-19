###############################################################################
# Plot Residuals from OF
###############################################################################

# --- SPECIFIC VARIABLES ---
OUTPUT_FILE = "postProcessing/residuals(p,U,T)/0/residuals.png"
XLABEL = "Iterations"
YLABEL = "Residuals"
TITLE  = "OpenFOAM Residuals"

# --- LOAD GLOBAL STYLE ---
#DATA_DIR = system("echo $OFSCRIPT_DIR")
DATA_DIR = "/home/helios/OpenFOAM/helios-13/run/SCRIPT"
load DATA_DIR . "/TEMPLATE_CASE/10_SCRIPT/POST_TRAITEMENT/GNUPLOT/gnuplot_template.gp"

# --- FILES & LIMITS (your specific data) ---
RESIDUALS = "./postProcessing/residuals(p,U,T)/0/residuals.dat"

set logscale y
set format y "1e%T"
set format x "%.0f"
set key width 1.0
set grid lw 1 lc rgb "#000000" dashtype 1
set grid xtics ytics back
set grid mxtics mytics

# --- PLOT --------------------------------------------------------------------
plot \
    RESIDUALS using 1:3 with lines ls 2 title "Ux", \
    RESIDUALS using 1:4 with lines ls 3 title "Uy", \
    RESIDUALS using 1:2 with lines ls 4 title "p" , \
    RESIDUALS using 1:5 with lines ls 4 title "T"

# --- END / RESET -------------------------------------------------------------
unset output
reset
